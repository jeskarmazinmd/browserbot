"""Opposite-direction, debit-only option control for directional strategies."""
from __future__ import annotations


def _opposite_contract(leg, contracts):
    wanted = "PUT" if leg.get("put_call") == "CALL" else "CALL"
    candidates = [
        c for c in contracts
        if c.get("putCall") == wanted
        and c.get("expirationDate") == leg.get("expiration")
        and float(c.get("bid") or 0) > 0
        and float(c.get("ask") or 0) >= float(c.get("bid") or 0)
    ]
    if not candidates:
        return None
    target_delta = abs(float(leg.get("delta") or 0.5))
    target_strike = float(leg.get("strike") or 0)
    return min(candidates, key=lambda c: (
        abs(float(c.get("strikePrice") or 0) - target_strike),
        abs(abs(float(c.get("delta") or 0)) - target_delta),
    ))


def _leg(contract, side):
    return {
        "symbol": contract["symbol"], "side": side,
        "bid": float(contract["bid"]), "ask": float(contract["ask"]),
        "multiplier": int(contract.get("multiplier") or 100),
        "strike": float(contract.get("strikePrice") or 0),
        "expiration": contract.get("expirationDate"),
        "put_call": contract.get("putCall"),
        "delta": contract.get("delta"),
    }


class InvertedStrategy:
    paper_only = True
    live_order_placement = False

    def __init__(self, original_cls, strategy_id):
        self._original = original_cls()
        self.name = strategy_id

    def evaluate(self, snapshot):
        result = []
        for original in self._original.evaluate(snapshot):
            legs = []
            original_legs = original.get("legs", [])
            vertical = len(original_legs) == 2
            for leg in original_legs:
                contract = _opposite_contract(leg, snapshot.get("contracts", []))
                if contract is None:
                    legs = []
                    break
                side = ({"BUY": "SELL", "SELL": "BUY"}[leg["side"]] if vertical else leg["side"])
                legs.append(_leg(contract, side))
            if not legs or len({leg["symbol"] for leg in legs}) != len(legs):
                continue
            decision = dict(original)
            decision["strategy_id"] = self.name
            decision["legs"] = legs
            decision["paper_only"] = True
            decision["live_order_placement"] = False
            research = dict(original.get("research") or {})
            research.update({"inversion_type": "opposite_option_direction", "control_strategy_id": original["strategy_id"]})
            decision["research"] = research
            result.append(decision)
        return result
