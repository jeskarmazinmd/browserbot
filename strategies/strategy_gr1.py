from detectors.rejection import detect_support_rejection

STRATEGY_ID = "GR1"


def evaluate(ctx):
    d = detect_support_rejection(ctx.prices, window=20, tolerance_pct=0.20)
    if not d.get("detected"):
        return None
    if d["confirmation_from_support_pct"] < 0.12 or d["separation_bounce_pct"] < 0.15:
        return None
    stop_pct = max(0.35, min(1.00, d["confirmation_from_support_pct"] + 0.15))
    return ctx.signal_factory(STRATEGY_ID, ctx.symbol, ctx.timestamp, ctx.current_price,
                              0.60, stop_pct, "generic_support_rejection", **{f"rejection_{k}": v for k, v in d.items()})
