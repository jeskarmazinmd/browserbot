from detectors.exhaustion import detect_selling_exhaustion

STRATEGY_ID = "GE1"


def evaluate(ctx):
    d = detect_selling_exhaustion(ctx.prices, window=12)
    if not d.get("detected"):
        return None
    if d["decline_to_low_pct"] < 0.60 or d["rebound_from_low_pct"] < 0.10 or d["score"] < 0.35:
        return None
    return ctx.signal_factory(STRATEGY_ID, ctx.symbol, ctx.timestamp, ctx.current_price,
                              0.60, 0.75, "generic_selling_exhaustion", **{f"exhaustion_{k}": v for k, v in d.items()})
