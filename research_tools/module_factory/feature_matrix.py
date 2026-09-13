"""
Generic symbol-minute feature matrix for Module Factory.

Each row represents what was knowable at one symbol-minute plus forward
outcomes used only by the research evaluator.

No named strategy logic lives here.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from statistics import mean

from research_tools.cascade_reversal_study import Bar


@dataclass
class FeatureRow:
    symbol: str
    minute: datetime
    price: float
    features: dict[str, float]
    forward_returns: dict[int, float]


def _returns(closes: list[float]) -> list[float]:
    return [
        100.0 * (closes[i] / closes[i - 1] - 1.0)
        for i in range(1, len(closes))
        if closes[i - 1] > 0
    ]


def _population_std(values: list[float]) -> float:
    if not values:
        return 0.0
    m = mean(values)
    return math.sqrt(mean((x - m) ** 2 for x in values))


def _skew(values: list[float]) -> float:
    if len(values) < 3:
        return 0.0
    m = mean(values)
    sd = _population_std(values)
    if sd == 0:
        return 0.0
    return mean(((x - m) / sd) ** 3 for x in values)


def _kurtosis(values: list[float]) -> float:
    if len(values) < 4:
        return 0.0
    m = mean(values)
    sd = _population_std(values)
    if sd == 0:
        return 0.0
    # Excess kurtosis.
    return mean(((x - m) / sd) ** 4 for x in values) - 3.0


def _autocorr_lag1(values: list[float]) -> float:
    if len(values) < 3:
        return 0.0

    left = values[:-1]
    right = values[1:]

    lm = mean(left)
    rm = mean(right)

    numerator = sum(
        (x - lm) * (y - rm)
        for x, y in zip(left, right)
    )

    left_ss = sum((x - lm) ** 2 for x in left)
    right_ss = sum((y - rm) ** 2 for y in right)

    denominator = math.sqrt(left_ss * right_ss)

    return numerator / denominator if denominator else 0.0


def _contiguous(
    bars: list[Bar],
    start: int,
    end: int,
) -> bool:
    return all(
        bars[i].minute - bars[i - 1].minute == timedelta(minutes=1)
        for i in range(start + 1, end + 1)
    )


def _return_over(
    bars: list[Bar],
    index: int,
    lookback: int,
) -> float:
    old = bars[index - lookback].close
    new = bars[index].close
    return 100.0 * (new / old - 1.0)


def _features_for_index(
    bars: list[Bar],
    index: int,
    spy_by_minute: dict[datetime, Bar],
) -> dict[str, float]:

    result: dict[str, float] = {}

    # Price displacement.
    for lookback in (1, 2, 3, 5, 10, 15, 20, 30, 60):
        result[f"return_{lookback}"] = _return_over(
            bars, index, lookback
        )

    # Realized volatility of one-minute returns.
    for lookback in (3, 5, 10, 20, 30, 60):
        closes = [
            bar.close
            for bar in bars[index - lookback:index + 1]
        ]
        result[f"volatility_{lookback}"] = _population_std(
            _returns(closes)
        )

    # Current close location in rolling high-low range.
    for lookback in (5, 10, 20, 30, 60):
        window = bars[index - lookback + 1:index + 1]
        high = max(bar.high for bar in window)
        low = min(bar.low for bar in window)
        span = high - low

        result[f"range_position_{lookback}"] = (
            (bars[index].close - low) / span
            if span > 0
            else 0.5
        )

    # Fraction of positive one-minute changes.
    for lookback in (3, 5, 10, 20, 30):
        closes = [
            bar.close
            for bar in bars[index - lookback:index + 1]
        ]
        values = _returns(closes)
        result[f"up_fraction_{lookback}"] = (
            sum(x > 0 for x in values) / len(values)
            if values
            else 0.0
        )

    # Change in equal-length return: recent leg minus previous leg.
    for lookback in (2, 3, 5, 10, 20):
        recent = _return_over(bars, index, lookback)
        previous_end = index - lookback
        previous_start = previous_end - lookback

        previous = 100.0 * (
            bars[previous_end].close
            / bars[previous_start].close
            - 1.0
        )

        result[f"acceleration_{lookback}"] = recent - previous

    # Lag-1 serial dependence of one-minute returns.
    for lookback in (5, 10, 20, 30):
        closes = [
            bar.close
            for bar in bars[index - lookback:index + 1]
        ]
        result[f"autocorr_1_{lookback}"] = _autocorr_lag1(
            _returns(closes)
        )

    # Distribution shape.
    for lookback in (10, 20, 30, 60):
        closes = [
            bar.close
            for bar in bars[index - lookback:index + 1]
        ]
        values = _returns(closes)

        result[f"skew_{lookback}"] = _skew(values)
        result[f"kurtosis_{lookback}"] = _kurtosis(values)

    # Market-relative return.
    for lookback in (1, 3, 5, 10, 20, 30, 60):
        current_spy = spy_by_minute.get(bars[index].minute)
        old_minute = bars[index - lookback].minute
        old_spy = spy_by_minute.get(old_minute)

        if current_spy is None or old_spy is None:
            result[f"spy_relative_return_{lookback}"] = math.nan
            continue

        spy_return = 100.0 * (
            current_spy.close / old_spy.close - 1.0
        )

        result[f"spy_relative_return_{lookback}"] = (
            result[f"return_{lookback}"] - spy_return
        )

    return result


def build_feature_matrix(
    bars_by_symbol: dict[str, list[Bar]],
    *,
    horizons: tuple[int, ...] = (1, 5, 10, 20),
    max_lookback: int = 60,
    stride: int = 1,
) -> list[FeatureRow]:

    if stride < 1:
        raise ValueError("stride must be >= 1")

    rows: list[FeatureRow] = []

    spy_by_minute = {
        bar.minute: bar
        for bar in bars_by_symbol.get("SPY", [])
    }

    longest_horizon = max(horizons)

    for symbol, bars in sorted(bars_by_symbol.items()):
        if symbol == "SPY":
            continue

        if len(bars) <= max_lookback + longest_horizon:
            continue

        for index in range(
            max_lookback,
            len(bars) - longest_horizon,
            stride,
        ):
            if not _contiguous(
                bars,
                index - max_lookback,
                index + longest_horizon,
            ):
                continue

            features = _features_for_index(
                bars,
                index,
                spy_by_minute,
            )

            forward = {
                horizon: 100.0 * (
                    bars[index + horizon].close
                    / bars[index].close
                    - 1.0
                )
                for horizon in horizons
            }

            rows.append(
                FeatureRow(
                    symbol=symbol,
                    minute=bars[index].minute,
                    price=bars[index].close,
                    features=features,
                    forward_returns=forward,
                )
            )

    return rows
