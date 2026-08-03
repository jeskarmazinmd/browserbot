"""Shared bounded nearest-miss scoring for snapshot strategies."""

from __future__ import annotations

import math


def minimum(name, observed, required, unit=""):
    return {"rule": name, "kind": "minimum", "observed": observed, "required": required, "unit": unit}


def maximum(name, observed, required, unit=""):
    return {"rule": name, "kind": "maximum", "observed": observed, "required": required, "unit": unit}


def boolean(name, observed):
    return {"rule": name, "kind": "boolean", "observed": bool(observed), "required": True, "unit": ""}


def between(name, observed, lower, upper, unit=""):
    return {"rule": name, "kind": "between", "observed": observed, "required": [lower, upper], "unit": unit}


def _evaluate(rule):
    kind = rule["kind"]
    observed = rule["observed"]
    try:
        if kind == "boolean":
            passed = bool(observed)
            return passed, 0.0 if passed else 1.0, False if passed else True
        value = float(observed)
        if not math.isfinite(value):
            return False, 10.0, None
        if kind == "minimum":
            required = float(rule["required"])
            shortfall = max(0.0, required - value)
            return shortfall == 0, shortfall / max(abs(required), 1e-9), shortfall
        if kind == "maximum":
            required = float(rule["required"])
            excess = max(0.0, value - required)
            return excess == 0, excess / max(abs(required), 1e-9), excess
        lower, upper = map(float, rule["required"])
        if value < lower:
            gap = lower - value
            return False, gap / max(abs(lower), 1e-9), gap
        if value > upper:
            gap = value - upper
            return False, gap / max(abs(upper), 1e-9), gap
        return True, 0.0, 0.0
    except (TypeError, ValueError):
        return False, 10.0, None


def consider(strategy, symbol, timestamp, price, rules, metrics=None):
    """Retain the closest rejected candidate on ``strategy.nearest_miss``."""
    failed = []
    score = 0.0
    for source in rules:
        rule = dict(source)
        passed, penalty, gap = _evaluate(rule)
        if passed:
            continue
        rule["shortfall"] = gap
        failed.append(rule)
        score += penalty
    if not failed:
        return False
    candidate = {
        "symbol": str(symbol),
        "timestamp": str(timestamp),
        "price": float(price),
        "miss_score": float(score),
        "failed_rules": failed,
        "metrics": dict(metrics or {}),
    }
    current = getattr(strategy, "nearest_miss", None)
    if current is None or candidate["miss_score"] < float(current.get("miss_score", math.inf)):
        strategy.nearest_miss = candidate
    return True


def reset(strategy):
    strategy.nearest_miss = None
