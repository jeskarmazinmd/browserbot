"""Conservative prospective spot-FX paper accounting."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

MINI_LOT_UNITS = 10_000


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


class ForexPaperTracker:
    """Track one-mini-lot-per-leg FX decisions; never submits an order."""

    def __init__(self, root="/data"):
        self.root = Path(root)
        self.ledger = self.root / "forex_paper_outcomes.jsonl"
        self.status_path = self.root / "forex_paper_status.json"
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
            "active_groups": len(self.active), "completed_groups": self.completed,
            "seen_groups": len(self.seen), "units_per_leg": MINI_LOT_UNITS,
            "online_commission_per_trade": 0.0,
            "financing_swap_included": False,
            "broker_execution_enabled": False,
            "pricing": "LONG open@ask close@bid; SHORT open@bid close@ask",
        })

    def open_decisions(self, decisions):
        for decision in decisions:
            timestamp = _dt(decision["timestamp"])
            legs = []
            invalid = False
            for leg in decision.get("legs", []):
                symbol = str(leg.get("symbol", "")).upper()
                bid = float(leg.get("bid") or 0)
                ask = float(leg.get("ask") or 0)
                units = int(leg.get("units") or 0)
                side = str(leg.get("side", "")).upper()
                # USD-base and USD-quote pairs have an exact conversion path
                # back to account dollars using this same market quote.
                supported = symbol.startswith("USD/") or symbol.endswith("/USD")
                if not supported or side not in {"LONG", "SHORT"} or bid <= 0 or ask < bid or units != MINI_LOT_UNITS:
                    invalid = True
                    break
                item = dict(leg)
                item["symbol"] = symbol
                item["entry_price"] = ask if side == "LONG" else bid
                legs.append(item)
            if invalid or not legs:
                continue
            key = "|".join([decision["strategy_id"], timestamp.isoformat()] + [x["symbol"] + ":" + x["side"] for x in legs])
            if key in self.seen:
                continue
            row = {
                "event": "OPEN", "group_id": key, "strategy_id": decision["strategy_id"],
                "opened_at": timestamp.isoformat(), "legs": legs,
                "take_profit_dollars": float(decision["take_profit_dollars"]),
                "stop_loss_dollars": float(decision["stop_loss_dollars"]),
                "max_hold_minutes": int(decision["max_hold_minutes"]),
                "paper_only": True, "broker_execution_enabled": False,
            }
            self.active[key] = row
            self.seen.add(key)
            self._append(row)
        self._status()

    @staticmethod
    def _leg_pnl_usd(leg, q):
        bid = float(q.get("bid") or 0)
        ask = float(q.get("ask") or 0)
        if bid <= 0 or ask < bid:
            return None, None, None
        close = bid if leg["side"] == "LONG" else ask
        direction = 1 if leg["side"] == "LONG" else -1
        quote_currency_pnl = (close - float(leg["entry_price"])) * int(leg["units"]) * direction
        symbol = leg["symbol"]
        if symbol.endswith("/USD"):
            usd_pnl = quote_currency_pnl
        elif symbol.startswith("USD/"):
            usd_pnl = quote_currency_pnl / close
        else:
            return None, None, None
        return usd_pnl, close, quote_currency_pnl

    @classmethod
    def _pnl(cls, group, quotes):
        total = 0.0
        closes = []
        for leg in group["legs"]:
            q = quotes.get(leg["symbol"])
            if not q:
                return None, None
            pnl, close, quote_pnl = cls._leg_pnl_usd(leg, q)
            if pnl is None:
                return None, None
            total += pnl
            closes.append({"symbol": leg["symbol"], "close_price": close, "quote_currency_pnl": quote_pnl, "net_pnl_dollars": pnl})
        return total, closes

    def update(self, timestamp, quotes):
        now = _dt(timestamp)
        closing = []
        for key, group in list(self.active.items()):
            pnl, closes = self._pnl(group, quotes)
            if pnl is None:
                continue
            age = (now - _dt(group["opened_at"])).total_seconds() / 60
            reason = None
            if pnl >= group["take_profit_dollars"]:
                reason = "TARGET"
            elif pnl <= -group["stop_loss_dollars"]:
                reason = "STOP"
            elif age >= group["max_hold_minutes"]:
                reason = "TIMEOUT"
            if reason:
                closing.append((key, group, pnl, closes, reason))
        for key, group, pnl, closes, reason in closing:
            row = {
                "event": "CLOSE", "group_id": key, "strategy_id": group["strategy_id"],
                "opened_at": group["opened_at"], "closed_at": now.isoformat(), "reason": reason,
                "net_pnl_dollars": pnl, "legs": closes,
                "financing_swap_included": False, "paper_only": True,
                "broker_execution_enabled": False,
            }
            self._append(row)
            self.active.pop(key, None)
            self.completed += 1
        self._status()
        return len(closing)
