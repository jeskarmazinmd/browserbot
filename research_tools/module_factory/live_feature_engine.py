"""
Rolling live feature engine for Module Factory.

Consumes completed minute prices and computes only contemporaneous/past-derived
features. No forward outcomes are produced here.
"""

from __future__ import annotations

import math
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime
from statistics import mean
from typing import Deque

from research_tools.module_factory.live_minute_feed import (
    CompletedMinute,
)


@dataclass(frozen=True)
class LiveFeatureRow:
    symbol: str
    timestamp: datetime
    price: float
    features: dict[str, float]


def _population_std(values: list[float]) -> float:
    if not values:
        return 0.0

    m = mean(values)
    return math.sqrt(
        mean((value - m) ** 2 for value in values)
    )


def _returns(closes: list[float]) -> list[float]:
    result = []

    for index in range(1, len(closes)):
        old = closes[index - 1]
        new = closes[index]

        if old <= 0:
            continue

        result.append(
            100.0 * (new / old - 1.0)
        )

    return result


def _skew(values: list[float]) -> float:
    if len(values) < 3:
        return 0.0

    m = mean(values)
    sd = _population_std(values)

    if sd == 0:
        return 0.0

    return mean(
        ((value - m) / sd) ** 3
        for value in values
    )


def _kurtosis(values: list[float]) -> float:
    if len(values) < 4:
        return 0.0

    m = mean(values)
    sd = _population_std(values)

    if sd == 0:
        return 0.0

    return (
        mean(
            ((value - m) / sd) ** 4
            for value in values
        )
        - 3.0
    )


def _autocorr_lag1(values: list[float]) -> float:
    if len(values) < 3:
        return 0.0

    left = values[:-1]
    right = values[1:]

    left_mean = mean(left)
    right_mean = mean(right)

    numerator = sum(
        (x - left_mean) * (y - right_mean)
        for x, y in zip(left, right)
    )

    left_ss = sum(
        (x - left_mean) ** 2
        for x in left
    )
    right_ss = sum(
        (y - right_mean) ** 2
        for y in right
    )

    denominator = math.sqrt(
        left_ss * right_ss
    )

    return (
        numerator / denominator
        if denominator
        else 0.0
    )


class LiveFeatureEngine:
    def __init__(
        self,
        *,
        max_history_minutes: int = 121,
    ):
        if max_history_minutes < 61:
            raise ValueError(
                "max_history_minutes must be >= 61"
            )

        self.max_history_minutes = int(
            max_history_minutes
        )

        self._history: dict[
            str,
            Deque[tuple[datetime, float]],
        ] = defaultdict(
            lambda: deque(
                maxlen=self.max_history_minutes
            )
        )

    def _append_minute(
        self,
        completed: CompletedMinute,
    ) -> None:
        for symbol, price in completed.prices.items():
            if price <= 0:
                continue

            history = self._history[symbol]

            if (
                history
                and completed.minute
                <= history[-1][0]
            ):
                continue

            history.append(
                (completed.minute, float(price))
            )

    @staticmethod
    def _is_contiguous(
        history: list[tuple[datetime, float]],
        required_points: int,
    ) -> bool:
        if len(history) < required_points:
            return False

        recent = history[-required_points:]

        for index in range(1, len(recent)):
            delta = (
                recent[index][0]
                - recent[index - 1][0]
            )

            if delta.total_seconds() != 60:
                return False

        return True

    @staticmethod
    def _return_over(
        closes: list[float],
        lookback: int,
    ) -> float:
        old = closes[-lookback - 1]
        new = closes[-1]

        return 100.0 * (
            new / old - 1.0
        )

    def _features_for_symbol(
        self,
        symbol: str,
    ) -> dict[str, float] | None:
        history = list(self._history[symbol])

        if not self._is_contiguous(
            history,
            61,
        ):
            return None

        closes = [
            price
            for _, price in history
        ]

        result: dict[str, float] = {}

        for lookback in (
            1,
            2,
            3,
            5,
            10,
            15,
            20,
            30,
            60,
        ):
            result[f"return_{lookback}"] = (
                self._return_over(
                    closes,
                    lookback,
                )
            )

        for lookback in (
            3,
            5,
            10,
            20,
            30,
            60,
        ):
            values = _returns(
                closes[-lookback - 1:]
            )

            result[
                f"volatility_{lookback}"
            ] = _population_std(values)

        # range_position_* is intentionally unavailable
        # in the live Factory path.
        #
        # Research uses rolling minute HIGH/LOW values,
        # while the production tape contains only the
        # final observed price for each minute.
        # Do not substitute a close-only approximation.

        for lookback in (
            3,
            5,
            10,
            20,
            30,
        ):
            values = _returns(
                closes[-lookback - 1:]
            )

            result[
                f"up_fraction_{lookback}"
            ] = (
                sum(value > 0 for value in values)
                / len(values)
                if values
                else 0.0
            )

        for lookback in (
            2,
            3,
            5,
            10,
            20,
        ):
            required = lookback * 2 + 1

            if len(closes) < required:
                continue

            recent = 100.0 * (
                closes[-1]
                / closes[-lookback - 1]
                - 1.0
            )

            previous_end = (
                len(closes)
                - lookback
                - 1
            )
            previous_start = (
                previous_end
                - lookback
            )

            previous = 100.0 * (
                closes[previous_end]
                / closes[previous_start]
                - 1.0
            )

            result[
                f"acceleration_{lookback}"
            ] = recent - previous

        for lookback in (
            5,
            10,
            20,
            30,
        ):
            values = _returns(
                closes[-lookback - 1:]
            )

            result[
                f"autocorr_1_{lookback}"
            ] = _autocorr_lag1(values)

        for lookback in (
            10,
            20,
            30,
            60,
        ):
            values = _returns(
                closes[-lookback - 1:]
            )

            result[
                f"skew_{lookback}"
            ] = _skew(values)

            result[
                f"kurtosis_{lookback}"
            ] = _kurtosis(values)

        return result

    def consume(
        self,
        completed: CompletedMinute,
    ) -> tuple[LiveFeatureRow, ...]:
        self._append_minute(completed)

        spy_features = None

        if "SPY" in completed.prices:
            spy_features = self._features_for_symbol(
                "SPY"
            )

        rows = []

        for symbol, price in sorted(
            completed.prices.items()
        ):
            if symbol == "SPY":
                continue

            features = self._features_for_symbol(
                symbol
            )

            if features is None:
                continue

            if spy_features is not None:
                for lookback in (
                    1,
                    3,
                    5,
                    10,
                    20,
                    30,
                    60,
                ):
                    own = features.get(
                        f"return_{lookback}"
                    )
                    spy = spy_features.get(
                        f"return_{lookback}"
                    )

                    if (
                        own is not None
                        and spy is not None
                    ):
                        features[
                            f"spy_relative_return_{lookback}"
                        ] = own - spy

            rows.append(
                LiveFeatureRow(
                    symbol=symbol,
                    timestamp=completed.minute,
                    price=float(price),
                    features=features,
                )
            )

        return tuple(rows)
