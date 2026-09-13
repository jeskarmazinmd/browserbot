"""
Frozen statistical validation primitives.

No discovery search is allowed here.

Frozen:
- features / controls
- horizon
- lag
- regime/tail/anomaly thresholds
- direction(s)
- primary-effect definition

Permitted nuisance estimation on validation data:
- residual-regression coefficients for a fixed candidate/control set
- mean/std normalization for a fixed anomaly feature set

Those nuisance estimates do not alter hypothesis identity and do not
select alternative specifications.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable

from research_tools.module_factory.research_rows import (
    UnifiedResearchRow,
)
from research_tools.module_factory.residual_scientist import (
    evaluate_residual_relationship,
)


@dataclass(frozen=True)
class FrozenStatisticalResult:
    scientist: str
    primary_effect: float
    expected_positive: bool
    n_samples: int
    n_events: int
    independent_time_units: int
    metrics: dict[str, object]


def _finite(value: object) -> bool:
    return (
        isinstance(value, (int, float))
        and math.isfinite(float(value))
    )


def _mean(values):
    if not values:
        return math.nan
    return sum(values) / len(values)


def _std(values):
    if len(values) < 2:
        return math.nan
    mean = _mean(values)
    variance = sum(
        (value - mean) ** 2
        for value in values
    ) / (len(values) - 1)
    return math.sqrt(max(0.0, variance))


def _pearson(xs, ys):
    if len(xs) < 3 or len(xs) != len(ys):
        return math.nan

    mx = _mean(xs)
    my = _mean(ys)

    dx = [x - mx for x in xs]
    dy = [y - my for y in ys]

    vx = sum(x * x for x in dx)
    vy = sum(y * y for y in dy)

    if vx <= 1e-18 or vy <= 1e-18:
        return math.nan

    return sum(
        x * y
        for x, y in zip(dx, dy)
    ) / math.sqrt(vx * vy)


def validate_fixed_regime(
    rows: Iterable[UnifiedResearchRow],
    *,
    feature: str,
    regime_feature: str,
    horizon: int,
    low_threshold: float,
    high_threshold: float,
    direction_low: int,
    direction_high: int,
) -> FrozenStatisticalResult:
    """
    Validate fixed Aug28 regime boundaries.

    Primary effect is directional correlation strength averaged across
    the two frozen regimes:
        low_direction * corr_low
        high_direction * corr_high
    Positive means the frozen sign pattern reproduced.
    """

    low_x = []
    low_y = []
    high_x = []
    high_y = []

    low_minutes = set()
    high_minutes = set()

    for row in rows:
        x = row.feature(feature)
        state = row.feature(regime_feature)
        outcome = row.outcome(horizon)

        if not (
            _finite(x)
            and _finite(state)
            and _finite(outcome)
        ):
            continue

        if state <= low_threshold:
            low_x.append(float(x))
            low_y.append(float(outcome))
            low_minutes.add(row.minute)

        elif state >= high_threshold:
            high_x.append(float(x))
            high_y.append(float(outcome))
            high_minutes.add(row.minute)

    low_corr = _pearson(low_x, low_y)
    high_corr = _pearson(high_x, high_y)

    if not (
        _finite(low_corr)
        and _finite(high_corr)
    ):
        primary = math.nan
    else:
        primary = 0.5 * (
            direction_low * low_corr
            + direction_high * high_corr
        )

    return FrozenStatisticalResult(
        scientist="regime",
        primary_effect=primary,
        expected_positive=True,
        n_samples=len(low_x) + len(high_x),
        n_events=min(len(low_x), len(high_x)),
        independent_time_units=min(
            len(low_minutes),
            len(high_minutes),
        ),
        metrics={
            "low_correlation": low_corr,
            "high_correlation": high_corr,
            "sign_reversal":
                (
                    _finite(low_corr)
                    and _finite(high_corr)
                    and low_corr * high_corr < 0
                ),
            "low_threshold": low_threshold,
            "high_threshold": high_threshold,
            "direction_low": direction_low,
            "direction_high": direction_high,
        },
    )


def validate_fixed_lag(
    rows: Iterable[UnifiedResearchRow],
    *,
    feature: str,
    horizon: int,
    lag: int,
    direction: int,
) -> FrozenStatisticalResult:
    """
    Validate exactly one frozen lag.

    No best-lag search occurs.
    """
    if lag < 0:
        raise ValueError("lag must be non-negative")

    grouped = {}

    for row in rows:
        grouped.setdefault(
            row.symbol,
            [],
        ).append(row)

    xs = []
    ys = []
    minutes = set()

    for symbol_rows in grouped.values():
        symbol_rows.sort(
            key=lambda row: row.minute
        )

        for index, target_row in enumerate(
            symbol_rows
        ):
            source_index = index - lag

            if source_index < 0:
                continue

            source = symbol_rows[source_index]

            x = source.feature(feature)
            outcome = target_row.outcome(horizon)

            if not (
                _finite(x)
                and _finite(outcome)
            ):
                continue

            xs.append(float(x))
            ys.append(float(outcome))
            minutes.add(target_row.minute)

    correlation = _pearson(xs, ys)

    primary = (
        direction * correlation
        if _finite(correlation)
        else math.nan
    )

    return FrozenStatisticalResult(
        scientist="time_series",
        primary_effect=primary,
        expected_positive=True,
        n_samples=len(xs),
        n_events=len(xs),
        independent_time_units=len(minutes),
        metrics={
            "lag": lag,
            "correlation": correlation,
            "direction": direction,
        },
    )


def validate_fixed_distribution_mean(
    rows: Iterable[UnifiedResearchRow],
    *,
    feature: str,
    horizon: int,
    low_threshold: float,
    high_threshold: float,
    direction_low: int,
    direction_high: int,
) -> FrozenStatisticalResult:
    """
    Validate the frozen distribution 'mean' state.

    Positive primary effect means both tail means, on average,
    reproduce their frozen directions.
    """

    low = []
    high = []
    low_minutes = set()
    high_minutes = set()

    for row in rows:
        value = row.feature(feature)
        outcome = row.outcome(horizon)

        if not (
            _finite(value)
            and _finite(outcome)
        ):
            continue

        if value <= low_threshold:
            low.append(float(outcome))
            low_minutes.add(row.minute)

        elif value >= high_threshold:
            high.append(float(outcome))
            high_minutes.add(row.minute)

    low_mean = _mean(low)
    high_mean = _mean(high)

    if not (
        _finite(low_mean)
        and _finite(high_mean)
    ):
        primary = math.nan
    else:
        primary = 0.5 * (
            direction_low * low_mean
            + direction_high * high_mean
        )

    return FrozenStatisticalResult(
        scientist="distribution",
        primary_effect=primary,
        expected_positive=True,
        n_samples=len(low) + len(high),
        n_events=min(len(low), len(high)),
        independent_time_units=min(
            len(low_minutes),
            len(high_minutes),
        ),
        metrics={
            "low_mean": low_mean,
            "high_mean": high_mean,
            "low_threshold": low_threshold,
            "high_threshold": high_threshold,
            "direction_low": direction_low,
            "direction_high": direction_high,
        },
    )


def validate_fixed_residual_claim(
    rows: Iterable[UnifiedResearchRow],
    *,
    candidate: str,
    controls: tuple[str, ...],
    horizon: int,
    expected_direction: int,
) -> FrozenStatisticalResult:
    """
    Candidate and controls are frozen.

    Regression coefficients are validation-sample nuisance estimates.
    No control or direction selection occurs.
    """

    rows = tuple(rows)

    result = evaluate_residual_relationship(
        rows,
        candidate=candidate,
        controls=controls,
        horizon=horizon,
        min_samples=30,
        max_controls=len(controls),
    )

    if result is None:
        return FrozenStatisticalResult(
            scientist="residual",
            primary_effect=math.nan,
            expected_positive=True,
            n_samples=0,
            n_events=0,
            independent_time_units=0,
            metrics={
                "evaluation_failed": True,
                "candidate": candidate,
                "controls": controls,
            },
        )

    primary = (
        expected_direction
        * result.residual_correlation
    )

    return FrozenStatisticalResult(
        scientist="residual",
        primary_effect=primary,
        expected_positive=True,
        n_samples=result.n,
        n_events=result.n,
        independent_time_units=(
            result.independent_time_units
        ),
        metrics={
            "candidate": candidate,
            "controls": controls,
            "raw_correlation":
                result.raw_correlation,
            "residual_correlation":
                result.residual_correlation,
            "incremental_clarity":
                result.incremental_clarity,
            "expected_direction":
                expected_direction,
        },
    )


def validate_fixed_anomaly_large_move(
    rows: Iterable[UnifiedResearchRow],
    *,
    features: tuple[str, ...],
    horizon: int,
    anomaly_threshold: float,
    move_threshold: float,
    expected_direction: int,
) -> FrozenStatisticalResult:
    """
    Validate the frozen anomaly large-move claim.

    Feature means/stds are nuisance normalization parameters estimated
    from the validation sample.

    Crucially:
    - feature set is frozen
    - squared-distance cutoff is frozen
    - forward-return move cutoff is frozen
    - horizon is frozen
    - no validation quantile is selected

    Primary effect:
        P(large move | anomaly) - P(large move | normal)

    Secondary directional metric checks the frozen direction.
    """

    rows = tuple(rows)

    complete = []

    for row in rows:
        values = tuple(
            row.feature(feature)
            for feature in features
        )
        outcome = row.outcome(horizon)

        if not (
            all(_finite(v) for v in values)
            and _finite(outcome)
        ):
            continue

        complete.append(
            (
                row,
                tuple(float(v) for v in values),
                float(outcome),
            )
        )

    if not complete:
        return FrozenStatisticalResult(
            scientist="anomaly",
            primary_effect=math.nan,
            expected_positive=True,
            n_samples=0,
            n_events=0,
            independent_time_units=0,
            metrics={"evaluation_failed": True},
        )

    columns = [
        [
            values[index]
            for _, values, _ in complete
        ]
        for index in range(len(features))
    ]

    means = tuple(
        _mean(column)
        for column in columns
    )

    stds = tuple(
        _std(column)
        for column in columns
    )

    anomaly_outcomes = []
    normal_outcomes = []
    anomaly_minutes = set()

    for row, values, outcome in complete:
        distance = 0.0
        usable = False

        for value, mean, std in zip(
            values,
            means,
            stds,
        ):
            if not (
                _finite(std)
                and std > 1e-12
            ):
                continue

            usable = True

            distance += (
                (value - mean) / std
            ) ** 2

        if not usable:
            continue

        if distance >= anomaly_threshold:
            anomaly_outcomes.append(outcome)
            anomaly_minutes.add(row.minute)
        else:
            normal_outcomes.append(outcome)

    if (
        not anomaly_outcomes
        or not normal_outcomes
    ):
        return FrozenStatisticalResult(
            scientist="anomaly",
            primary_effect=math.nan,
            expected_positive=True,
            n_samples=len(complete),
            n_events=len(anomaly_outcomes),
            independent_time_units=(
                len(anomaly_minutes)
            ),
            metrics={
                "evaluation_failed": True,
                "reason": "empty anomaly or normal set",
            },
        )

    anomaly_large = _mean([
        1.0
        if abs(outcome) >= move_threshold
        else 0.0
        for outcome in anomaly_outcomes
    ])

    normal_large = _mean([
        1.0
        if abs(outcome) >= move_threshold
        else 0.0
        for outcome in normal_outcomes
    ])

    anomaly_mean = _mean(
        anomaly_outcomes
    )
    normal_mean = _mean(
        normal_outcomes
    )

    primary = (
        anomaly_large
        - normal_large
    )

    directional_difference = (
        expected_direction
        * (
            anomaly_mean
            - normal_mean
        )
    )

    return FrozenStatisticalResult(
        scientist="anomaly",
        primary_effect=primary,
        expected_positive=True,
        n_samples=len(complete),
        n_events=len(anomaly_outcomes),
        independent_time_units=(
            len(anomaly_minutes)
        ),
        metrics={
            "features": features,
            "anomaly_threshold":
                anomaly_threshold,
            "move_threshold":
                move_threshold,
            "anomaly_large_move_probability":
                anomaly_large,
            "normal_large_move_probability":
                normal_large,
            "anomaly_mean":
                anomaly_mean,
            "normal_mean":
                normal_mean,
            "directional_difference":
                directional_difference,
            "expected_direction":
                expected_direction,
            "n_anomaly":
                len(anomaly_outcomes),
            "n_normal":
                len(normal_outcomes),
            "normalization":
                "validation-sample-nuisance",
        },
    )
