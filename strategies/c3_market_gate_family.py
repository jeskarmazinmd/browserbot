"""Prospective, paper-only market-regime gates for C3N25S10.

Every arm receives the canonical parent entry and either mirrors it unchanged
or refrains.  Inputs end one full clock minute before the parent entry, so no
entry-minute or future information can influence admission.  Thresholds are
round, pre-registered research hypotheses rather than fitted values.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from typing import Any, Mapping

import pandas as pd


PARENT_STRATEGY_ID = "C3N25S10"
FORWARD_START_UTC = "2026-09-02T13:30:00+00:00"
FAMILY_VERSION = "c3_market_gate_v1_20260902"
MIN_BREADTH_SYMBOLS = 50

GATES: dict[str, dict[str, Any]] = {
    "C3MG_IWM5": {
        "feature": "iwm_ret_5m",
        "op": ">=",
        "threshold": -0.25,
        "hypothesis": "avoid entries during sharp five-minute small-cap selling",
    },
    "C3MG_SPY5": {
        "feature": "spy_ret_5m",
        "op": ">=",
        "threshold": -0.20,
        "hypothesis": "avoid entries during sharp five-minute broad-market selling",
    },
    "C3MG_BRD35": {
        "feature": "green_pct_5m",
        "op": ">=",
        "threshold": 35.0,
        "hypothesis": "require at least modest five-minute market breadth",
    },
    "C3MG_MED10": {
        "feature": "median_return_5m",
        "op": ">=",
        "threshold": -0.10,
        "hypothesis": "avoid a materially falling median eligible symbol",
    },
    "C3MG_P10": {
        "feature": "p10_return_5m",
        "op": ">=",
        "threshold": -0.75,
        "hypothesis": "avoid severe weakness in the lower tail of the universe",
    },
}

COMBO_STRATEGY_ID = "C3MG_3OF4"
COMBO_COMPONENTS = (
    "C3MG_IWM5",
    "C3MG_SPY5",
    "C3MG_BRD35",
    "C3MG_MED10",
)
COMBO_MIN_PASS = 3
FAMILY_STRATEGY_IDS = tuple(GATES) + (COMBO_STRATEGY_ID,)


def _utc(value: Any) -> pd.Timestamp | None:
    try:
        result = pd.Timestamp(value)
    except (TypeError, ValueError):
        return None
    if pd.isna(result):
        return None
    if result.tzinfo is None:
        return result.tz_localize("UTC")
    return result.tz_convert("UTC")


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
    """Evaluate causal market gates and clone only admitted parent entries."""

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
        work["timestamp"] = pd.to_datetime(
            work["timestamp"], utc=True, errors="coerce"
        ).dt.floor("min")
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

        previous_cutoff = cutoff - pd.Timedelta(minutes=5)
        returns: dict[str, float] = {}
        for symbol, rows in work[work["timestamp"] <= cutoff].groupby("symbol"):
            series = rows.set_index("timestamp")["price"].sort_index()
            value = _return_pct(
                _asof(series, cutoff),
                _asof(series, previous_cutoff),
            )
            if value is not None:
                returns[str(symbol)] = value

        result: dict[str, float] = {}
        for symbol, feature in (
            ("IWM", "iwm_ret_5m"),
            ("SPY", "spy_ret_5m"),
            ("QQQ", "qqq_ret_5m"),
        ):
            if symbol in returns:
                result[feature] = returns[symbol]

        universe_returns = pd.Series(
            [value for symbol, value in returns.items() if symbol not in {"SPY", "QQQ", "IWM"}],
            dtype=float,
        )
        if len(universe_returns) >= MIN_BREADTH_SYMBOLS:
            result.update({
                "symbols_measured": float(len(universe_returns)),
                "green_pct_5m": float((universe_returns > 0).mean() * 100.0),
                "median_return_5m": float(universe_returns.median()),
                "p10_return_5m": float(universe_returns.quantile(0.10)),
            })

        self._feature_cache[cutoff] = dict(result)
        return result

    @staticmethod
    def _passes(value: float, rule: Mapping[str, Any]) -> bool:
        threshold = float(rule["threshold"])
        return value >= threshold if rule["op"] == ">=" else value <= threshold

    def _child(
        self,
        parent: Mapping[str, Any],
        strategy_id: str,
        metadata: Mapping[str, Any],
    ) -> dict[str, Any]:
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

    def derive_batch(
        self,
        parents: list[Mapping[str, Any]],
        frame: pd.DataFrame,
    ) -> list[dict[str, Any]]:
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
                decision = {
                    "strategy_id": strategy_id,
                    "symbol": parent.get("symbol"),
                    "timestamp": parent.get("timestamp"),
                    "source_setup_id": parent.get("setup_id"),
                    "feature": feature,
                    "operator": rule["op"],
                    "threshold": float(rule["threshold"]),
                    "value": value,
                    "passed": passed,
                    "reason": "passed" if passed else ("missing_feature" if value is None else "gate_refrained"),
                    "feature_cutoff": cutoff.isoformat(),
                    "hypothesis": rule["hypothesis"],
                }
                decisions.append(decision)
                if passed:
                    children.append(self._child(parent, strategy_id, {
                        "c3_market_gate_feature": feature,
                        "c3_market_gate_operator": rule["op"],
                        "c3_market_gate_threshold": float(rule["threshold"]),
                        "c3_market_gate_value": float(value),
                        "c3_market_gate_cutoff": cutoff.isoformat(),
                    }))

            combo_passes = sum(parent_decisions.get(component, False) for component in COMBO_COMPONENTS)
            combo_passed = combo_passes >= COMBO_MIN_PASS and all(
                component in parent_decisions for component in COMBO_COMPONENTS
            )
            decisions.append({
                "strategy_id": COMBO_STRATEGY_ID,
                "symbol": parent.get("symbol"),
                "timestamp": parent.get("timestamp"),
                "source_setup_id": parent.get("setup_id"),
                "feature": "combo_pass_count",
                "operator": ">=",
                "threshold": float(COMBO_MIN_PASS),
                "value": float(combo_passes),
                "passed": combo_passed,
                "reason": "passed" if combo_passed else "gate_refrained",
                "feature_cutoff": cutoff.isoformat(),
                "components": list(COMBO_COMPONENTS),
            })
            if combo_passed:
                children.append(self._child(parent, COMBO_STRATEGY_ID, {
                    "c3_market_gate_feature": "combo_pass_count",
                    "c3_market_gate_operator": ">=",
                    "c3_market_gate_threshold": float(COMBO_MIN_PASS),
                    "c3_market_gate_value": float(combo_passes),
                    "c3_market_gate_cutoff": cutoff.isoformat(),
                    "c3_market_gate_components": list(COMBO_COMPONENTS),
                }))

        self.last_decisions = decisions
        return children
