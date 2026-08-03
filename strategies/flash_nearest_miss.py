"""Pure per-strategy scoring for complete flash windows."""

import math


def score(measurement, strategy_id, config, min_pre_return, min_pre_slope, default_max_drop):
    rules = [
        ("pre_return_pct", "minimum", float(measurement["pre_return_pct"]), float(min_pre_return), "%"),
        ("pre_slope_pct_per_hour", "minimum", float(measurement["pre_slope_pct_per_hour"]), float(min_pre_slope), "%/hour"),
        ("flash_drop_pct", "minimum", float(measurement["flash_drop_pct"]), float(config["flash_drop_pct"]), "%"),
        ("flash_drop_pct", "maximum", float(measurement["flash_drop_pct"]), float(config.get("max_flash_drop_pct", default_max_drop)), "%"),
    ]
    if "min_pre_r2" in config:
        rules.append(("pre_r2", "minimum", float(measurement["pre_r2"]), float(config["min_pre_r2"]), ""))
    if "max_pre_slope_pct_per_hour" in config:
        rules.append(("pre_slope_pct_per_hour", "maximum", float(measurement["pre_slope_pct_per_hour"]), float(config["max_pre_slope_pct_per_hour"]), "%/hour"))

    failed_rules = []
    miss_score = 0.0
    for name, kind, observed, required, unit in rules:
        if not math.isfinite(observed):
            gap = None
            penalty = 10.0
        elif kind == "minimum":
            gap = max(0.0, required - observed)
            penalty = gap / max(abs(required), 1e-9)
        else:
            gap = max(0.0, observed - required)
            penalty = gap / max(abs(required), 1e-9)
        if gap == 0.0:
            continue
        failed_rules.append({
            "rule": name, "kind": kind, "observed": observed,
            "required": required, "shortfall": gap, "unit": unit,
        })
        miss_score += penalty

    if not failed_rules:
        return None
    failed_names = list(dict.fromkeys(rule["rule"] for rule in failed_rules))
    return {
        **measurement,
        "strategy_id": str(strategy_id),
        "miss_score": miss_score,
        "failed_rules": failed_rules,
        "failed": ",".join(failed_names),
        "gap": failed_rules[0].get("shortfall"),
    }
