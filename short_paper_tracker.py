"""Independent conservative paper accounting for short-only equity research."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

NY = ZoneInfo("America/New_York")


def _dt(value):
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc)
    return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(timezone.utc)


def _write_json(path, payload):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, separators=(",", ":")) + "\n")
    tmp.replace(path)


class ShortPaperTracker:
    def __init__(self, root="/data", notional=1000.0):
        self.root = Path(root)
        self.notional = float(notional)
        self.ledger = self.root / "short_paper_outcomes.jsonl"
        self.status_path = self.root / "short_paper_status.json"
        self.active = {}
        self.completed = 0
        self.seen = set()
        self._restore(); self._status()

    def _restore(self):
        if not self.ledger.exists(): return
        try:
            for line in self.ledger.read_text(errors="replace").splitlines():
                try: row = json.loads(line)
                except Exception: continue
                key = row.get("setup_id")
                if not key: continue
                self.seen.add(key)
                if row.get("event") == "OPEN": self.active[key] = row
                elif row.get("event") == "CLOSE": self.active.pop(key, None); self.completed += 1
        except OSError: pass

    def _append(self, row):
        self.ledger.parent.mkdir(parents=True, exist_ok=True)
        with self.ledger.open("a") as handle:
            handle.write(json.dumps(row, separators=(",", ":")) + "\n")

    def _status(self):
        _write_json(self.status_path, {
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "active": len(self.active), "completed": self.completed, "seen": len(self.seen),
            "notional_per_signal": self.notional,
            "online_equity_commission": 0.0,
            "borrow_fees_included": False,
            "short_locate_verified": False,
            "reg_sho_rule_201_modeled": False,
            "broker_execution_enabled": False,
            "pricing": "SHORT open@bid; buy-to-cover@ask; whole shares",
        })

    def open_decisions(self, decisions):
        for decision in decisions:
            if str(decision.get("side", "")).upper() != "SHORT": continue
            timestamp = _dt(decision["timestamp"])
            symbol = str(decision.get("symbol", "")).upper().strip()
            bid = float(decision.get("bid") or 0); ask = float(decision.get("ask") or 0)
            if not symbol or bid <= 0 or ask < bid: continue
            shares = int(self.notional / bid)
            if shares < 1: continue
            key = f'{decision["strategy_id"]}|{symbol}|{timestamp.replace(second=0, microsecond=0).isoformat()}'
            if key in self.seen: continue
            target_pct = float(decision["target_pct"]); stop_pct = float(decision["stop_pct"])
            row = {
                "event": "OPEN", "setup_id": key, "strategy_id": decision["strategy_id"],
                "symbol": symbol, "side": "SHORT", "opened_at": timestamp.isoformat(),
                "entry_price": bid, "entry_ask": ask, "shares": shares,
                "notional_used": shares * bid,
                "target_price": bid * (1 - target_pct / 100),
                "stop_price": bid * (1 + stop_pct / 100),
                "max_hold_minutes": int(decision["max_hold_minutes"]),
                "paper_only": True, "broker_execution_enabled": False,
            }
            self.active[key] = row; self.seen.add(key); self._append(row)
        self._status()

    def update(self, timestamp, quotes):
        now = _dt(timestamp); et = now.astimezone(NY)
        at_eod = (et.hour, et.minute) >= (15, 55)
        closing = []
        for key, row in list(self.active.items()):
            q = quotes.get(row["symbol"])
            if not q: continue
            ask = float(q.get("ask") or 0)
            if ask <= 0: continue
            age = (now - _dt(row["opened_at"])).total_seconds() / 60
            reason = None
            if ask <= row["target_price"]: reason = "TARGET"
            elif ask >= row["stop_price"]: reason = "STOP"
            elif at_eod: reason = "EOD"
            elif age >= row["max_hold_minutes"]: reason = "TIMEOUT"
            if reason: closing.append((key, row, ask, reason))
        for key, row, exit_ask, reason in closing:
            pnl = (row["entry_price"] - exit_ask) * row["shares"]
            ret = (row["entry_price"] - exit_ask) / row["entry_price"] * 100
            out = {
                "event": "CLOSE", "setup_id": key, "strategy_id": row["strategy_id"],
                "symbol": row["symbol"], "side": "SHORT", "opened_at": row["opened_at"],
                "closed_at": now.isoformat(), "entry_price": row["entry_price"],
                "exit_price": exit_ask, "shares": row["shares"], "exit_reason": reason,
                "return_pct": ret, "pnl": pnl,
                "borrow_fees_included": False, "short_locate_verified": False,
                "paper_only": True, "broker_execution_enabled": False,
            }
            self._append(out); self.active.pop(key, None); self.completed += 1
        self._status(); return len(closing)
