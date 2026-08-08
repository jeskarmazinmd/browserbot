"""Conservative one-contract futures paper accounting.

No broker execution exists here.  Entries and exits cross the displayed spread,
and P&L uses the contract multiplier supplied by Schwab.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

COMMISSION_PER_CONTRACT_SIDE = 2.25


def _dt(value):
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc)
    return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(timezone.utc)


def _write_json(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, separators=(",", ":")) + "\n")
    tmp.replace(path)


class FuturesPaperTracker:
    """Persist and mark prospective futures decisions without placing orders."""

    def __init__(self, root="/data"):
        self.root = Path(root)
        self.ledger = self.root / "futures_paper_outcomes.jsonl"
        self.status_path = self.root / "futures_paper_status.json"
        self.active = {}
        self.completed = 0
        self.seen = set()
        self._restore()
        self._status()

    def _restore(self):
        if not self.ledger.exists():
            return
        try:
            for line in self.ledger.read_text(errors="replace").splitlines():
                try:
                    row = json.loads(line)
                except Exception:
                    continue
                key = row.get("group_id")
                if not key:
                    continue
                self.seen.add(key)
                if row.get("event") == "OPEN":
                    self.active[key] = row
                elif row.get("event") == "CLOSE":
                    self.active.pop(key, None)
                    self.completed += 1
        except OSError:
            pass

    def _append(self, row):
        self.ledger.parent.mkdir(parents=True, exist_ok=True)
        with self.ledger.open("a") as handle:
            handle.write(json.dumps(row, separators=(",", ":")) + "\n")

    def _status(self):
        _write_json(self.status_path, {
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "active_groups": len(self.active),
            "completed_groups": self.completed,
            "seen_groups": len(self.seen),
            "contracts_per_leg": 1,
            "commission_per_contract_side": COMMISSION_PER_CONTRACT_SIDE,
            "exchange_regulatory_fees_included": False,
            "broker_execution_enabled": False,
            "pricing": "LONG open@ask close@bid; SHORT open@bid close@ask",
        })

    def required_symbols(self):
        return sorted({leg["symbol"] for group in self.active.values() for leg in group["legs"]})

    def open_decisions(self, decisions):
        for decision in decisions:
            timestamp = _dt(decision["timestamp"])
            legs = []
            invalid = False
            for leg in decision.get("legs", []):
                bid = float(leg.get("bid") or 0)
                ask = float(leg.get("ask") or 0)
                multiplier = float(leg.get("multiplier") or 0)
                side = str(leg.get("side", "")).upper()
                if side not in {"LONG", "SHORT"} or bid <= 0 or ask < bid or multiplier <= 0:
                    invalid = True
                    break
                item = dict(leg)
                item["entry_price"] = ask if side == "LONG" else bid
                item["entry_commission"] = COMMISSION_PER_CONTRACT_SIDE
                legs.append(item)
            if invalid or not legs:
                continue
            raw_key = "|".join([decision["strategy_id"], timestamp.isoformat()] + [x["symbol"] + ":" + x["side"] for x in legs])
            if raw_key in self.seen:
                continue
            row = {
                "event": "OPEN",
                "group_id": raw_key,
                "strategy_id": decision["strategy_id"],
                "opened_at": timestamp.isoformat(),
                "legs": legs,
                "take_profit_dollars": float(decision["take_profit_dollars"]),
                "stop_loss_dollars": float(decision["stop_loss_dollars"]),
                "max_hold_minutes": int(decision["max_hold_minutes"]),
                "paper_only": True,
                "broker_execution_enabled": False,
            }
            self.active[raw_key] = row
            self.seen.add(raw_key)
            self._append(row)
        self._status()

    @staticmethod
    def _pnl(group, quotes):
        total = 0.0
        closes = []
        for leg in group["legs"]:
            q = quotes.get(leg["symbol"])
            if not q:
                return None, None
            bid = float(q.get("bid") or 0)
            ask = float(q.get("ask") or 0)
            if bid <= 0 or ask < bid:
                return None, None
            if leg["side"] == "LONG":
                close = bid
                gross = (close - leg["entry_price"]) * leg["multiplier"]
            else:
                close = ask
                gross = (leg["entry_price"] - close) * leg["multiplier"]
            net = gross - leg["entry_commission"] - COMMISSION_PER_CONTRACT_SIDE
            total += net
            closes.append({"symbol": leg["symbol"], "close_price": close, "gross_pnl_dollars": gross, "net_pnl_dollars": net})
        return total, closes

    def update(self, timestamp, exact_quotes):
        now = _dt(timestamp)
        closing = []
        for key, group in list(self.active.items()):
            pnl, closes = self._pnl(group, exact_quotes)
            if pnl is None:
                continue
            age_minutes = (now - _dt(group["opened_at"])).total_seconds() / 60
            reason = None
            if pnl >= group["take_profit_dollars"]:
                reason = "TARGET"
            elif pnl <= -group["stop_loss_dollars"]:
                reason = "STOP"
            elif age_minutes >= group["max_hold_minutes"]:
                reason = "TIMEOUT"
            if reason:
                closing.append((key, group, pnl, closes, reason))
        for key, group, pnl, closes, reason in closing:
            row = {
                "event": "CLOSE", "group_id": key, "strategy_id": group["strategy_id"],
                "opened_at": group["opened_at"], "closed_at": now.isoformat(), "reason": reason,
                "net_pnl_dollars": pnl, "legs": closes, "paper_only": True,
                "broker_execution_enabled": False,
            }
            self._append(row)
            self.active.pop(key, None)
            self.completed += 1
        self._status()
        return len(closing)
