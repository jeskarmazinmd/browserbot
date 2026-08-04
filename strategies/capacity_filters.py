"""Prospective per-strategy capacity filters for a small research account.

The underlying strategy modules remain unchanged.  This layer limits only the
minute-strategy signals forwarded to the paper outcome tracker.  Rules were
selected from the 2026-08-04 research sample and therefore require prospective
validation; they are not evidence of a durable trading edge.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Any


CAPACITY_FILTER_START_UTC = "2026-08-05T13:30:00+00:00"
_CAPACITY_FILTER_START = datetime.fromisoformat(CAPACITY_FILTER_START_UTC)


# Exactly one selection rule per strategy. Strategies for which no one-rule
# improvement survived the $10k/ten-slot screen are intentionally absent.
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
    "VT1": {"kind": "min", "metric": "slope_45m_pct_per_hour", "value": 1.34},
}


def _number(payload: dict[str, Any], metric: str) -> float | None:
    try:
        return float(payload[metric])
    except (KeyError, TypeError, ValueError):
        return None


def _passes(payload: dict[str, Any], rule: dict[str, Any]) -> bool:
    kind = rule["kind"]
    if kind == "equals":
        return payload.get(rule["metric"]) == rule["value"]
    if kind == "membership":
        memberships = payload.get("universe_memberships") or []
        return (rule["name"] in memberships) is bool(rule["present"])

    value = _number(payload, rule["metric"])
    if value is None:
        return False
    if kind == "min":
        return value >= float(rule["value"])
    if kind == "max":
        return value <= float(rule["value"])
    if kind == "band":
        return float(rule["low"]) <= value <= float(rule["high"])
    raise ValueError(f"unsupported capacity filter kind: {kind}")


def apply_capacity_filters(payloads: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Apply one prospective rule per configured strategy to one snapshot."""
    kept: list[dict[str, Any]] = []
    ranked: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for payload in payloads:
        try:
            timestamp = datetime.fromisoformat(
                str(payload.get("timestamp", "")).replace("Z", "+00:00")
            )
        except ValueError:
            timestamp = None
        if timestamp is None or timestamp < _CAPACITY_FILTER_START:
            kept.append(payload)
            continue
        strategy_id = str(payload.get("strategy_id", ""))
        rule = CAPACITY_FILTERS.get(strategy_id)
        if rule is None:
            kept.append(payload)
        elif rule["kind"] == "rank":
            if _number(payload, rule["metric"]) is not None:
                ranked[strategy_id].append(payload)
        elif _passes(payload, rule):
            kept.append(payload)

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

    kept.sort(
        key=lambda payload: (
            str(payload.get("timestamp", "")),
            str(payload.get("strategy_id", "")),
            str(payload.get("symbol", "")),
        )
    )
    return kept
