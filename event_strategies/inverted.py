"""Paper-only side inversion for an existing event strategy."""
from __future__ import annotations


class InvertedStrategy:
    paper_only = True
    live_order_placement = False

    def __init__(self, original_cls, strategy_id):
        self._original = original_cls()
        self.name = strategy_id

    def evaluate(self, event, quote):
        result = []
        for original in self._original.evaluate(event, quote):
            decision = dict(original)
            decision["strategy_id"] = self.name
            decision["side"] = "SHORT" if original["side"] == "LONG" else "LONG"
            decision["paper_only"] = True
            decision["live_order_placement"] = False
            decision["inversion_type"] = "reaction_fade"
            decision["control_strategy_id"] = original["strategy_id"]
            result.append(decision)
        return result
