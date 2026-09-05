"""Prospective, paper-only execution-policy family for NH015DUP signals.

Every policy sees the same source signal and executable quote. Immediate
policies cross the spread only when their limit and admission rules permit it.
Passive policies remain pending and require later ask-side evidence before a
fill is recorded. This module has no broker or trading-client dependency.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
import json
import math
import os
from pathlib import Path
from typing import Any, Mapping
from zoneinfo import ZoneInfo


SOURCE_STRATEGY_ID = "C3N25S10NH015DUP"
FAMILY_VERSION = "nh015_execution_family_v1_20260905"
NY = ZoneInfo("America/New_York")


@dataclass(frozen=True)
class Policy:
    strategy_id: str
    entry_mode: str = "IOC"
    buffer_fraction: float = 0.0
    max_spread_pct: float | None = None
    min_edge_spread_ratio: float | None = None
    passive_seconds: float = 30.0
    require_trade_through: bool = False
    no_new_high_seconds: float = 15.0


POLICIES = (
    Policy("C3N25S10NH015XBUF05", buffer_fraction=0.0005),
    Policy("C3N25S10NH015XBUF10", buffer_fraction=0.0010),
    Policy("C3N25S10NH015XSP05", max_spread_pct=0.05),
    Policy("C3N25S10NH015XSP10", max_spread_pct=0.10),
    Policy("C3N25S10NH015XEDGE3", min_edge_spread_ratio=3.0),
    Policy("C3N25S10NH015XMID", entry_mode="MIDPOINT"),
    Policy(
        "C3N25S10NH015XMIDTHRU",
        entry_mode="MIDPOINT",
        require_trade_through=True,
    ),
    Policy(
        "C3N25S10NH015XBIDTHRU",
        entry_mode="BID",
        require_trade_through=True,
    ),
    Policy("C3N25S10NH015XLONG60", no_new_high_seconds=60.0),
)
POLICY_BY_ID = {policy.strategy_id: policy for policy in POLICIES}


def _utc(value: Any) -> datetime:
    if isinstance(value, datetime):
        result = value
    else:
        result = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if result.tzinfo is None:
        result = result.replace(tzinfo=timezone.utc)
    return result.astimezone(timezone.utc)


def _positive(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) and result > 0 else None


def _spread_pct(bid: float, ask: float) -> float:
    midpoint = (bid + ask) / 2.0
    return ((ask - bid) / midpoint) * 100.0


class NH015ExecutionFamily:
    """Durable execution experiment with no order-placement capability."""

    def __init__(self, data_root: Path, *, eod_hour: int = 15, eod_minute: int = 55):
        self.root = Path(data_root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.ledger_path = self.root / "nh015_execution_family_outcomes.jsonl"
        self.state_path = self.root / "nh015_execution_family_active.json"
        self.status_path = self.root / "nh015_execution_family_status.json"
        self.eod_hour = int(eod_hour)
        self.eod_minute = int(eod_minute)
        self.pending: dict[str, dict[str, Any]] = {}
        self.active: dict[str, dict[str, Any]] = {}
        self.seen: set[str] = set()
        self.counts: dict[str, dict[str, int]] = {
            policy.strategy_id: {
                "pending": 0, "entries": 0, "skips": 0,
                "expired": 0, "exits": 0,
            }
            for policy in POLICIES
        }
        self._recover()

    @staticmethod
    def _key(policy: Policy, source_setup_id: str) -> str:
        return f"{policy.strategy_id}|{source_setup_id}"

    @staticmethod
    def _atomic_json(path: Path, value: Mapping[str, Any]) -> None:
        temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
        with temporary.open("w") as handle:
            json.dump(value, handle, separators=(",", ":"), default=str)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)

    def _append(self, row: Mapping[str, Any]) -> None:
        with self.ledger_path.open("a") as handle:
            handle.write(json.dumps(row, separators=(",", ":"), default=str) + "\n")

    def _persist(self) -> None:
        self._atomic_json(
            self.state_path,
            {
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "pending": list(self.pending.values()),
                "active": list(self.active.values()),
            },
        )
        self._write_status()

    def _write_status(self) -> None:
        self._atomic_json(
            self.status_path,
            {
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "family_version": FAMILY_VERSION,
                "source_strategy_id": SOURCE_STRATEGY_ID,
                "paper_only": True,
                "broker_execution_enabled": False,
                "policies": [asdict(policy) for policy in POLICIES],
                "pending": len(self.pending),
                "active": len(self.active),
                "seen": len(self.seen),
                "counts": self.counts,
            },
        )

    def _recover(self) -> None:
        if self.ledger_path.exists():
            with self.ledger_path.open(errors="replace") as handle:
                for line in handle:
                    try:
                        row = json.loads(line)
                    except (TypeError, ValueError):
                        continue
                    key = row.get("setup_id")
                    strategy_id = row.get("strategy_id")
                    if not key or strategy_id not in POLICY_BY_ID:
                        continue
                    self.seen.add(key)
                    event = row.get("event_type")
                    if event == "FAMILY_PENDING":
                        self.pending[key] = dict(row)
                        self.counts[strategy_id]["pending"] += 1
                    elif event == "FAMILY_ENTRY":
                        self.pending.pop(key, None)
                        self.active[key] = dict(row)
                        self.counts[strategy_id]["entries"] += 1
                    elif event == "FAMILY_SKIP":
                        self.pending.pop(key, None)
                        self.counts[strategy_id]["skips"] += 1
                    elif event == "FAMILY_EXPIRE":
                        self.pending.pop(key, None)
                        self.counts[strategy_id]["expired"] += 1
                    elif event == "FAMILY_EXIT":
                        self.active.pop(key, None)
                        self.counts[strategy_id]["exits"] += 1

        if self.state_path.exists():
            try:
                saved = json.loads(self.state_path.read_text())
            except (OSError, TypeError, ValueError):
                saved = {}
            for record in saved.get("pending", []):
                key = record.get("setup_id")
                if key in self.pending:
                    self.pending[key].update(record)
            for record in saved.get("active", []):
                key = record.get("setup_id")
                if key in self.active:
                    self.active[key].update(record)
        self._write_status()

    def symbols(self) -> set[str]:
        return {
            str(record["symbol"]).upper()
            for record in (*self.pending.values(), *self.active.values())
            if record.get("symbol")
        }

    def register(
        self,
        signal: Mapping[str, Any],
        quote: Mapping[str, Any] | None,
        now: datetime | None = None,
    ) -> list[dict[str, Any]]:
        """Evaluate all fixed policies for one source signal."""
        if str(signal.get("strategy_id") or "") != SOURCE_STRATEGY_ID:
            return []
        try:
            timestamp = _utc(now or signal.get("timestamp"))
        except (TypeError, ValueError):
            return []
        symbol = str(signal.get("symbol") or "").strip().upper()
        source_setup_id = str(signal.get("setup_id") or "")
        model_entry = _positive(signal.get("entry_price"))
        target = _positive(signal.get("target_price"))
        stop = _positive(signal.get("stop_price"))
        if not symbol or not source_setup_id or None in (model_entry, target, stop):
            return []

        bid = _positive((quote or {}).get("bid"))
        ask = _positive((quote or {}).get("ask"))
        valid_quote = bid is not None and ask is not None and ask >= bid
        spread = _spread_pct(bid, ask) if valid_quote else None
        edge_pct = ((target / model_entry) - 1.0) * 100.0
        emitted = []

        for policy in POLICIES:
            key = self._key(policy, source_setup_id)
            if key in self.seen:
                continue
            self.seen.add(key)
            common = {
                "recorded_at": datetime.now(timezone.utc).isoformat(),
                "setup_id": key,
                "strategy_id": policy.strategy_id,
                "family_version": FAMILY_VERSION,
                "source_strategy_id": SOURCE_STRATEGY_ID,
                "source_setup_id": source_setup_id,
                "symbol": symbol,
                "signal_timestamp": timestamp.isoformat(),
                "model_entry_price": model_entry,
                "target_price": target,
                "stop_price": stop,
                "signal_edge_pct": edge_pct,
                "entry_bid_observed": bid,
                "entry_ask_observed": ask,
                "entry_spread_pct": spread,
                "paper_only": True,
                "broker_execution_enabled": False,
                "policy": asdict(policy),
            }
            reason = None
            if not valid_quote:
                reason = "NO_EXECUTABLE_QUOTE"
            elif policy.max_spread_pct is not None and spread > policy.max_spread_pct:
                reason = "SPREAD_ABOVE_CAP"
            elif (
                policy.min_edge_spread_ratio is not None
                and (spread <= 0 or edge_pct / spread < policy.min_edge_spread_ratio)
            ):
                reason = "EDGE_SPREAD_RATIO_BELOW_MINIMUM"

            if reason:
                row = {**common, "event_type": "FAMILY_SKIP", "reason": reason}
                self._append(row)
                self.counts[policy.strategy_id]["skips"] += 1
                emitted.append(row)
                continue

            if policy.entry_mode == "IOC":
                limit = round(model_entry * (1.0 + policy.buffer_fraction), 2)
                if ask > limit:
                    row = {
                        **common, "event_type": "FAMILY_SKIP",
                        "limit_price": limit, "reason": "ASK_ABOVE_LIMIT",
                    }
                    self._append(row)
                    self.counts[policy.strategy_id]["skips"] += 1
                else:
                    row = self._entry(common, policy, ask, bid, timestamp, limit)
                    self.active[key] = row
                    self._append(row)
                    self.counts[policy.strategy_id]["entries"] += 1
                emitted.append(row)
                continue

            limit = round((bid + ask) / 2.0, 2) if policy.entry_mode == "MIDPOINT" else bid
            row = {
                **common,
                "event_type": "FAMILY_PENDING",
                "limit_price": limit,
                "placed_at": timestamp.isoformat(),
                "expires_at": (timestamp + timedelta(seconds=policy.passive_seconds)).isoformat(),
            }
            self.pending[key] = row
            self._append(row)
            self.counts[policy.strategy_id]["pending"] += 1
            emitted.append(row)

        self._persist()
        return emitted

    @staticmethod
    def _entry(
        common: Mapping[str, Any], policy: Policy, price: float,
        initial_bid: float, timestamp: datetime, limit: float,
    ) -> dict[str, Any]:
        return {
            **common,
            "event_type": "FAMILY_ENTRY",
            "entry_timestamp": timestamp.isoformat(),
            "entry_price": price,
            "actual_entry_price": price,
            "limit_price": limit,
            "no_new_high_seconds": policy.no_new_high_seconds,
            "nh015_activated": False,
            "nh015_highest_bid": initial_bid,
            "nh015_high_bid_at": None,
            "entry_fill_time": timestamp.isoformat(),
            "last_bid": price,
            "last_bid_at": timestamp.isoformat(),
        }

    @staticmethod
    def _dynamic_exit(record: dict[str, Any], bid: float, now: datetime) -> bool:
        entry = float(record["entry_price"])
        high = float(record.get("nh015_highest_bid") or entry)
        if bid > high:
            record["nh015_highest_bid"] = bid
            record["nh015_high_bid_at"] = now.isoformat()
        if not record.get("nh015_activated"):
            if bid < entry * 1.003:
                return False
            record["nh015_activated"] = True
            record["nh015_activated_at"] = now.isoformat()
            if not record.get("nh015_high_bid_at"):
                record["nh015_highest_bid"] = max(high, bid)
                record["nh015_high_bid_at"] = now.isoformat()
        try:
            high_at = _utc(record["nh015_high_bid_at"])
        except (TypeError, ValueError):
            return False
        return (now - high_at).total_seconds() >= float(record["no_new_high_seconds"])

    def update(
        self, quotes: Mapping[str, Mapping[str, Any]], now: datetime
    ) -> list[dict[str, Any]]:
        """Advance pending orders and active paper positions from fresh NBBO."""
        now = _utc(now)
        now_et = now.astimezone(NY)
        at_eod = (now_et.hour, now_et.minute) >= (self.eod_hour, self.eod_minute)
        emitted = []
        changed = False

        for key, record in list(self.pending.items()):
            policy = POLICY_BY_ID[record["strategy_id"]]
            quote = quotes.get(str(record["symbol"]).upper()) or {}
            bid = _positive(quote.get("bid"))
            ask = _positive(quote.get("ask"))
            valid = bid is not None and ask is not None and ask >= bid
            expired = now >= _utc(record["expires_at"]) or at_eod
            limit = float(record["limit_price"])
            fillable = valid and (ask < limit if policy.require_trade_through else ask <= limit)
            if fillable:
                entry = self._entry(record, policy, ask, bid, now, limit)
                entry["passive_wait_seconds"] = (now - _utc(record["placed_at"])).total_seconds()
                self._append(entry)
                self.active[key] = entry
                del self.pending[key]
                self.counts[policy.strategy_id]["entries"] += 1
                emitted.append(entry)
                changed = True
            elif expired:
                row = {
                    **record, "event_type": "FAMILY_EXPIRE",
                    "recorded_at": datetime.now(timezone.utc).isoformat(),
                    "expired_at": now.isoformat(), "reason": "PASSIVE_NOT_FILLED",
                    "last_bid": bid, "last_ask": ask,
                }
                self._append(row)
                del self.pending[key]
                self.counts[policy.strategy_id]["expired"] += 1
                emitted.append(row)
                changed = True

        for key, record in list(self.active.items()):
            quote = quotes.get(str(record["symbol"]).upper()) or {}
            bid = _positive(quote.get("bid"))
            signal_day = _utc(record["signal_timestamp"]).astimezone(NY).date()
            if bid is None:
                if not (at_eod or now_et.date() > signal_day):
                    continue
                bid = _positive(record.get("last_bid"))
                if bid is None:
                    continue
            else:
                record["last_bid"] = bid
                record["last_bid_at"] = now.isoformat()
                changed = True

            if bid <= float(record["stop_price"]):
                reason = "STOP"
            elif bid >= float(record["target_price"]):
                reason = "TARGET"
            elif now_et.date() > signal_day or at_eod:
                reason = "EOD"
            elif self._dynamic_exit(record, bid, now):
                reason = "NO_NEW_HIGH"
            else:
                continue
            row = {
                **record,
                "event_type": "FAMILY_EXIT",
                "recorded_at": datetime.now(timezone.utc).isoformat(),
                "exit_timestamp": now.isoformat(),
                "exit_price": bid,
                "exit_bid": bid,
                "exit_reason": reason,
                "return_pct": (bid / float(record["entry_price"]) - 1.0) * 100.0,
            }
            self._append(row)
            del self.active[key]
            self.counts[record["strategy_id"]]["exits"] += 1
            emitted.append(row)
            changed = True

        if changed:
            self._persist()
        return emitted
