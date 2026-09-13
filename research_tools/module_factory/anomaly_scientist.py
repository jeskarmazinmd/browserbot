"""
Anomaly scientist for Module Factory.

Question:
    Do unusual multivariate feature states have systematically
    different future outcomes?

Anomaly detection uses FEATURES ONLY. Forward outcomes never affect
which observations are classified as anomalous.

Method:
    - standardize a bounded feature set
    - compute multivariate squared distance from the center
    - classify the highest-scoring observations as anomalies
    - compare their future outcome distribution with ordinary states

This deliberately searches for joint unusualness rather than requiring
one preselected feature to be extreme.

No predictive direction is specified in advance.
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


def _mean(values: list[float]) -> float:
    if not values:
        return math.nan
    return sum(values) / len(values)


def _std(values: list[float]) -> float:
    if len(values) < 2:
        return math.nan

    mean = _mean(values)

    variance = sum(
        (value - mean) ** 2
        for value in values
    ) / len(values)

    return math.sqrt(variance)


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
class AnomalyDiscovery:
    features: tuple[str, ...]
    horizon: int
    anomaly_quantile: float
    anomaly_threshold: float
    move_threshold: float
    n: int
    n_anomaly: int
    n_normal: int
    anomaly_mean: float
    normal_mean: float
    anomaly_positive_probability: float
    normal_positive_probability: float
    anomaly_large_move_probability: float
    normal_large_move_probability: float
    mean_effect: float
    directional_effect: float
    large_move_effect: float
    dominant_effect: str
    direction: int
    score: float
    independent_time_units: int
    ancestry: tuple[str, ...]

    @property
    def discovery_id(self) -> str:
        payload = (
            ",".join(self.features)
            + f"|{self.horizon}|"
            + f"{self.anomaly_quantile:.6f}"
        )

        digest = hashlib.sha256(
            payload.encode()
        ).hexdigest()[:16]

        return f"anomaly:{digest}"


def evaluate_anomaly_state(
    rows: Iterable[
        UnifiedResearchRow
    ],
    *,
    features: Iterable[str],
    horizon: int,
    anomaly_quantile: float = 0.90,
    move_quantile: float = 0.80,
    min_anomaly_samples: int = 30,
    max_features: int = 8,
) -> AnomalyDiscovery | None:
    features = tuple(
        dict.fromkeys(features)
    )

    if not features:
        raise ValueError(
            "at least one feature is required"
        )

    if len(features) > max_features:
        raise ValueError(
            "too many anomaly features"
        )

    if not (
        0.50
        < anomaly_quantile
        < 1.0
    ):
        raise ValueError(
            "anomaly_quantile must satisfy "
            "0.5 < q < 1"
        )

    if not (
        0.50
        < move_quantile
        < 1.0
    ):
        raise ValueError(
            "move_quantile must satisfy "
            "0.5 < q < 1"
        )

    observations = []
    observation_minutes = []
    ancestry = set()

    for row in rows:
        values = [
            row.feature(feature)
            for feature in features
        ]

        outcome = row.outcome(
            horizon
        )

        if not (
            all(
                _finite(value)
                for value in values
            )
            and _finite(outcome)
        ):
            continue

        observations.append(
            (values, outcome)
        )
        observation_minutes.append(
            row.minute
        )

        for feature in features:
            ancestry.update(
                row.ancestry(feature)
            )

    if (
        len(observations)
        < 2 * min_anomaly_samples
    ):
        return None

    columns = [
        [
            values[index]
            for values, _
            in observations
        ]
        for index
        in range(len(features))
    ]

    means = [
        _mean(column)
        for column in columns
    ]

    stds = [
        _std(column)
        for column in columns
    ]

    usable = [
        index
        for index, std
        in enumerate(stds)
        if (
            _finite(std)
            and std > 1e-12
        )
    ]

    if not usable:
        return None

    scores = []

    for values, _ in observations:
        squared_distance = sum(
            (
                (
                    values[index]
                    - means[index]
                )
                / stds[index]
            ) ** 2
            for index in usable
        )

        scores.append(
            squared_distance
        )

    anomaly_threshold = _quantile(
        scores,
        anomaly_quantile,
    )

    if not _finite(
        anomaly_threshold
    ):
        return None

    anomaly_outcomes = []
    normal_outcomes = []
    anomaly_minutes = set()

    for (
        score,
        (_, outcome),
        minute,
    ) in zip(
        scores,
        observations,
        observation_minutes,
    ):
        if score >= anomaly_threshold:
            anomaly_outcomes.append(
                outcome
            )
            anomaly_minutes.add(
                minute
            )
        else:
            normal_outcomes.append(
                outcome
            )

    if (
        len(anomaly_outcomes)
        < min_anomaly_samples
        or len(normal_outcomes)
        < min_anomaly_samples
    ):
        return None

    all_outcomes = [
        outcome
        for _, outcome
        in observations
    ]

    move_threshold = _quantile(
        [
            abs(outcome)
            for outcome
            in all_outcomes
        ],
        move_quantile,
    )

    anomaly_mean = _mean(
        anomaly_outcomes
    )

    normal_mean = _mean(
        normal_outcomes
    )

    anomaly_positive = (
        _positive_probability(
            anomaly_outcomes
        )
    )

    normal_positive = (
        _positive_probability(
            normal_outcomes
        )
    )

    anomaly_large = (
        _large_move_probability(
            anomaly_outcomes,
            move_threshold,
        )
    )

    normal_large = (
        _large_move_probability(
            normal_outcomes,
            move_threshold,
        )
    )

    outcome_scale = max(
        _mean(
            [
                abs(outcome)
                for outcome
                in all_outcomes
            ]
        ),
        1e-12,
    )

    mean_effect = (
        abs(
            anomaly_mean
            - normal_mean
        )
        / outcome_scale
    )

    directional_effect = abs(
        anomaly_positive
        - normal_positive
    )

    large_move_effect = abs(
        anomaly_large
        - normal_large
    )

    effects = {
        "mean": mean_effect,
        "direction": (
            directional_effect
        ),
        "large_move": (
            large_move_effect
        ),
    }

    dominant_effect = max(
        effects,
        key=effects.get,
    )

    direction = (
        1
        if anomaly_mean
        > normal_mean
        else -1
    )

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
            len(anomaly_outcomes)
        )
    )

    return AnomalyDiscovery(
        features=features,
        horizon=horizon,
        anomaly_quantile=(
            anomaly_quantile
        ),
        anomaly_threshold=(
            anomaly_threshold
        ),
        move_threshold=(
            move_threshold
        ),
        n=len(observations),
        n_anomaly=len(
            anomaly_outcomes
        ),
        n_normal=len(
            normal_outcomes
        ),
        anomaly_mean=(
            anomaly_mean
        ),
        normal_mean=(
            normal_mean
        ),
        anomaly_positive_probability=(
            anomaly_positive
        ),
        normal_positive_probability=(
            normal_positive
        ),
        anomaly_large_move_probability=(
            anomaly_large
        ),
        normal_large_move_probability=(
            normal_large
        ),
        mean_effect=mean_effect,
        directional_effect=(
            directional_effect
        ),
        large_move_effect=(
            large_move_effect
        ),
        dominant_effect=(
            dominant_effect
        ),
        direction=direction,
        score=score,
        independent_time_units=len(
            anomaly_minutes
        ),
        ancestry=tuple(
            sorted(ancestry)
        ),
    )


def discover_anomaly_states(
    rows: Iterable[
        UnifiedResearchRow
    ],
    *,
    feature_groups: Iterable[
        Iterable[str]
    ],
    horizons: tuple[int, ...] = (
        1,
        5,
        10,
        20,
    ),
    anomaly_quantiles: tuple[
        float,
        ...
    ] = (
        0.90,
        0.95,
    ),
    move_quantile: float = 0.80,
    min_anomaly_samples: int = 30,
    min_effect: float = 0.10,
    max_groups: int = 40,
    max_features_per_group: int = 8,
    max_results: int = 50,
) -> list[AnomalyDiscovery]:
    rows = list(rows)

    groups = []
    seen = set()

    for group in feature_groups:
        canonical = tuple(
            sorted(
                dict.fromkeys(group)
            )
        )

        if not canonical:
            continue

        if (
            len(canonical)
            > max_features_per_group
        ):
            continue

        if canonical in seen:
            continue

        seen.add(canonical)
        groups.append(canonical)

        if len(groups) >= max_groups:
            break

    discoveries = []

    for features in groups:
        for horizon in horizons:
            for anomaly_quantile in (
                anomaly_quantiles
            ):
                result = (
                    evaluate_anomaly_state(
                        rows,
                        features=features,
                        horizon=horizon,
                        anomaly_quantile=(
                            anomaly_quantile
                        ),
                        move_quantile=(
                            move_quantile
                        ),
                        min_anomaly_samples=(
                            min_anomaly_samples
                        ),
                        max_features=(
                            max_features_per_group
                        ),
                    )
                )

                if result is None:
                    continue

                strongest = max(
                    result.mean_effect,
                    result.directional_effect,
                    result.large_move_effect,
                )

                if strongest < min_effect:
                    continue

                discoveries.append(
                    result
                )

    discoveries.sort(
        key=lambda item: (
            item.score,
            max(
                item.mean_effect,
                item.directional_effect,
                item.large_move_effect,
            ),
        ),
        reverse=True,
    )

    return discoveries[
        :max_results
    ]
