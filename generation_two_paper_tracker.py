"""Independent, prospective G2 portfolios using the established BA fill engine."""
import math
import json
import os

from executable_paper_engine import executable_mark
from generation_one_paper_tracker import GenerationOneBidAskTracker
from strategies import generation_two as flash

FILE_STEM = "paper_generation_two_bidask_independent"
IDS = flash.IDS
spec_for = flash.spec_for


class GenerationTwoBidAskTracker(GenerationOneBidAskTracker):
    IDS = IDS
    FILE_STEM = FILE_STEM
    flash_catalog = flash
    minute_catalog = None
    EXECUTION_MODEL = "GENERATION_TWO_BIDASK_V1"
    DEFER_ENTRY_CHECKPOINT = True

    def _append(self, row):
        # Every fill/rejection is durable before admission returns. Recovery
        # uses these rows for cash, quantities, deduplication and book usage.
        with self.ledger_path.open("a") as handle:
            handle.write(json.dumps(row, separators=(",", ":"), default=str) + "\n")
            handle.flush()
            os.fsync(handle.fileno())

    def _consume(self, key, identity, used, quantity):
        # The fill ledger is authoritative; avoid rewriting a growing book
        # diagnostic and whole active portfolio after every individual fill.
        self._liquidity[key] = {"identity": identity, "used": used + quantity}

    def _write_status(self):
        super()._write_status()
        if hasattr(self, "liquidity_path"):
            self._atomic_json(self.liquidity_path, self._liquidity)

    def entry_gate(self, signal, quote, now):
        # G2 spread gates require contemporaneous evidence for BOTH book sides.
        for action in ("BUY", "SELL"):
            mark = executable_mark(quote, action=action, now=now, max_quote_age_ms=5000)
            if mark["state"] != "EXECUTABLE":
                return mark["reason"]
        spec = self.spec_for(signal["strategy_id"])
        ask, bid = flash.num(quote["ask"]), flash.num(quote["bid"])
        spread = (ask / bid - 1) * 100
        target = flash.num(signal.get("target_price"))
        if spread > spec.max_entry_spread_pct:
            return "g2_spread_above_limit"
        if (target / ask - 1) * 100 < spec.min_executable_upside_pct:
            return "g2_insufficient_executable_upside"
        # Distance is a filter, never interpreted as an expected profit.
        if target - ask < spec.min_target_spread_multiple * (ask - bid):
            return "g2_target_distance_below_spread_multiple"
        if spec.one_position_per_symbol and any(
                row["strategy_id"] == spec.strategy_id and row["symbol"] == signal["symbol"]
                for row in self.active.values()):
            return "g2_symbol_already_open"
        return None

    def quantity_limit(self, sid, signal, ask, cash, requested):
        spec = self.spec_for(sid)
        if spec.portfolio_risk_fraction is None:
            return requested
        active = [row for row in self.active.values() if row["strategy_id"] == sid]
        equity = cash + sum(row["remaining_qty"] * row["entry_price"] for row in active)
        open_risk = sum(row["remaining_qty"] * max(0.0, row["entry_price"] - row["stop_price"])
                        for row in active)
        budget = max(0.0, equity * spec.portfolio_risk_fraction - open_risk)
        per_share = ask - flash.num(signal.get("stop_price"))
        return min(requested, math.floor(budget / per_share))
