from detectors.mean_reversion import detect_mean_reversion

STRATEGY_ID = "GM1"


def evaluate(ctx):
    d = detect_mean_reversion(ctx.prices, baseline_window=30, recent_window=5)
    if not d.get("detected"):
        return None
    if d["zscore"] > -1.25 or d["rebound_from_recent_low_pct"] < 0.10:
        return None
    return ctx.signal_factory(STRATEGY_ID, ctx.symbol, ctx.timestamp, ctx.current_price,
                              0.65, 0.80, "generic_mean_reversion", **{f"reversion_{k}": v for k, v in d.items()})
