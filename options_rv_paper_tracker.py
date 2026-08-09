"""Paper ledger for defined-risk, multi-leg options structures."""
from __future__ import annotations

import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path


class OptionsRVTracker:
    def __init__(self, root="/data"):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.active_path = self.root / "options_rv_paper_active.json"
        self.outcome_path = self.root / "options_rv_paper_outcomes.jsonl"
        self.status_path = self.root / "options_rv_paper_status.json"
        self.commission = float(os.getenv("OPTIONS_RV_COMMISSION_PER_CONTRACT_SIDE", "0.65"))
        self.active = self._load()
        self.seen = set(self.active)
        self.completed = 0

    def _load(self):
        try:
            value = json.loads(self.active_path.read_text())
            return value if isinstance(value, dict) else {}
        except (OSError, ValueError, TypeError):
            return {}

    @staticmethod
    def _atomic(path, value):
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(value, separators=(",", ":")))
        tmp.replace(path)

    @staticmethod
    def _price(leg, opening):
        side = leg["side"]
        if opening:
            return float(leg["ask"] if side == "BUY" else leg["bid"])
        return float(leg["bid"] if side == "BUY" else leg["ask"])

    def _cash_flow(self, legs, opening):
        cash = 0.0
        contracts = 0
        for leg in legs:
            qty = int(leg.get("quantity", 1))
            if qty < 1 or qty > 2:
                raise ValueError("leg quantity must be one or two")
            px = self._price(leg, opening)
            if not math.isfinite(px) or px < 0:
                raise ValueError("invalid option price")
            cash += (1 if leg["side"] == "SELL" else -1) * px * 100 * qty
            contracts += qty
        cash -= self.commission * contracts
        return cash, contracts

    @staticmethod
    def _bounded(legs):
        buys = sum(int(x.get("quantity", 1)) for x in legs if x.get("side") == "BUY")
        sells = sum(int(x.get("quantity", 1)) for x in legs if x.get("side") == "SELL")
        return buys >= sells and buys > 0 and sells > 0

    def open(self, signal, now):
        key = str(signal["setup_id"])
        if key in self.seen or key in self.active:
            return False
        legs = [dict(x) for x in signal.get("legs", [])]
        if not 2 <= len(legs) <= 4 or not signal.get("defined_risk") or not self._bounded(legs):
            return False
        try:
            opening_cf, contracts = self._cash_flow(legs, True)
            max_loss = float(signal["max_loss_dollars"])
        except (KeyError, TypeError, ValueError):
            return False
        if not math.isfinite(max_loss) or max_loss <= 0 or max_loss + 1e-9 < max(0.0, -opening_cf):
            return False
        row = dict(signal)
        row.update({
            "opened_at": now.isoformat(), "opening_cash_flow": opening_cf,
            "max_loss_dollars": max_loss, "entry_contract_sides": contracts,
        })
        self.active[key] = row
        self.seen.add(key)
        self._save(now)
        return True

    def update(self, quotes, now):
        finished = []
        for key, row in list(self.active.items()):
            legs = []
            missing = False
            for old in row["legs"]:
                quote = quotes.get(old["symbol"])
                if not quote:
                    missing = True
                    break
                legs.append({**old, **quote})
            if missing:
                continue
            closing_cf, sides = self._cash_flow(legs, False)
            pnl = float(row["opening_cash_flow"]) + closing_cf
            ret = 100 * pnl / float(row["max_loss_dollars"])
            age = (now - datetime.fromisoformat(row["opened_at"])).total_seconds() / 60
            reason = None
            if ret >= float(row.get("target_return_pct", 20)):
                reason = "TARGET"
            elif ret <= -abs(float(row.get("stop_return_pct", 35))):
                reason = "STOP"
            elif age >= float(row.get("max_hold_minutes", 360)):
                reason = "TIMEOUT"
            if reason:
                out = {**row, "closed_at": now.isoformat(), "exit_reason": reason,
                       "closing_cash_flow": closing_cf, "pnl_dollars": pnl,
                       "return_on_max_risk_pct": ret, "exit_contract_sides": sides}
                with self.outcome_path.open("a") as handle:
                    handle.write(json.dumps(out, separators=(",", ":")) + "\n")
                finished.append(key)
                self.completed += 1
        for key in finished:
            self.active.pop(key, None)
        self._save(now)

    def _save(self, now=None):
        now = now or datetime.now(timezone.utc)
        self._atomic(self.active_path, self.active)
        self._atomic(self.status_path, {
            "updated_at": now.isoformat(), "active_groups": len(self.active),
            "completed_groups_this_process": self.completed, "seen_groups": len(self.seen),
            "commission_per_contract_side": self.commission,
            "exchange_regulatory_fees_included": False,
            "assignment_exercise_modeled": False, "early_assignment_modeled": False,
            "margin_model": "strategy_declared_defined_risk",
            "broker_execution_enabled": False,
            "pricing": "all BUY legs open@ask close@bid; SELL legs open@bid close@ask",
        })
