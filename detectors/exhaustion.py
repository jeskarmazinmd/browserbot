import math
import numpy as np
from .common import clean_prices, return_pct


def detect_selling_exhaustion(values, window=12):
    prices = clean_prices(values)
    if len(prices) < window + 1:
        return {"detected": False, "reason": "insufficient_history"}
    sample = prices.tail(window + 1).reset_index(drop=True)
    returns = sample.pct_change().dropna() * 100.0
    half = len(returns) // 2
    early = returns.iloc[:half]
    late = returns.iloc[half:]
    early_abs = float(early.abs().mean()) if len(early) else math.nan
    late_abs = float(late.abs().mean()) if len(late) else math.nan
    contraction = 1.0 - late_abs / early_abs if early_abs > 0 else math.nan
    early_down = float((-early[early < 0]).mean()) if (early < 0).any() else 0.0
    late_down = float((-late[late < 0]).mean()) if (late < 0).any() else 0.0
    down_pressure_contraction = 1.0 - late_down / early_down if early_down > 0 else math.nan
    low = float(sample.min())
    current = float(sample.iloc[-1])
    decline = (float(sample.iloc[0]) - low) / float(sample.iloc[0]) * 100.0
    rebound = return_pct(low, current)
    score_parts = [x for x in (contraction, down_pressure_contraction, min(rebound / 0.30, 1.0)) if math.isfinite(x)]
    score = float(np.clip(np.mean(score_parts), 0.0, 1.0)) if score_parts else 0.0
    return {
        "detected": bool(decline > 0 and contraction > 0 and rebound > 0),
        "decline_to_low_pct": decline,
        "rebound_from_low_pct": rebound,
        "absolute_move_contraction": contraction,
        "down_pressure_contraction": down_pressure_contraction,
        "early_abs_return_pct": early_abs,
        "late_abs_return_pct": late_abs,
        "score": score,
    }
