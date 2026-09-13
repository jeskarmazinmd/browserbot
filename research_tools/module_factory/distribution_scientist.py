"""
Distribution scientist for Module Factory.

Question:
    Does the distribution of future outcomes change when a feature
    enters an unusual part of its own distribution?

This scientist studies:
    - low/high feature tails
    - changes in future absolute-move probability
    - changes in future directional probability
    - changes in future mean outcome
    - asymmetric behavior between opposite feature tails

It does not assume that high or low feature values are bullish,
bearish, volatile, or quiet. Direction is empirical.

No real-data discovery is performed here.
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


def _mean(
    values: list[float],
) -> float:
    if not values:
        return math.nan

    return sum(values) / len(values)


def _quantile(
    values: list[float],
    q: float,
) -> float:
    if not values:
        return math.nan

    ordered = sorted(values)

    if len(ordered) == 1:
        return ordered[0]

    position = (
        (len(ordered) - 1) * q
    )

    lower = int(
        math.floor(position)
    )
    upper = int(
        math.ceil(position)
    )

    if lower == upper:
        return ordered[lower]

    weight = position - lower

    return (
        ordered[lower]
        * (1.0 - weight)
        + ordered[upper]
        * weight
    )


def _positive_probability(
    values: list[float],
) -> float:
    if not values:
        return math.nan

    return sum(
        value > 0.0
        for value in values
    ) / len(values)


def _large_move_probability(
    values: list[float],
    threshold: float,
) -> float:
    if not values:
        return math.nan

    return sum(
        abs(value) >= threshold
        for value in values
    ) / len(values)


@dataclass(frozen=True)
class DistributionDiscovery:
    feature: str
    horizon: int
    tail_quantile: float
    low_threshold: float
    high_threshold: float
    move_threshold: float
    n_all: int
    n_low: int
    n_high: int
    global_mean: float
    low_mean: float
    high_mean: float
    global_positive_probability: float
    low_positive_probability: float
    high_positive_probability: float
    global_large_move_probability: float
    low_large_move_probability: float
    high_large_move_probability: float
    mean_asymmetry: float
    directional_asymmetry: float
    move_asymmetry: float
    dominant_effect: str
    direction_low: int
    direction_high: int
    score: float
    independent_time_units: int
    ancestry: tuple[str, ...]

    @property
    def discovery_id(self) -> str:
        payload = (
            f"{self.feature}|"
            f"{self.horizon}|"
            f"{self.tail_quantile:.6f}"
        )

        digest = hashlib.sha256(
            payload.encode()
        ).hexdigest()[:16]

        return (
            f"distribution:{digest}"
        )


def evaluate_distribution_state(
    rows: Iterable[
        UnifiedResearchRow
    ],
    *,
    feature: str,
    horizon: int,
    tail_quantile: float = 0.20,
    move_quantile: float = 0.80,
    min_tail_samples: int = 30,
) -> DistributionDiscovery | None:
    if not (
        0.0
        < tail_quantile
        < 0.5
    ):
        raise ValueError(
            "tail_quantile must satisfy "
            "0 < q < 0.5"
        )

    if not (
        0.5
        < move_quantile
        < 1.0
    ):
        raise ValueError(
            "move_quantile must satisfy "
            "0.5 < q < 1"
        )

    observations = []
    ancestry = set()

    for row in rows:
        value = row.feature(
            feature
        )

        outcome = row.outcome(
            horizon
        )

        if not (
            _finite(value)
            and _finite(outcome)
        ):
            continue

        observations.append((value, outcome, row.minute))

        ancestry.update(
            row.ancestry(feature)
        )

    if (
        len(observations)
        < 2 * min_tail_samples
    ):
        return None

    feature_values = [
        value
        for value, _, _
        in observations
    ]

    outcomes = [
        outcome
        for _, outcome, _
        in observations
    ]

    low_threshold = _quantile(
        feature_values,
        tail_quantile,
    )

    high_threshold = _quantile(
        feature_values,
        1.0 - tail_quantile,
    )

    if not (
        _finite(low_threshold)
        and _finite(high_threshold)
        and low_threshold
        < high_threshold
    ):
        return None

    low_minutes = {minute for value, _, minute in observations if value <= low_threshold}
    high_minutes = {minute for value, _, minute in observations if value >= high_threshold}

    low_outcomes = [
        outcome
        for value, outcome, _
        in observations
        if value <= low_threshold
    ]

    high_outcomes = [
        outcome
        for value, outcome, _
        in observations
        if value >= high_threshold
    ]

    if (
        len(low_outcomes)
        < min_tail_samples
        or len(high_outcomes)
        < min_tail_samples
    ):
        return None

    absolute_outcomes = [
        abs(outcome)
        for outcome in outcomes
    ]

    move_threshold = _quantile(
        absolute_outcomes,
        move_quantile,
    )

    if not _finite(
        move_threshold
    ):
        return None

    global_mean = _mean(
        outcomes
    )

    low_mean = _mean(
        low_outcomes
    )

    high_mean = _mean(
        high_outcomes
    )

    global_positive = (
        _positive_probability(
            outcomes
        )
    )

    low_positive = (
        _positive_probability(
            low_outcomes
        )
    )

    high_positive = (
        _positive_probability(
            high_outcomes
        )
    )

    global_large = (
        _large_move_probability(
            outcomes,
            move_threshold,
        )
    )

    low_large = (
        _large_move_probability(
            low_outcomes,
            move_threshold,
        )
    )

    high_large = (
        _large_move_probability(
            high_outcomes,
            move_threshold,
        )
    )

    mean_scale = max(
        _mean(absolute_outcomes),
        1e-12,
    )

    mean_asymmetry = (
        abs(
            high_mean
            - low_mean
        )
        / mean_scale
    )

    directional_asymmetry = abs(
        high_positive
        - low_positive
    )

    move_asymmetry = abs(
        high_large
        - low_large
    )

    effects = {
        "mean": mean_asymmetry,
        "direction": (
            directional_asymmetry
        ),
        "large_move": (
            move_asymmetry
        ),
    }

    dominant_effect = max(
        effects,
        key=effects.get,
    )

    direction_low = (
        1
        if low_mean > 0.0
        else -1
    )

    direction_high = (
        1
        if high_mean > 0.0
        else -1
    )

    # Give each kind of distributional change a chance to matter.
    # The largest effect drives discovery, while secondary effects
    # contribute modestly.
    ordered_effects = sorted(
        effects.values(),
        reverse=True,
    )

    primary = ordered_effects[0]
    secondary = sum(
        ordered_effects[1:]
    )

    score = (
        (
            primary
            + 0.25 * secondary
        )
        * math.sqrt(
            min(
                len(low_outcomes),
                len(high_outcomes),
            )
        )
    )

    return DistributionDiscovery(
        feature=feature,
        horizon=horizon,
        tail_quantile=(
            tail_quantile
        ),
        low_threshold=(
            low_threshold
        ),
        high_threshold=(
            high_threshold
        ),
        move_threshold=(
            move_threshold
        ),
        n_all=len(outcomes),
        n_low=len(low_outcomes),
        n_high=len(high_outcomes),
        global_mean=global_mean,
        low_mean=low_mean,
        high_mean=high_mean,
        global_positive_probability=(
            global_positive
        ),
        low_positive_probability=(
            low_positive
        ),
        high_positive_probability=(
            high_positive
        ),
        global_large_move_probability=(
            global_large
        ),
        low_large_move_probability=(
            low_large
        ),
        high_large_move_probability=(
            high_large
        ),
        mean_asymmetry=(
            mean_asymmetry
        ),
        directional_asymmetry=(
            directional_asymmetry
        ),
        move_asymmetry=(
            move_asymmetry
        ),
        dominant_effect=(
            dominant_effect
        ),
        direction_low=(
            direction_low
        ),
        direction_high=(
            direction_high
        ),
        score=score,
        independent_time_units=min(
            len(low_minutes),
            len(high_minutes),
        ),
        ancestry=tuple(
            sorted(ancestry)
        ),
    )


def discover_distribution_states(
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
    tail_quantiles: tuple[
        float,
        ...
    ] = (
        0.10,
        0.20,
        0.25,
    ),
    move_quantile: float = 0.80,
    min_tail_samples: int = 30,
    min_effect: float = 0.10,
    max_features: int = 30,
    max_results: int = 50,
) -> list[DistributionDiscovery]:
    rows = list(rows)

    names = list(
        dict.fromkeys(
            feature_names
        )
    )[:max_features]

    discoveries = []

    for feature in names:
        for horizon in horizons:
            for tail_quantile in (
                tail_quantiles
            ):
                result = (
                    evaluate_distribution_state(
                        rows,
                        feature=feature,
                        horizon=horizon,
                        tail_quantile=(
                            tail_quantile
                        ),
                        move_quantile=(
                            move_quantile
                        ),
                        min_tail_samples=(
                            min_tail_samples
                        ),
                    )
                )

                if result is None:
                    continue

                strongest_effect = max(
                    result.mean_asymmetry,
                    result.directional_asymmetry,
                    result.move_asymmetry,
                )

                if (
                    strongest_effect
                    < min_effect
                ):
                    continue

                discoveries.append(
                    result
                )

    discoveries.sort(
        key=lambda item: (
            item.score,
            max(
                item.mean_asymmetry,
                item.directional_asymmetry,
                item.move_asymmetry,
            ),
        ),
        reverse=True,
    )

    return discoveries[
        :max_results
    ]
