from detectors.trend import detect_trend
from detectors.pullback import detect_pullback

STRATEGY_ID = "GP1"


def evaluate(ctx):
    trend = detect_trend(ctx.prices, window=30)
    pullback = detect_pullback(ctx.prices, trend_window=30)
    if not trend.get("detected") or not pullback.get("detected"):
        return None
    if trend["return_pct"] < 0.50 or trend["r2"] < 0.25:
        return None
    if not (0.20 <= pullback["pullback_depth_pct"] <= 1.50):
        return None
    if pullback["recovery_from_low_pct"] < 0.10:
        return None
    metrics = {**{f"trend_{k}": v for k, v in trend.items()}, **{f"pullback_{k}": v for k, v in pullback.items()}}
    return ctx.signal_factory(STRATEGY_ID, ctx.symbol, ctx.timestamp, ctx.current_price,
                              0.65, 0.65, "generic_trend_pullback", **metrics)
