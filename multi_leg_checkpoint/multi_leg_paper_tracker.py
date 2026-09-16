"""Durable paper accounting for coordinated multi-symbol strategy trades.

This tracker is intentionally separate from PaperOutcomeTracker.  A multi-leg
decision is one economic trade and must never be scored as unrelated legs.
It is research-only: there is no broker-order path in this module.
"""

from __future__ import annotations

import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo


NY = ZoneInfo("America/New_York")
VALID_SIDES = {"LONG": 1.0, "SHORT": -1.0}


def _utc(value):
    if isinstance(value, datetime):
        result = value
    else:
        result = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if result.tzinfo is None:
        result = result.replace(tzinfo=timezone.utc)
    return result.astimezone(timezone.utc)


def _positive(value):
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) and value > 0 else None


class MultiLegPaperTracker:
    """Track coordinated long/short groups using one group notional."""

    def __init__(
        self,
        data_root,
        *,
        group_notional=1000.0,
        eod_hour=15,
        eod_minute=55,
    ):
        self.root = Path(data_root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.ledger_path = self.root / "multi_leg_paper_outcomes.jsonl"
        self.state_path = self.root / "multi_leg_paper_active.json"
        self.status_path = self.root / "multi_leg_paper_status.json"
        self.group_notional = float(group_notional)
        self.eod_hour = int(eod_hour)
        self.eod_minute = int(eod_minute)
        self.active = {}
        self.seen = set()
        self.completed = 0
        self._recover()

    def _append(self, row):
        with self.ledger_path.open("a") as handle:
            handle.write(json.dumps(row, separators=(",", ":"), default=str) + "\n")

    @staticmethod
    def _atomic_json(path, value):
        temporary = path.with_name(path.name + ".tmp")
        with temporary.open("w") as handle:
            json.dump(value, handle, separators=(",", ":"), default=str)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)

    def _persist(self):
        self._atomic_json(
            self.state_path,
            {
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "active": list(self.active.values()),
            },
        )
        self._write_status()

    def _write_status(self):
        self._atomic_json(
            self.status_path,
            {
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "active_groups": len(self.active),
                "completed_groups": self.completed,
                "seen_groups": len(self.seen),
                "group_notional": self.group_notional,
                "broker_execution_enabled": False,
            },
        )

    def _recover(self):
        open_groups = {}
        if self.ledger_path.exists():
            with self.ledger_path.open(errors="replace") as handle:
                for line in handle:
                    try:
                        row = json.loads(line)
                    except (ValueError, TypeError):
                        continue
                    group_id = row.get("group_id")
                    if not group_id:
                        continue
                    self.seen.add(str(group_id))
                    if row.get("event_type") == "MULTI_LEG_ENTRY":
                        open_groups[str(group_id)] = row
                    elif row.get("event_type") == "MULTI_LEG_EXIT":
                        open_groups.pop(str(group_id), None)
                        self.completed += 1
        self.active = open_groups
        if self.state_path.exists():
            try:
                saved = json.loads(self.state_path.read_text()).get("active", [])
            except (OSError, ValueError, TypeError):
                saved = []
            for item in saved:
                group_id = str(item.get("group_id") or "")
                if group_id in self.active:
                    self.active[group_id].update(item)
        self._write_status()

    @staticmethod
    def _group_id(signal, timestamp):
        supplied = signal.get("group_id")
        if supplied:
            return str(supplied)
        minute = timestamp.replace(second=0, microsecond=0).isoformat()
        return f"{signal.get('strategy_id')}|{minute}"

    def register(self, signal):
        """Register a complete coordinated group atomically or reject it."""
        try:
            timestamp = _utc(signal.get("timestamp"))
        except (TypeError, ValueError):
            return False
        strategy_id = str(signal.get("strategy_id") or "").strip()
        raw_legs = signal.get("legs")
        if not strategy_id or not isinstance(raw_legs, list) or len(raw_legs) < 2:
            return False

        normalized = []
        symbols = set()
        total_weight = 0.0
        for leg in raw_legs:
            if not isinstance(leg, dict):
                return False
            symbol = str(leg.get("symbol") or "").strip().upper()
            side = str(leg.get("side") or "").strip().upper()
            entry = _positive(leg.get("entry_price"))
            weight = _positive(leg.get("weight"))
            if not symbol or symbol in symbols or side not in VALID_SIDES or not entry or not weight:
                return False
            symbols.add(symbol)
            total_weight += weight
            normalized.append({
                "symbol": symbol,
                "side": side,
                "entry_price": entry,
                "weight": weight,
            })
        if total_weight <= 0:
            return False

        for leg in normalized:
            leg["weight"] /= total_weight
            leg["notional"] = self.group_notional * leg["weight"]
            leg["last_price"] = leg["entry_price"]

        group_id = self._group_id(signal, timestamp)
        if group_id in self.seen:
            return False
        take_profit_pct = _positive(signal.get("take_profit_pct")) or 1.0
        stop_loss_pct = _positive(signal.get("stop_loss_pct")) or 1.0
        max_hold_minutes = _positive(signal.get("max_hold_minutes")) or 60.0
        record = {
            "event_type": "MULTI_LEG_ENTRY",
            "group_id": group_id,
            "strategy_id": strategy_id,
            "signal_timestamp": timestamp.isoformat(),
            "group_notional": self.group_notional,
            "legs": normalized,
            "take_profit_pct": take_profit_pct,
            "stop_loss_pct": stop_loss_pct,
            "max_hold_minutes": max_hold_minutes,
            "paper_only": True,
            "live_order_placement": False,
            "setup": signal.get("setup"),
            "research": signal.get("research", {}),
            "recorded_at": datetime.now(timezone.utc).isoformat(),
        }
        self._append(record)
        self.seen.add(group_id)
        self.active[group_id] = record
        self._persist()
        return True

    @staticmethod
    def _mark(record, prices):
        pnl = 0.0
        complete = True
        legs = []
        for leg in record["legs"]:
            item = dict(leg)
            price = _positive(prices.get(leg["symbol"]))
            if price is None:
                price = _positive(leg.get("last_price"))
                complete = False
            if price is None:
                return None, False, []
            item["last_price"] = price
            direction = VALID_SIDES[leg["side"]]
            leg_return = direction * (price / leg["entry_price"] - 1.0)
            leg_pnl = leg["notional"] * leg_return
            item["return_pct"] = leg_return * 100.0
            item["pnl"] = leg_pnl
            pnl += leg_pnl
            legs.append(item)
        return pnl, complete, legs

    def update(self, prices, now):
        """Mark every group and close it on group target/stop/time/EOD."""
        now = _utc(now)
        now_et = now.astimezone(NY)
        at_eod = (now_et.hour, now_et.minute) >= (self.eod_hour, self.eod_minute)
        closed = []
        changed = False
        for group_id, record in list(self.active.items()):
            pnl, complete, marked_legs = self._mark(record, prices)
            if pnl is None:
                continue
            record["legs"] = marked_legs
            record["mark_pnl"] = pnl
            record["mark_return_pct"] = pnl / record["group_notional"] * 100.0
            changed = True
            age_minutes = (now - _utc(record["signal_timestamp"])).total_seconds() / 60.0
            reason = None
            if record["mark_return_pct"] >= record["take_profit_pct"]:
                reason = "GROUP_TARGET"
            elif record["mark_return_pct"] <= -record["stop_loss_pct"]:
                reason = "GROUP_STOP"
            elif age_minutes >= record["max_hold_minutes"]:
                reason = "MAX_HOLD"
            elif at_eod:
                reason = "EOD"
            if reason is None:
                continue
            # A normal intraday close requires all current marks.  At EOD the
            # last observed mark is allowed so one absent quote cannot strand a
            # coordinated paper group overnight.
            if not complete and not at_eod:
                continue
            exit_row = {
                **record,
                "event_type": "MULTI_LEG_EXIT",
                "exit_timestamp": now.isoformat(),
                "exit_reason": reason,
                "pnl": pnl,
                "return_pct": pnl / record["group_notional"] * 100.0,
                "recorded_at": datetime.now(timezone.utc).isoformat(),
            }
            self._append(exit_row)
            closed.append(exit_row)
            del self.active[group_id]
            self.completed += 1
        if changed:
            self._persist()
        return closed
