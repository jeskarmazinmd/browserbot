"""Prospective, paper-only market-regime gates for C3N25S10.

Each arm receives the canonical parent entry and either mirrors it unchanged
or refrains. Inputs end one full minute before entry. Round thresholds are
pre-registered research hypotheses, not values fitted to bot outcomes.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

import pandas as pd

PARENT_STRATEGY_ID = "C3N25S10"
FORWARD_START_UTC = "2026-09-02T13:30:00+00:00"
FAMILY_VERSION = "c3_market_gate_v2_20260902"
MIN_BREADTH_SYMBOLS = 50
LOOKBACKS = (5, 15)
INDEX_SYMBOLS = {"SPY", "QQQ", "IWM"}


def _rule(feature, op, threshold, hypothesis):
    return {"feature": feature, "op": op, "threshold": threshold,
            "hypothesis": hypothesis}


# The original five IDs and thresholds are retained unchanged for continuity.
GATES: dict[str, dict[str, Any]] = {
    "C3MG_IWM5": _rule("iwm_ret_5m", ">=", -0.25, "five-minute small-cap weakness"),
    "C3MG_SPY5": _rule("spy_ret_5m", ">=", -0.20, "five-minute broad-index weakness"),
    "C3MG_BRD35": _rule("green_pct_5m", ">=", 35.0, "five-minute breadth"),
    "C3MG_MED10": _rule("median_return_5m", ">=", -0.10, "median-stock weakness"),
    "C3MG_P10": _rule("p10_return_5m", ">=", -0.75, "lower-tail weakness"),

    # Index/small-cap weakness: strict and lenient, short and sustained.
    "C3MG_I5S": _rule("iwm_ret_5m", ">=", -0.10, "strict short small-cap weakness"),
    "C3MG_I5L": _rule("iwm_ret_5m", ">=", -0.50, "lenient short small-cap weakness"),
    "C3MG_I15S": _rule("iwm_ret_15m", ">=", -0.30, "strict sustained small-cap weakness"),
    "C3MG_I15L": _rule("iwm_ret_15m", ">=", -0.60, "lenient sustained small-cap weakness"),
    "C3MG_QQQ5": _rule("qqq_ret_5m", ">=", -0.20, "five-minute growth-index weakness"),

    # Breadth was the clearest discriminator in the independent market study.
    "C3MG_BRD30": _rule("green_pct_5m", ">=", 30.0, "lenient short breadth floor"),
    "C3MG_BRD40": _rule("green_pct_5m", ">=", 40.0, "moderate short breadth floor"),
    "C3MG_BRD45": _rule("green_pct_5m", ">=", 45.0, "firm short breadth floor"),
    "C3MG_BRD50": _rule("green_pct_5m", ">=", 50.0, "majority-positive short breadth"),
    "C3MG_B15L": _rule("green_pct_15m", ">=", 35.0, "lenient sustained breadth floor"),
    "C3MG_B15S": _rule("green_pct_15m", ">=", 45.0, "strict sustained breadth floor"),

    # Central-market and tail weakness.
    "C3MG_M5S": _rule("median_return_5m", ">=", -0.05, "strict short median weakness"),
    "C3MG_M5L": _rule("median_return_5m", ">=", -0.20, "lenient short median weakness"),
    "C3MG_M15S": _rule("median_return_15m", ">=", -0.10, "strict sustained median weakness"),
    "C3MG_M15L": _rule("median_return_15m", ">=", -0.20, "lenient sustained median weakness"),
    "C3MG_P10S": _rule("p10_return_5m", ">=", -0.50, "strict lower-tail weakness"),
    "C3MG_P10L": _rule("p10_return_5m", ">=", -1.00, "lenient lower-tail weakness"),

    # Relative structure, deterioration, narrowing, tail spread, and stress.
    "C3MG_REL20": _rule("iwm_minus_spy_5m", ">=", -0.20, "small-cap lag versus SPY"),
    "C3MG_BSLP5": _rule("breadth_change_5v15", ">=", -5.0, "rapid breadth deterioration"),
    "C3MG_NAR50": _rule("spy_minus_median_5m", "<=", 0.50, "narrow SPY leadership"),
    "C3MG_DSP75": _rule("downside_spread_5m", "<=", 0.75, "stretched downside tail"),
    "C3MG_STRESS": _rule("p90_abs_return_5m", "<=", 1.00, "cross-sectional stress"),
}

CORE_COMPONENTS = ("C3MG_IWM5", "C3MG_SPY5", "C3MG_BRD35", "C3MG_MED10")
COMBOS: dict[str, dict[str, Any]] = {
    "C3MG_2OF4": {"components": CORE_COMPONENTS, "min_pass": 2,
                   "hypothesis": "lenient core consensus"},
    "C3MG_3OF4": {"components": CORE_COMPONENTS, "min_pass": 3,
                   "hypothesis": "majority core consensus"},
    "C3MG_4OF4": {"components": CORE_COMPONENTS, "min_pass": 4,
                   "hypothesis": "unanimous core consensus"},
    "C3MG_XS3": {"components": ("C3MG_I15S", "C3MG_B15S", "C3MG_M15S", "C3MG_P10S"),
                  "min_pass": 3, "hypothesis": "strict sustained consensus"},
    "C3MG_DIV2": {"components": ("C3MG_REL20", "C3MG_BSLP5", "C3MG_NAR50"),
                   "min_pass": 2, "hypothesis": "market-divergence consensus"},
}

# Compatibility for diagnostics written against v1.
COMBO_STRATEGY_ID = "C3MG_3OF4"
COMBO_COMPONENTS = CORE_COMPONENTS
COMBO_MIN_PASS = 3
FAMILY_STRATEGY_IDS = tuple(GATES) + tuple(COMBOS)


def _utc(value: Any) -> pd.Timestamp | None:
    try:
        result = pd.Timestamp(value)
    except (TypeError, ValueError):
        return None
    if pd.isna(result):
        return None
    return result.tz_localize("UTC") if result.tzinfo is None else result.tz_convert("UTC")


def _asof(series: pd.Series, timestamp: pd.Timestamp) -> float | None:
    eligible = series[series.index <= timestamp]
    if eligible.empty:
        return None
    try:
        value = float(eligible.iloc[-1])
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def _return_pct(current: float | None, previous: float | None) -> float | None:
    if current is None or previous is None or previous <= 0:
        return None
    return (current / previous - 1.0) * 100.0


class C3MarketGateFamily:
    def __init__(self) -> None:
        self._frame_cache_key: tuple[Any, ...] | None = None
        self._frame_cache = pd.DataFrame(columns=["timestamp", "symbol", "price"])
        self._feature_cache: dict[pd.Timestamp, dict[str, float]] = {}
        self.last_decisions: list[dict[str, Any]] = []

    def _normalize_frame(self, frame: pd.DataFrame) -> pd.DataFrame:
        required = {"timestamp", "symbol", "price"}
        if frame is None or frame.empty or not required.issubset(frame.columns):
            return pd.DataFrame(columns=["timestamp", "symbol", "price"])
        key = (id(frame), len(frame), str(frame["timestamp"].iloc[-1]))
        if key == self._frame_cache_key:
            return self._frame_cache
        work = frame[["timestamp", "symbol", "price"]].copy()
        work["timestamp"] = pd.to_datetime(work["timestamp"], utc=True, errors="coerce").dt.floor("min")
        work["symbol"] = work["symbol"].astype(str).str.upper()
        work["price"] = pd.to_numeric(work["price"], errors="coerce")
        work = work.dropna(subset=["timestamp", "symbol", "price"])
        work = work[work["price"] > 0]
        work = work.sort_values(["symbol", "timestamp"]).drop_duplicates(
            ["symbol", "timestamp"], keep="last"
        )
        self._frame_cache_key = key
        self._frame_cache = work
        self._feature_cache.clear()
        return work

    def features(self, entry_timestamp: Any, frame: pd.DataFrame) -> dict[str, float]:
        entry = _utc(entry_timestamp)
        if entry is None:
            return {}
        cutoff = entry.floor("min") - pd.Timedelta(minutes=1)
        work = self._normalize_frame(frame)
        cached = self._feature_cache.get(cutoff)
        if cached is not None:
            return dict(cached)
        if work.empty:
            return {}

        eligible = work[work["timestamp"] <= cutoff]
        if eligible.empty:
            return {}
        # Vectorized as-of snapshots preserve the v1 semantics while avoiding
        # thousands of Python-level per-symbol scans at every unique cutoff.
        current = eligible.groupby("symbol", sort=False)["price"].last()
        result: dict[str, float] = {}
        for lookback in LOOKBACKS:
            previous_cutoff = cutoff - pd.Timedelta(minutes=lookback)
            prior_rows = eligible[eligible["timestamp"] <= previous_cutoff]
            if prior_rows.empty:
                continue
            previous = prior_rows.groupby("symbol", sort=False)["price"].last()
            returns = ((current / previous) - 1.0).dropna() * 100.0
            for symbol in INDEX_SYMBOLS:
                if symbol in returns.index:
                    result[f"{symbol.lower()}_ret_{lookback}m"] = float(returns.loc[symbol])
            universe = returns[~returns.index.isin(INDEX_SYMBOLS)].astype(float)
            if len(universe) >= MIN_BREADTH_SYMBOLS:
                result[f"symbols_measured_{lookback}m"] = float(len(universe))
                result[f"green_pct_{lookback}m"] = float((universe > 0).mean() * 100.0)
                result[f"median_return_{lookback}m"] = float(universe.median())
                result[f"p10_return_{lookback}m"] = float(universe.quantile(0.10))
                result[f"p90_abs_return_{lookback}m"] = float(universe.abs().quantile(0.90))

        for name, left, right in (
            ("iwm_minus_spy_5m", "iwm_ret_5m", "spy_ret_5m"),
            ("breadth_change_5v15", "green_pct_5m", "green_pct_15m"),
            ("spy_minus_median_5m", "spy_ret_5m", "median_return_5m"),
            ("downside_spread_5m", "median_return_5m", "p10_return_5m"),
        ):
            if left in result and right in result:
                result[name] = result[left] - result[right]
        self._feature_cache[cutoff] = dict(result)
        return result

    @staticmethod
    def _passes(value: float, rule: Mapping[str, Any]) -> bool:
        threshold = float(rule["threshold"])
        return value >= threshold if rule["op"] == ">=" else value <= threshold

    def _child(self, parent: Mapping[str, Any], strategy_id: str,
               metadata: Mapping[str, Any]) -> dict[str, Any]:
        child = deepcopy(dict(parent))
        symbol = str(parent.get("symbol") or "").strip()
        child.update({
            "strategy_id": strategy_id,
            "setup_id": f"{strategy_id}|{symbol}|{parent.get('timestamp')}",
            "source_strategy_id": PARENT_STRATEGY_ID,
            "source_setup_id": parent.get("setup_id"),
            "forward_start_utc": FORWARD_START_UTC,
            "paper_only": True,
            "live_order_placement": False,
            "c3_market_gate_family_version": FAMILY_VERSION,
            **dict(metadata),
        })
        return child

    def derive_batch(self, parents: list[Mapping[str, Any]],
                     frame: pd.DataFrame) -> list[dict[str, Any]]:
        children: list[dict[str, Any]] = []
        decisions: list[dict[str, Any]] = []
        forward_start = _utc(FORWARD_START_UTC)
        for parent in parents:
            if str(parent.get("strategy_id") or "").upper() != PARENT_STRATEGY_ID:
                continue
            entry = _utc(parent.get("timestamp"))
            if entry is None or forward_start is None or entry < forward_start:
                continue
            features = self.features(entry, frame)
            cutoff = entry.floor("min") - pd.Timedelta(minutes=1)
            parent_decisions: dict[str, bool] = {}

            for strategy_id, rule in GATES.items():
                feature = str(rule["feature"])
                value = features.get(feature)
                passed = value is not None and self._passes(float(value), rule)
                parent_decisions[strategy_id] = passed
                decisions.append({
                    "strategy_id": strategy_id, "symbol": parent.get("symbol"),
                    "timestamp": parent.get("timestamp"), "source_setup_id": parent.get("setup_id"),
                    "feature": feature, "operator": rule["op"],
                    "threshold": float(rule["threshold"]), "value": value, "passed": passed,
                    "reason": "passed" if passed else ("missing_feature" if value is None else "gate_refrained"),
                    "feature_cutoff": cutoff.isoformat(), "hypothesis": rule["hypothesis"],
                })
                if passed:
                    children.append(self._child(parent, strategy_id, {
                        "c3_market_gate_feature": feature,
                        "c3_market_gate_operator": rule["op"],
                        "c3_market_gate_threshold": float(rule["threshold"]),
                        "c3_market_gate_value": float(value),
                        "c3_market_gate_cutoff": cutoff.isoformat(),
                    }))

            for strategy_id, combo in COMBOS.items():
                components = tuple(combo["components"])
                pass_count = sum(parent_decisions.get(component, False) for component in components)
                passed = all(c in parent_decisions for c in components) and pass_count >= int(combo["min_pass"])
                parent_decisions[strategy_id] = passed
                decisions.append({
                    "strategy_id": strategy_id, "symbol": parent.get("symbol"),
                    "timestamp": parent.get("timestamp"), "source_setup_id": parent.get("setup_id"),
                    "feature": "combo_pass_count", "operator": ">=",
                    "threshold": float(combo["min_pass"]), "value": float(pass_count),
                    "passed": passed, "reason": "passed" if passed else "gate_refrained",
                    "feature_cutoff": cutoff.isoformat(), "components": list(components),
                    "hypothesis": combo["hypothesis"],
                })
                if passed:
                    children.append(self._child(parent, strategy_id, {
                        "c3_market_gate_feature": "combo_pass_count",
                        "c3_market_gate_operator": ">=",
                        "c3_market_gate_threshold": float(combo["min_pass"]),
                        "c3_market_gate_value": float(pass_count),
                        "c3_market_gate_cutoff": cutoff.isoformat(),
                        "c3_market_gate_components": list(components),
                    }))
        self.last_decisions = decisions
        return children
