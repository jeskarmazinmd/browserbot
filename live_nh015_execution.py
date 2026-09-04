"""Fail-closed live allocation state for C3N25S10NH015.

The allocation rules intentionally mirror the rolling 5K portfolio model:
$5,000 initial capital, 1% equity risk per trade, a 20% maximum position,
whole shares, capital unavailable until the position closes, and each day's
ending equity carried into the next day. Actual broker P/L is applied when a
live exit is reconciled.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
from typing import Any, Mapping
from zoneinfo import ZoneInfo


STRATEGY_ID = "C3N25S10NH015"
STARTING_CASH = 5000.0
RISK_FRACTION = 0.01
MAX_POSITION_FRACTION = 0.20
NY = ZoneInfo("America/New_York")

# An unfunded-account transport test may explicitly allow a cash failure to
# reach Schwab's order endpoint.  This exception is opt-in and must never be
# inferred merely from the account being empty.
UNFUNDED_PROBE_ADVISORY_FINDINGS = frozenset({"insufficient_broker_cash"})


def partition_broker_preflight_findings(
    findings: list[str],
) -> tuple[list[str], list[str]]:
    """Split blockers from explicitly enabled unfunded-probe advisories."""
    advisory_findings = (
        UNFUNDED_PROBE_ADVISORY_FINDINGS
        if unfunded_order_probe_enabled()
        else frozenset()
    )
    blockers = [item for item in findings if item not in advisory_findings]
    advisories = [item for item in findings if item in advisory_findings]
    return blockers, advisories


def _truthy(name: str, default: str = "0") -> bool:
    return os.environ.get(name, default).strip().lower() in {
        "1", "true", "yes", "on",
    }


def unfunded_order_probe_enabled() -> bool:
    """Allow cash failures through only for deliberate empty-account tests."""
    return _truthy("LIVE_UNFUNDED_ORDER_PROBE_ENABLED")


def daily_loss_fraction() -> float:
    """Configured daily halt fraction; zero disables the optional breaker."""
    raw = os.environ.get("LIVE_DAILY_LOSS_LIMIT_PCT", "0").strip()
    try:
        percent = float(raw)
    except ValueError as exc:
        raise RuntimeError("LIVE_DAILY_LOSS_LIMIT_PCT must be numeric") from exc
    if percent < 0 or percent >= 100:
        raise RuntimeError("LIVE_DAILY_LOSS_LIMIT_PCT must be in [0, 100)")
    return percent / 100.0


def cash_only_preflight_findings(
    balances: Mapping[str, Any],
    required_cash: float,
) -> list[str]:
    """Validate an order against cash fields without considering margin credit."""
    cash_values = []
    for key in ("cashBalance", "cashAvailableForTrading"):
        try:
            if balances.get(key) is not None:
                cash_values.append(float(balances[key]))
        except (TypeError, ValueError):
            pass
    if not cash_values:
        return ["broker_cash_balance_unavailable"]
    if min(cash_values) + 1e-9 < float(required_cash):
        return ["insufficient_broker_cash"]
    return []


def margin_debit_findings(balances: Mapping[str, Any]) -> list[str]:
    """Return fail-closed findings for broker-reported margin debt."""
    findings = []
    try:
        if balances.get("cashBalance") is not None and float(balances["cashBalance"]) < -0.01:
            findings.append("negative_broker_cash_balance")
    except (TypeError, ValueError):
        findings.append("invalid_broker_cash_balance")
    try:
        if balances.get("marginBalance") is not None and float(balances["marginBalance"]) > 0.01:
            findings.append("broker_margin_debit_detected")
    except (TypeError, ValueError):
        findings.append("invalid_broker_margin_balance")
    return findings


def configured_for_nh015() -> bool:
    """Require both the master arm and an exact strategy allowlist."""
    return (
        _truthy("LIVE_ORDER_PLACEMENT_ENABLED")
        and os.environ.get("LIVE_STRATEGY_ID", "").strip().upper()
        == STRATEGY_ID
    )


def _atomic_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True, default=str) + "\n"
    )
    os.replace(temporary, path)


def _market_day(now: datetime) -> str:
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    return now.astimezone(NY).date().isoformat()


@dataclass(frozen=True)
class Allocation:
    shares: int
    model_entry_price: float
    reserved_cost: float
    equity: float
    risk_shares: int
    position_shares: int
    cash_shares: int


class NH015LiveBook:
    """Durable virtual $5k book used only to size live NH015 orders."""

    def __init__(self, root: Path, now: datetime | None = None):
        self.root = Path(root)
        self.state_path = self.root / "nh015_live_allocation.json"
        self.audit_path = self.root / "nh015_live_audit.jsonl"
        self.history_path = self.root / "nh015_live_daily_history.json"
        self.state = self._load(now or datetime.now(timezone.utc))

    @staticmethod
    def _fresh(day: str, capital: float = STARTING_CASH) -> dict[str, Any]:
        return {
            "version": 2,
            "strategy_id": STRATEGY_ID,
            "market_day": day,
            "initial_capital": STARTING_CASH,
            "starting_cash": float(capital),
            "cash": float(capital),
            "deployed": 0.0,
            "realized_pnl": 0.0,
            "risk_halted": False,
            "risk_halt_reason": None,
            "active": {},
            "attempted": {},
        }

    def _load(self, now: datetime) -> dict[str, Any]:
        day = _market_day(now)
        carried_capital = STARTING_CASH
        try:
            value = json.loads(self.state_path.read_text())
            if (
                isinstance(value, dict)
                and value.get("version") in {1, 2}
                and value.get("strategy_id") == STRATEGY_ID
            ):
                if value.get("version") == 1:
                    value["version"] = 2
                    value.setdefault("initial_capital", STARTING_CASH)
                    value.setdefault("starting_cash", STARTING_CASH)
                    value.setdefault("risk_halted", False)
                    value.setdefault("risk_halt_reason", None)
                    self.state = value
                    self.checkpoint()
                if value.get("market_day") == day:
                    return value
                if value.get("active"):
                    value["rollover_blocked_for_day"] = day
                    return value
                self._archive(value)
                carried_capital = (
                    float(value.get("cash", 0.0))
                    + float(value.get("deployed", 0.0))
                )
        except (OSError, ValueError, TypeError):
            pass
        return self._fresh(day, carried_capital)

    def _archive(self, state: Mapping[str, Any]) -> None:
        day = str(state.get("market_day") or "")
        if not day:
            return
        try:
            history = json.loads(self.history_path.read_text())
            if not isinstance(history, dict):
                history = {}
        except (OSError, ValueError, TypeError):
            history = {}
        equity = float(state.get("cash", 0.0)) + float(state.get("deployed", 0.0))
        attempts = list((state.get("attempted") or {}).values())
        history[day] = {
            "strategy_id": STRATEGY_ID,
            "starting_cash": float(state.get("starting_cash", STARTING_CASH)),
            "end_equity": equity,
            "return_pct": (
                equity / float(state.get("starting_cash", STARTING_CASH)) - 1.0
            ) * 100.0,
            "total_return_pct": (equity / STARTING_CASH - 1.0) * 100.0,
            "realized_pnl": float(state.get("realized_pnl", 0.0)),
            "attempted": len(attempts),
            "submitted": sum(
                row.get("status") not in {
                    "ORDER_ATTEMPTED", "ENTRY_SUBMISSION_FAILED",
                }
                for row in attempts
            ),
            "closed": sum(row.get("status") == "CLOSED" for row in attempts),
            "unfilled": sum(
                row.get("status") == "ENTRY_UNFILLED" for row in attempts
            ),
        }
        _atomic_json(self.history_path, history)

    def _audit(self, event: str, **fields: Any) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        row = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event": event,
            "strategy_id": STRATEGY_ID,
            **fields,
        }
        with self.audit_path.open("a") as handle:
            handle.write(json.dumps(row, sort_keys=True, default=str) + "\n")
            handle.flush()
            os.fsync(handle.fileno())

    def checkpoint(self) -> None:
        _atomic_json(self.state_path, self.state)

    def rollover(self, now: datetime) -> bool:
        day = _market_day(now)
        if self.state.get("market_day") == day:
            return True
        if self.state.get("active"):
            self.state["rollover_blocked_for_day"] = day
            self.checkpoint()
            return False
        self._archive(self.state)
        carried_equity = self.equity
        self.state = self._fresh(day, carried_equity)
        self.checkpoint()
        self._audit("DAY_ROLLOVER", market_day=day, starting_cash=carried_equity)
        return True

    @property
    def equity(self) -> float:
        # This deliberately matches the simulator: open positions remain at
        # entry cost rather than being marked to market for new-trade sizing.
        return float(self.state["cash"]) + float(self.state["deployed"])

    def allocation(self, signal: Mapping[str, Any], now: datetime) -> tuple[Allocation | None, list[str]]:
        errors: list[str] = []
        if not self.rollover(now):
            errors.append("prior_day_position_still_active")
        if self.state.get("risk_halted"):
            errors.append("risk_halted_for_day")
        if str(signal.get("strategy_id") or "").upper() != STRATEGY_ID:
            errors.append("strategy_not_allowlisted")
        setup_id = str(signal.get("setup_id") or "")
        if not setup_id:
            errors.append("missing_setup_id")
        elif setup_id in self.state.get("attempted", {}):
            errors.append("setup_already_attempted")
        try:
            entry = float(signal["entry_price"])
            stop = float(signal["stop_price"])
        except (KeyError, TypeError, ValueError):
            entry = stop = 0.0
            errors.append("invalid_entry_or_stop")
        risk_per_share = abs(entry - stop)
        if entry <= 0 or stop <= 0 or risk_per_share <= 0:
            if "invalid_entry_or_stop" not in errors:
                errors.append("invalid_entry_or_stop")
        if errors:
            return None, errors

        equity = self.equity
        cash = float(self.state["cash"])
        risk_shares = math.floor(equity * RISK_FRACTION / risk_per_share)
        position_shares = math.floor(equity * MAX_POSITION_FRACTION / entry)
        cash_shares = math.floor(cash / entry)
        shares = min(risk_shares, position_shares, cash_shares)
        if shares < 1:
            return None, ["insufficient_virtual_capital"]
        allocation = Allocation(
            shares=shares,
            model_entry_price=entry,
            reserved_cost=shares * entry,
            equity=equity,
            risk_shares=risk_shares,
            position_shares=position_shares,
            cash_shares=cash_shares,
        )
        return allocation, []

    def mark_to_market_equity(
        self,
        positions: Mapping[str, Mapping[str, Any]],
        prices: Mapping[str, Any],
    ) -> float:
        """Estimate live equity consistently with the reservation ledger."""
        equity = float(self.state.get("cash", 0.0))
        by_setup = {
            str(pos.get("setup_id") or ""): pos
            for pos in positions.values()
        }
        for setup_id, active in self.state.get("active", {}).items():
            reserved = float(active.get("reserved_cost", 0.0))
            equity += reserved
            pos = by_setup.get(str(setup_id))
            if not pos or not pos.get("actual_entry_price"):
                continue
            symbol = str(pos.get("symbol") or active.get("symbol") or "").upper()
            current = prices.get(symbol)
            if current is None:
                continue
            quantity = float(pos.get("actual_qty") or pos.get("filled_qty") or pos.get("qty") or 0.0)
            equity += quantity * (float(current) - float(pos["actual_entry_price"]))
        return equity

    def halt(self, reason: str, **details: Any) -> bool:
        """Persist a risk halt; return True only for the first transition."""
        if self.state.get("risk_halted"):
            return False
        self.state["risk_halted"] = True
        self.state["risk_halt_reason"] = str(reason)
        self.state["risk_halted_at"] = datetime.now(timezone.utc).isoformat()
        self.checkpoint()
        self._audit("RISK_HALT", reason=reason, **details)
        return True

    def evaluate_daily_loss(
        self,
        positions: Mapping[str, Mapping[str, Any]],
        prices: Mapping[str, Any],
    ) -> tuple[bool, float]:
        equity = self.mark_to_market_equity(positions, prices)
        start = float(self.state.get("starting_cash", STARTING_CASH))
        loss_fraction = daily_loss_fraction()
        breached = (
            loss_fraction > 0
            and equity <= start * (1.0 - loss_fraction)
        )
        if breached:
            self.halt(
                "daily_loss_limit",
                estimated_equity=equity,
                day_starting_equity=start,
                loss_fraction=loss_fraction,
            )
        return bool(self.state.get("risk_halted")), equity

    def record_attempt(
        self,
        signal: Mapping[str, Any],
        allocation: Allocation,
        now: datetime,
    ) -> None:
        setup_id = str(signal["setup_id"])
        row = {
            "setup_id": setup_id,
            "symbol": str(signal["symbol"]).upper(),
            "attempted_at": now.isoformat(),
            "shares": allocation.shares,
            "model_entry_price": allocation.model_entry_price,
            "reserved_cost": allocation.reserved_cost,
            "status": "ORDER_ATTEMPTED",
        }
        self.state["attempted"][setup_id] = row
        self.checkpoint()
        self._audit("ORDER_ATTEMPT_RECORDED", allocation=row)

    def record_submission(self, setup_id: str, order_id: str) -> None:
        attempt = self.state["attempted"][setup_id]
        attempt.update({"status": "ENTRY_SUBMITTED", "order_id": str(order_id)})
        active = dict(attempt)
        self.state["active"][setup_id] = active
        self.state["cash"] = float(self.state["cash"]) - float(active["reserved_cost"])
        self.state["deployed"] = float(self.state["deployed"]) + float(active["reserved_cost"])
        self.checkpoint()
        self._audit("ENTRY_SUBMITTED", position=active)

    def record_submission_failure(self, setup_id: str, response: Any) -> None:
        attempt = self.state["attempted"].get(setup_id)
        if attempt is not None:
            attempt["status"] = "ENTRY_SUBMISSION_FAILED"
            attempt["response"] = response
        self.checkpoint()
        self._audit("ENTRY_SUBMISSION_FAILED", setup_id=setup_id, response=response)

    def release_unfilled(self, setup_id: str, reason: str) -> None:
        active = self.state["active"].pop(setup_id, None)
        if active is None:
            return
        reserved = float(active["reserved_cost"])
        self.state["cash"] = float(self.state["cash"]) + reserved
        self.state["deployed"] = float(self.state["deployed"]) - reserved
        self.state["attempted"][setup_id]["status"] = "ENTRY_UNFILLED"
        self.state["attempted"][setup_id]["release_reason"] = reason
        self.checkpoint()
        self._audit("ENTRY_UNFILLED", setup_id=setup_id, reason=reason)

    def close(self, setup_id: str, realized_pnl: float, exit_record: Mapping[str, Any]) -> None:
        active = self.state["active"].pop(setup_id, None)
        if active is None:
            self._audit("UNMATCHED_EXIT", setup_id=setup_id, exit=dict(exit_record))
            return
        reserved = float(active["reserved_cost"])
        pnl = float(realized_pnl)
        self.state["cash"] = float(self.state["cash"]) + reserved + pnl
        self.state["deployed"] = float(self.state["deployed"]) - reserved
        self.state["realized_pnl"] = float(self.state["realized_pnl"]) + pnl
        self.state["attempted"][setup_id]["status"] = "CLOSED"
        self.state["attempted"][setup_id]["realized_pnl"] = pnl
        self.checkpoint()
        self._audit(
            "POSITION_CLOSED",
            setup_id=setup_id,
            realized_pnl=pnl,
            end_equity=self.equity,
            exit=dict(exit_record),
        )

    def status(self) -> dict[str, Any]:
        return {
            **self.state,
            "equity": self.equity,
            "return_pct": (self.equity / STARTING_CASH - 1.0) * 100.0,
            "live_armed": configured_for_nh015(),
            "sizing": {
                "risk_fraction": RISK_FRACTION,
                "max_position_fraction": MAX_POSITION_FRACTION,
                "whole_shares": True,
            },
        }

    def publish_status(self) -> None:
        _atomic_json(self.root / "nh015_live_status.json", self.status())


def nh015_should_exit(position: dict[str, Any], price: float, now: datetime) -> bool:
    """Advance the live C2/15-second state and report an exit decision."""
    entry = float(position.get("actual_entry_price") or 0.0)
    if entry <= 0 or price <= 0:
        return False
    high = float(position.get("highest_price_since_fill") or entry)
    if price > high:
        position["highest_price_since_fill"] = price
        position["mfe_at"] = now.isoformat()
        high = price
    if not position.get("nh015_activated"):
        if price < entry * 1.003:
            return False
        position["nh015_activated"] = True
        position["nh015_activated_at"] = now.isoformat()
    high_at_raw = position.get("mfe_at") or position.get("entry_fill_time")
    try:
        high_at = datetime.fromisoformat(str(high_at_raw).replace("Z", "+00:00"))
        if high_at.tzinfo is None:
            high_at = high_at.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return False
    return (now - high_at).total_seconds() >= 15.0
