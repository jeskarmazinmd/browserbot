"""Prospective, research-only admission descendants of C3N25S10.

Each child clones an already-confirmed canonical entry and changes no entry or
exit price.  A child exists only when its frozen, pre-entry feature rule passes.
Feature computation deliberately ends one full clock minute before entry to
match ``research_tools/trading_analyzer.py`` and prevent entry-minute leakage.
"""

from __future__ import annotations

from collections import deque
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Mapping

import pandas as pd


PARENT_STRATEGY_ID = "C3N25S10"
FORWARD_START_UTC = "2026-08-31T13:30:00+00:00"
FAMILY_VERSION = "c3_admission_v1_20260831"

# These are the genuinely distinct single-feature survivors reported by the
# analyzer's 2026-08-21..28 day-level train/test split.  Fixed-window slope
# aliases are intentionally omitted because they select the same trades as the
# corresponding returns.  No combinations are included without separate OOS
# evidence.
FILTERS: dict[str, dict[str, Any]] = {
    "C3F_VOL3": {"feature": "vol_3m", "op": ">=", "threshold": 0.5075},
    "C3F_DEN5": {"feature": "signal_density_5m", "op": ">=", "threshold": 14.0},
    "C3F_R2DN": {"feature": "ret_2m", "op": "<=", "threshold": -1.1078},
    "C3F_R1DN": {"feature": "ret_1m", "op": "<=", "threshold": -0.5348},
    "C3F_R3FLAT": {"feature": "ret_3m", "op": ">=", "threshold": -0.5782},
    "C3F_P10R1": {"feature": "cross_p10_ret_1m", "op": ">=", "threshold": -0.0976},
    "C3F_P10R5": {"feature": "cross_p10_ret_5m", "op": ">=", "threshold": -0.2635},
    "C3F_HI3": {"feature": "dist_from_3m_high", "op": "<=", "threshold": -0.8660},
    "C3F_LOW3": {"feature": "dist_from_3m_low", "op": "<=", "threshold": 0.0},
    "C3F_HI5": {"feature": "dist_from_5m_high", "op": "<=", "threshold": -1.4266},
    "C3F_HI10": {"feature": "dist_from_10m_high", "op": "<=", "threshold": -2.3223},
}

FAMILY_STRATEGY_IDS = tuple(FILTERS)


def _utc(value: Any) -> datetime | None:
    try:
        result = pd.Timestamp(value)
    except (TypeError, ValueError):
        return None
    if pd.isna(result):
        return None
    if result.tzinfo is None:
        result = result.tz_localize("UTC")
    else:
        result = result.tz_convert("UTC")
    return result.to_pydatetime()


def _pct(current: float | None, previous: float | None) -> float | None:
    if current is None or previous is None or previous <= 0:
        return None
    return (current / previous - 1.0) * 100.0


def _asof(series: pd.Series, timestamp: pd.Timestamp) -> float | None:
    eligible = series[series.index <= timestamp]
    if eligible.empty:
        return None
    try:
        value = float(eligible.iloc[-1])
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


class C3AdmissionFamily:
    """Compute causal features and fan one canonical entry into passing arms."""

    def __init__(self) -> None:
        self._canonical_entries: deque[pd.Timestamp] = deque()
        self._frame_cache_key: tuple[Any, ...] | None = None
        self._frame_cache = pd.DataFrame(columns=["timestamp", "symbol", "price"])
        self._cross_cache: dict[tuple[tuple[Any, ...], pd.Timestamp], dict[str, float]] = {}

    def _signal_density(self, entry: pd.Timestamp) -> int:
        cutoff = entry - pd.Timedelta(minutes=5)
        while self._canonical_entries and self._canonical_entries[0] < cutoff:
            self._canonical_entries.popleft()
        self._canonical_entries.append(entry)
        return len(self._canonical_entries)

    def _normalize_frame(self, frame: pd.DataFrame) -> pd.DataFrame:
        required = {"timestamp", "symbol", "price"}
        if frame is None or frame.empty or not required.issubset(frame.columns):
            return pd.DataFrame(columns=["timestamp", "symbol", "price"])
        key = (id(frame), len(frame), str(frame["timestamp"].iloc[-1]))
        if key == self._frame_cache_key:
            return self._frame_cache
        work = frame[["timestamp", "symbol", "price"]].copy()
        work["timestamp"] = pd.to_datetime(work["timestamp"], utc=True, errors="coerce").dt.floor("min")
        work["symbol"] = work["symbol"].astype(str)
        work["price"] = pd.to_numeric(work["price"], errors="coerce")
        work = work.dropna(subset=["timestamp", "symbol", "price"])
        work = work[work["price"] > 0]
        normalized = (
            work.sort_values(["timestamp", "symbol"])
            .drop_duplicates(["symbol", "timestamp"], keep="last")
        )
        self._frame_cache_key = key
        self._frame_cache = normalized
        self._cross_cache.clear()
        return normalized

    def _cross_features(
        self,
        work: pd.DataFrame,
        cutoff: pd.Timestamp,
    ) -> dict[str, float]:
        cache_key = (self._frame_cache_key or (id(work), len(work)), cutoff)
        cached = self._cross_cache.get(cache_key)
        if cached is not None:
            return dict(cached)
        result: dict[str, float] = {}
        market_rows = work[work["timestamp"] <= cutoff]
        if not market_rows.empty:
            wide = market_rows.pivot(index="timestamp", columns="symbol", values="price").sort_index()
            if cutoff in wide.index:
                for minutes in (1, 5):
                    returns = wide.pct_change(minutes, fill_method=None) * 100.0
                    row = returns.loc[cutoff].dropna()
                    if not row.empty:
                        result[f"cross_p10_ret_{minutes}m"] = float(row.quantile(0.10))
        self._cross_cache[cache_key] = dict(result)
        return result

    def features(
        self,
        parent: Mapping[str, Any],
        frame: pd.DataFrame,
        *,
        density: int | None = None,
    ) -> dict[str, float]:
        entry_dt = _utc(parent.get("timestamp"))
        symbol = str(parent.get("symbol") or "").strip()
        if entry_dt is None or not symbol:
            return {}
        entry = pd.Timestamp(entry_dt)
        cutoff = entry.floor("min") - pd.Timedelta(minutes=1)
        work = self._normalize_frame(frame)
        features: dict[str, float] = {
            "signal_density_5m": float(
                self._signal_density(entry) if density is None else density
            ),
        }
        if work.empty:
            return features

        symbol_rows = work[(work["symbol"] == symbol) & (work["timestamp"] <= cutoff)]
        symbol_series = symbol_rows.set_index("timestamp")["price"].sort_index()
        p0 = _asof(symbol_series, cutoff)
        if p0 is not None:
            for minutes in (1, 2, 3):
                previous = _asof(symbol_series, cutoff - pd.Timedelta(minutes=minutes))
                value = _pct(p0, previous)
                if value is not None:
                    features[f"ret_{minutes}m"] = value

            for minutes in (3, 5, 10):
                start = cutoff - pd.Timedelta(minutes=minutes - 1)
                window = symbol_series[(symbol_series.index >= start) & (symbol_series.index <= cutoff)]
                if not window.empty:
                    features[f"dist_from_{minutes}m_high"] = _pct(p0, float(window.max()))
                    features[f"dist_from_{minutes}m_low"] = _pct(p0, float(window.min()))
                if minutes == 3 and len(window) >= 3:
                    returns = window.pct_change().dropna() * 100.0
                    if len(returns) >= 2:
                        features["vol_3m"] = float(returns.std())

        features.update(self._cross_features(work, cutoff))
        return {key: value for key, value in features.items() if value is not None}

    def _derive_with_density(
        self,
        parent: Mapping[str, Any],
        frame: pd.DataFrame,
        density: int | None,
    ) -> list[dict[str, Any]]:
        if str(parent.get("strategy_id") or "").upper() != PARENT_STRATEGY_ID:
            return []
        entry_dt = _utc(parent.get("timestamp"))
        forward_start = _utc(FORWARD_START_UTC)
        if entry_dt is None or forward_start is None:
            return []

        # Always observe canonical density, including warm-up/pre-start entries.
        feature_values = self.features(parent, frame, density=density)
        if entry_dt < forward_start:
            return []

        symbol = str(parent.get("symbol") or "").strip()
        if not symbol:
            return []
        source_setup_id = str(
            parent.get("setup_id")
            or f"{PARENT_STRATEGY_ID}|{symbol}|{pd.Timestamp(entry_dt).floor('min').isoformat()}"
        )

        children: list[dict[str, Any]] = []
        for strategy_id, rule in FILTERS.items():
            feature = str(rule["feature"])
            if feature not in feature_values:
                continue  # Missing causal input fails closed for this arm.
            value = float(feature_values[feature])
            threshold = float(rule["threshold"])
            passed = value <= threshold if rule["op"] == "<=" else value >= threshold
            if not passed:
                continue
            child = deepcopy(dict(parent))
            child.update({
                "strategy_id": strategy_id,
                "setup_id": f"{strategy_id}|{symbol}|{parent.get('timestamp')}",
                "source_strategy_id": PARENT_STRATEGY_ID,
                "source_setup_id": source_setup_id,
                "forward_start_utc": FORWARD_START_UTC,
                "paper_only": True,
                "live_order_placement": False,
                "c3_admission_family_version": FAMILY_VERSION,
                "c3_admission_feature": feature,
                "c3_admission_operator": rule["op"],
                "c3_admission_threshold": threshold,
                "c3_admission_value": value,
                "c3_admission_cutoff": (
                    pd.Timestamp(entry_dt).floor("min") - pd.Timedelta(minutes=1)
                ).isoformat(),
            })
            children.append(child)
        return children

    def derive(self, parent: Mapping[str, Any], frame: pd.DataFrame) -> list[dict[str, Any]]:
        """Derive from one parent; batch callers should prefer ``derive_batch``."""
        return self._derive_with_density(parent, frame, None)

    def derive_batch(
        self,
        parents: list[Mapping[str, Any]],
        frame: pd.DataFrame,
    ) -> list[dict[str, Any]]:
        """Derive a scan atomically so simultaneous entries share one density."""
        canonical: list[tuple[Mapping[str, Any], pd.Timestamp]] = []
        for parent in parents:
            if str(parent.get("strategy_id") or "").upper() != PARENT_STRATEGY_ID:
                continue
            timestamp = _utc(parent.get("timestamp"))
            if timestamp is not None:
                canonical.append((parent, pd.Timestamp(timestamp)))
        if not canonical:
            return []

        all_times = list(self._canonical_entries) + [timestamp for _, timestamp in canonical]
        newest = max(all_times)
        oldest_relevant = newest - pd.Timedelta(minutes=5)
        all_times = sorted(timestamp for timestamp in all_times if timestamp >= oldest_relevant)
        self._canonical_entries = deque(all_times)

        children: list[dict[str, Any]] = []
        for parent, timestamp in canonical:
            start = timestamp - pd.Timedelta(minutes=5)
            density = sum(start <= candidate <= timestamp for candidate in all_times)
            children.extend(self._derive_with_density(parent, frame, density))
        return children
