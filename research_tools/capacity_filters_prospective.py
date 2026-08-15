"""Prospective per-strategy capacity filters for the research paper bot.

The strategy modules remain unchanged. This layer limits only minute-strategy
signals forwarded to the paper outcome tracker. Rules beginning 2026-08-17
were generated from the exploratory 2026-08-11..14 sample and are hypotheses,
not evidence of a durable edge. Five percent of rejected signals are selected
deterministically for an audit control.
"""

from __future__ import annotations

import hashlib
from collections import defaultdict
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo


NY = ZoneInfo("America/New_York")
CAPACITY_FILTER_START_UTC = "2026-08-05T13:30:00+00:00"
_CAPACITY_FILTER_START = datetime.fromisoformat(CAPACITY_FILTER_START_UTC)
PROSPECTIVE_FILTER_START_UTC = "2026-08-17T13:30:00+00:00"


CAPACITY_FILTERS: dict[str, dict[str, Any]] = {
    "CV1": {"kind": "rank", "metric": "early_r2", "direction": "max", "limit": 1},
    "EMA1": {"kind": "rank", "metric": "latest_volume_ratio", "direction": "min", "limit": 1},
    "EMA2": {"kind": "max", "metric": "rebound_2m_pct", "value": 0.11},
    "GE1": {"kind": "rank", "metric": "exhaustion_rebound_from_low_pct", "direction": "min", "limit": 1},
    "GM1": {"kind": "min", "metric": "reversion_zscore", "value": -1.30},
    "GP1": {"kind": "min", "metric": "trend_up_minute_fraction", "value": 0.63},
    "GT1": {"kind": "band", "metric": "trend_slope_pct_per_hour", "low": 1.57, "high": 1.80},
    "M1": {"kind": "rank", "metric": "rebound_2m_pct", "direction": "min", "limit": 1},
    "M2": {"kind": "max", "metric": "largest_one_minute_decline_pct", "value": 0.74},
    "MC1": {"kind": "equals", "metric": "legacy_eligible", "value": True},
    "OR1": {"kind": "min", "metric": "opening_range_pct", "value": 2.20},
    "PD1": {"kind": "max", "metric": "rebound_from_low_pct", "value": 0.53},
    "RS1": {"kind": "max", "metric": "excess_return_30m_pct", "value": 0.76},
    "RS2": {"kind": "max", "metric": "excess_return_30m_pct", "value": 0.76},
    "RS3": {"kind": "rank", "metric": "return_30m_pct", "direction": "min", "limit": 1},
    "SH1": {"kind": "rank", "metric": "flattening_ratio", "direction": "max", "limit": 1},
    "TD1": {"kind": "max", "metric": "return_5m_pct", "value": 0.045},
    "TF1": {"kind": "max", "metric": "pullback_from_10m_high_pct", "value": 0.26},
    "TL1": {"kind": "max", "metric": "prior_gap_below_trendline_pct", "value": 0.28},
    "VE1": {"kind": "min", "metric": "compression_range_pct", "value": 0.565},
    "VR1": {"kind": "membership", "name": "HIGH_LIQUIDITY", "present": True},
    "VT1": {"kind": "max", "metric": "slope_45m_pct_per_hour", "value": 1.34},

    # Frozen v3 hypotheses. All inputs exist at the signal timestamp. Missing,
    # malformed, or future-stamped regime data fails open.
    "AV1": {
        "kind": "all",
        "rules": [
            {"kind": "max", "metric": "drawdown_15m_to_5m_low_pct", "value": 0.45626052},
            {"kind": "time_after", "minute_et": 843},
        ],
        "start_utc": PROSPECTIVE_FILTER_START_UTC,
        "audit_fraction": 0.05,
        "fail_open": True,
    },
    "BO1": {
        "kind": "min", "source": "regime", "metric": "dispersion.bottom10_avg",
        "value": -2.3494522, "start_utc": PROSPECTIVE_FILTER_START_UTC,
        "audit_fraction": 0.05, "fail_open": True,
    },
    "EMA3": {
        "kind": "min", "source": "regime", "metric": "dispersion.bottom10_avg",
        "value": -2.3431794, "start_utc": PROSPECTIVE_FILTER_START_UTC,
        "audit_fraction": 0.05, "fail_open": True,
    },
    "GR1": {
        "kind": "max", "metric": "rejection_confirmation_from_support_pct",
        "value": 0.12790698, "start_utc": PROSPECTIVE_FILTER_START_UTC,
        "audit_fraction": 0.05, "fail_open": True,
    },
    "GTMX": {
        "kind": "time_after", "minute_et": 910,
        "start_utc": PROSPECTIVE_FILTER_START_UTC,
        "audit_fraction": 0.05, "fail_open": True,
    },
    "HL1": {
        "kind": "max", "source": "regime", "metric": "dispersion.spread",
        "value": 4.6676321, "start_utc": PROSPECTIVE_FILTER_START_UTC,
        "audit_fraction": 0.05, "fail_open": True,
    },
    "QTD1X": {
        "kind": "min", "metric": "flash_drop_pct", "value": 1.9943335,
        "start_utc": PROSPECTIVE_FILTER_START_UTC,
        "audit_fraction": 0.05, "fail_open": True,
    },
    "SMA1": {
        "kind": "min", "source": "regime", "metric": "returns.SPY.5m",
        "value": 0.016728433, "start_utc": PROSPECTIVE_FILTER_START_UTC,
        "audit_fraction": 0.05, "fail_open": True,
    },
    "VWEMA1": {
        "kind": "min", "source": "regime", "metric": "dispersion.bottom10_avg",
        "value": -2.1868328, "start_utc": PROSPECTIVE_FILTER_START_UTC,
        "audit_fraction": 0.05, "fail_open": True,
    },

    "EMA1RR": {
        "kind": "max", "source": "regime",
        "metric": "breadth.red_pct_5m", "value": 36.08517,
        "start_utc": PROSPECTIVE_FILTER_START_UTC,
        "audit_fraction": 0.05, "fail_open": True,
    },
    "EMA1T50": {
        "kind": "max", "source": "regime",
        "metric": "breadth.red_pct_5m", "value": 36.08517,
        "start_utc": PROSPECTIVE_FILTER_START_UTC,
        "audit_fraction": 0.05, "fail_open": True,
    },
    "EMA1V15": {
        "kind": "max", "source": "regime",
        "metric": "breadth.red_pct_5m", "value": 36.08517,
        "start_utc": PROSPECTIVE_FILTER_START_UTC,
        "audit_fraction": 0.05, "fail_open": True,
    },
    "PTD1X": {
        "kind": "min", "metric": "pre_r2", "value": 0.67272675,
        "start_utc": PROSPECTIVE_FILTER_START_UTC,
        "audit_fraction": 0.05, "fail_open": False,
    },
}


def _timestamp(value: Any) -> datetime | None:
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def _nested(payload: dict[str, Any], path: str) -> Any:
    value: Any = payload
    for part in path.split("."):
        if not isinstance(value, dict) or part not in value:
            return None
        value = value[part]
    return value


def _number(payload: dict[str, Any], metric: str) -> float | None:
    try:
        return float(_nested(payload, metric))
    except (TypeError, ValueError):
        return None


def _metric(payload: dict[str, Any], regime: dict[str, Any] | None, rule: dict[str, Any]) -> float | None:
    if rule.get("source") != "regime":
        return _number(payload, rule["metric"])
    if not isinstance(regime, dict):
        return None
    signal_time = _timestamp(payload.get("timestamp"))
    regime_time = _timestamp(regime.get("timestamp"))
    if signal_time is None or regime_time is None or regime_time > signal_time:
        return None
    return _number(regime, rule["metric"])


def _passes(payload: dict[str, Any], rule: dict[str, Any], regime: dict[str, Any] | None) -> bool | None:
    kind = rule["kind"]
    if kind == "all":
        decisions = [_passes(payload, child, regime) for child in rule["rules"]]
        if any(decision is False for decision in decisions):
            return False
        return None if any(decision is None for decision in decisions) else True
    if kind == "time_after":
        timestamp = _timestamp(payload.get("timestamp"))
        if timestamp is None:
            return None
        local = timestamp.astimezone(NY)
        return local.hour * 60 + local.minute >= int(rule["minute_et"])
    if kind == "equals":
        return payload.get(rule["metric"]) == rule["value"]
    if kind == "membership":
        memberships = payload.get("universe_memberships") or []
        return (rule["name"] in memberships) is bool(rule["present"])

    value = _metric(payload, regime, rule)
    if value is None:
        return None
    if kind == "min":
        return value >= float(rule["value"])
    if kind == "max":
        return value <= float(rule["value"])
    if kind == "band":
        return float(rule["low"]) <= value <= float(rule["high"])
    raise ValueError(f"unsupported capacity filter kind: {kind}")


def _audit_selected(payload: dict[str, Any], fraction: float) -> bool:
    identity = str(payload.get("setup_id") or "|".join((
        str(payload.get("strategy_id", "")),
        str(payload.get("symbol", "")),
        str(payload.get("timestamp", "")),
    ))).encode("utf-8")
    bucket = int.from_bytes(hashlib.sha256(identity).digest()[:8], "big") / 2**64
    return bucket < fraction


def _marked(payload: dict[str, Any], *, passed: bool, audited: bool = False) -> dict[str, Any]:
    result = dict(payload)
    result["capacity_filter_passed"] = passed
    result["capacity_filter_audit"] = audited
    result["capacity_filter_version"] = "v3_frozen_20260817"
    return result


def apply_capacity_filters(
    payloads: list[dict[str, Any]],
    *,
    regime: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Apply prospective rules and retain a deterministic rejected control."""
    kept: list[dict[str, Any]] = []
    ranked: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for payload in payloads:
        timestamp = _timestamp(payload.get("timestamp"))
        if timestamp is None or timestamp < _CAPACITY_FILTER_START:
            kept.append(payload)
            continue
        strategy_id = str(payload.get("strategy_id", ""))
        rule = CAPACITY_FILTERS.get(strategy_id)
        if rule is None:
            kept.append(payload)
            continue
        rule_start = _timestamp(rule.get("start_utc"))
        if rule_start is not None and timestamp < rule_start:
            kept.append(payload)
            continue
        if rule["kind"] == "rank":
            if _number(payload, rule["metric"]) is not None:
                ranked[strategy_id].append(payload)
            continue

        decision = _passes(payload, rule, regime)
        if decision is True:
            kept.append(_marked(payload, passed=True) if "audit_fraction" in rule else payload)
        elif decision is None and rule.get("fail_open"):
            kept.append(_marked(payload, passed=True))
        elif _audit_selected(payload, float(rule.get("audit_fraction", 0.0))):
            kept.append(_marked(payload, passed=False, audited=True))

    for strategy_id, candidates in ranked.items():
        rule = CAPACITY_FILTERS[strategy_id]
        reverse = rule["direction"] == "max"
        candidates.sort(
            key=lambda payload: (
                _number(payload, rule["metric"]),
                str(payload.get("setup_id", "")),
            ),
            reverse=reverse,
        )
        kept.extend(candidates[: int(rule["limit"])])

    kept.sort(key=lambda payload: (
        str(payload.get("timestamp", "")),
        str(payload.get("strategy_id", "")),
        str(payload.get("symbol", "")),
    ))
    return kept
