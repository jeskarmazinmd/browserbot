"""
Time-series scientist for Module Factory.

Question:
    Does a feature contain information whose relationship with a future
    outcome depends on when the feature was observed?

This scientist studies:
    - lagged effects
    - delayed information
    - persistence versus reversal
    - sign changes across lags
    - strongest response lag

Rows are grouped by symbol and ordered by minute so information never
travels across symbols.

No predictive direction is specified in advance.
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from typing import Iterable

from research_tools.module_factory.research_rows import (
    UnifiedResearchRow,
)


def _finite(value: float) -> bool:
    return math.isfinite(value)


def _pearson(
    xs: list[float],
    ys: list[float],
) -> float:
    if len(xs) < 3:
        return math.nan

    mx = sum(xs) / len(xs)
    my = sum(ys) / len(ys)

    dx = [
        value - mx
        for value in xs
    ]
    dy = [
        value - my
        for value in ys
    ]

    vx = sum(
        value * value
        for value in dx
    )
    vy = sum(
        value * value
        for value in dy
    )

    if vx <= 1e-18 or vy <= 1e-18:
        return math.nan

    return sum(
        x * y
        for x, y in zip(dx, dy)
    ) / math.sqrt(vx * vy)


def _group_rows(
    rows: Iterable[
        UnifiedResearchRow
    ],
) -> dict[str, list[UnifiedResearchRow]]:
    grouped = {}

    for row in rows:
        grouped.setdefault(
            row.symbol,
            [],
        ).append(row)

    for symbol_rows in grouped.values():
        symbol_rows.sort(
            key=lambda row: row.minute
        )

    return grouped


def _direction(
    correlation: float,
) -> int:
    return (
        1
        if correlation > 0.0
        else -1
    )


@dataclass(frozen=True)
class LagEvidence:
    lag: int
    n: int
    correlation: float
    independent_time_units: int

    @property
    def direction(self) -> int:
        return _direction(
            self.correlation
        )


@dataclass(frozen=True)
class TimeSeriesDiscovery:
    feature: str
    horizon: int
    evidence: tuple[
        LagEvidence,
        ...
    ]
    best_lag: int
    best_correlation: float
    contemporaneous_correlation: float
    incremental_lag_edge: float
    sign_change: bool
    direction: int
    score: float
    independent_time_units: int
    ancestry: tuple[str, ...]

    @property
    def discovery_id(self) -> str:
        lags = ",".join(
            str(item.lag)
            for item in self.evidence
        )

        payload = (
            f"{self.feature}|"
            f"{self.horizon}|"
            f"{lags}"
        )

        digest = hashlib.sha256(
            payload.encode()
        ).hexdigest()[:16]

        return f"time_series:{digest}"


def evaluate_lag_structure(
    rows: Iterable[
        UnifiedResearchRow
    ],
    *,
    feature: str,
    horizon: int,
    lags: tuple[int, ...] = (
        0,
        1,
        2,
        3,
        5,
        10,
    ),
    min_samples: int = 30,
) -> TimeSeriesDiscovery | None:
    if not lags:
        raise ValueError(
            "at least one lag is required"
        )

    if any(
        lag < 0
        for lag in lags
    ):
        raise ValueError(
            "lags must be non-negative"
        )

    lags = tuple(
        sorted(set(lags))
    )

    grouped = _group_rows(rows)

    evidence = []
    ancestry = set()

    for lag in lags:
        xs = []
        ys = []
        target_minutes = set()

        for symbol_rows in (
            grouped.values()
        ):
            for index, target_row in (
                enumerate(symbol_rows)
            ):
                source_index = (
                    index - lag
                )

                if source_index < 0:
                    continue

                source_row = symbol_rows[
                    source_index
                ]

                x = source_row.feature(
                    feature
                )

                outcome = target_row.outcome(
                    horizon
                )

                if not (
                    _finite(x)
                    and _finite(outcome)
                ):
                    continue

                xs.append(x)
                ys.append(outcome)
                target_minutes.add(
                    target_row.minute
                )

                ancestry.update(
                    source_row.ancestry(
                        feature
                    )
                )

        if len(xs) < min_samples:
            continue

        correlation = _pearson(
            xs,
            ys,
        )

        if not _finite(correlation):
            continue

        evidence.append(
            LagEvidence(
                lag=lag,
                n=len(xs),
                correlation=(
                    correlation
                ),
                independent_time_units=len(
                    target_minutes
                ),
            )
        )

    if not evidence:
        return None

    best = max(
        evidence,
        key=lambda item: abs(
            item.correlation
        ),
    )

    lag_zero = next(
        (
            item
            for item in evidence
            if item.lag == 0
        ),
        None,
    )

    contemporaneous = (
        lag_zero.correlation
        if lag_zero is not None
        else 0.0
    )

    incremental_lag_edge = max(
        0.0,
        abs(best.correlation)
        - abs(contemporaneous),
    )

    signs = {
        _direction(
            item.correlation
        )
        for item in evidence
        if abs(
            item.correlation
        ) >= 0.05
    }

    sign_change = (
        len(signs) > 1
    )

    delayed_bonus = (
        1.25
        if best.lag > 0
        else 1.0
    )

    sign_change_bonus = (
        1.20
        if sign_change
        else 1.0
    )

    score = (
        abs(best.correlation)
        * (
            1.0
            + incremental_lag_edge
        )
        * delayed_bonus
        * sign_change_bonus
        * math.sqrt(best.n)
    )

    return TimeSeriesDiscovery(
        feature=feature,
        horizon=horizon,
        evidence=tuple(evidence),
        best_lag=best.lag,
        best_correlation=(
            best.correlation
        ),
        contemporaneous_correlation=(
            contemporaneous
        ),
        incremental_lag_edge=(
            incremental_lag_edge
        ),
        sign_change=sign_change,
        direction=_direction(
            best.correlation
        ),
        score=score,
        independent_time_units=(
            best.independent_time_units
        ),
        ancestry=tuple(
            sorted(ancestry)
        ),
    )


def discover_lag_structures(
    rows: Iterable[
        UnifiedResearchRow
    ],
    *,
    feature_names: Iterable[str],
    horizons: tuple[int, ...] = (
        1,
        5,
        10,
        20,
    ),
    lags: tuple[int, ...] = (
        0,
        1,
        2,
        3,
        5,
        10,
    ),
    min_samples: int = 30,
    min_best_correlation: float = 0.10,
    max_features: int = 30,
    max_results: int = 50,
) -> list[TimeSeriesDiscovery]:
    rows = list(rows)

    names = list(
        dict.fromkeys(
            feature_names
        )
    )[:max_features]

    discoveries = []

    for feature in names:
        for horizon in horizons:
            result = (
                evaluate_lag_structure(
                    rows,
                    feature=feature,
                    horizon=horizon,
                    lags=lags,
                    min_samples=min_samples,
                )
            )

            if result is None:
                continue

            if (
                abs(
                    result.best_correlation
                )
                < min_best_correlation
            ):
                continue

            discoveries.append(
                result
            )

    discoveries.sort(
        key=lambda item: (
            item.score,
            item.incremental_lag_edge,
            abs(
                item.best_correlation
            ),
        ),
        reverse=True,
    )

    return discoveries[
        :max_results
    ]
