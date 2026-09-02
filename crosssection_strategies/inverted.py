"""Paper-only side inversion for an existing cross-sectional strategy."""
from __future__ import annotations


class InvertedStrategy:
    paper_only = True
    live_order_placement = False

    def __init__(self, original_cls, strategy_id):
        self._original = original_cls()
        self.name = strategy_id

    def evaluate(self, snapshot):
        decisions = self._original.evaluate(snapshot)
        result = []
        for original in decisions:
            decision = dict(original)
            decision["strategy_id"] = self.name
            decision["side"] = "SHORT" if original["side"] == "LONG" else "LONG"
            decision["paper_only"] = True
            decision["live_order_placement"] = False
            research = dict(original.get("research") or {})
            research.update({"inversion_type": "side", "control_strategy_id": original["strategy_id"]})
            decision["research"] = research
            result.append(decision)
        return result
