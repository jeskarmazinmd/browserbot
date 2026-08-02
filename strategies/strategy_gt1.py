from detectors.trend import detect_trend

STRATEGY_ID = "GT1"


def evaluate(ctx):
    d = detect_trend(ctx.prices, window=30)
    if not d.get("detected"):
        return None
    if d["return_pct"] < 0.60 or d["r2"] < 0.35 or d["up_minute_fraction"] < 0.52:
        return None
    return ctx.signal_factory(STRATEGY_ID, ctx.symbol, ctx.timestamp, ctx.current_price,
                              0.70, 0.70, "generic_trend_continuation", **{f"trend_{k}": v for k, v in d.items()})
