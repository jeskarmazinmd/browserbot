"""
Common falsification evidence engine for Module Factory.

Purpose
-------
Take already-defined evaluation observations for a FROZEN hypothesis
and independently calculate diagnostics used by the validation policy.

This module does NOT redesign hypotheses.

It measures:
    - sample and event count
    - raw and net-of-cost effect
    - symbol concentration
    - time concentration
    - lag-1 dependence
    - effective sample size
    - parameter-neighborhood stability
    - multiple-testing adjusted p-value

The scientist's discovery score is deliberately irrelevant here.

No market data is loaded by this module.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable

from research_tools.module_factory.hypothesis_protocol import (
    FrozenHypothesis,
    ValidationEvidence,
)


def _finite(value: float) -> bool:
    return math.isfinite(value)


def _mean(
    values: list[float],
) -> float:
    if not values:
        return math.nan

    return sum(values) / len(values)


def _pearson(
    xs: list[float],
    ys: list[float],
) -> float:
    if len(xs) < 3:
        return math.nan

    mx = _mean(xs)
    my = _mean(ys)

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

    if (
        vx <= 1e-18
        or vy <= 1e-18
    ):
        return math.nan

    return sum(
        left * right
        for left, right
        in zip(dx, dy)
    ) / math.sqrt(
        vx * vy
    )


def _normal_two_sided_p(
    z: float,
) -> float:
    return math.erfc(
        abs(z)
        / math.sqrt(2.0)
    )


@dataclass(frozen=True)
class EvaluationObservation:
    symbol: str
    time_bucket: str
    effect: float
    event: bool = True

    def __post_init__(self) -> None:
        if not self.symbol:
            raise ValueError(
                "symbol cannot be empty"
            )

        if not self.time_bucket:
            raise ValueError(
                "time_bucket cannot be empty"
            )

        if not _finite(
            self.effect
        ):
            raise ValueError(
                "effect must be finite"
            )


@dataclass(frozen=True)
class FalsificationDiagnostics:
    n_samples: int
    n_events: int
    primary_effect: float
    net_effect: float
    symbol_concentration: float
    time_concentration: float
    lag1_dependence: float
    effective_sample_size: float
    parameter_stability: float
    raw_p_value: float
    adjusted_p_value: float


def _concentration(
    labels: list[str],
) -> float:
    if not labels:
        return 1.0

    counts = {}

    for label in labels:
        counts[label] = (
            counts.get(label, 0)
            + 1
        )

    return (
        max(counts.values())
        / len(labels)
    )


def _lag1_dependence(
    effects: list[float],
) -> float:
    if len(effects) < 4:
        return 0.0

    correlation = _pearson(
        effects[:-1],
        effects[1:],
    )

    if not _finite(
        correlation
    ):
        return 0.0

    return max(
        -0.99,
        min(
            0.99,
            correlation,
        ),
    )


def _effective_sample_size(
    n: int,
    lag1: float,
) -> float:
    if n <= 0:
        return 0.0

    # AR(1)-style approximation. Negative serial dependence can
    # increase nominal information, but we conservatively cap ESS
    # at the actual observation count.
    estimate = (
        n
        * (1.0 - lag1)
        / (1.0 + lag1)
    )

    return max(
        1.0,
        min(
            float(n),
            estimate,
        ),
    )


def _effect_p_value(
    effects: list[float],
    effective_n: float,
) -> float:
    if len(effects) < 2:
        return 1.0

    mean = _mean(effects)

    variance = sum(
        (value - mean) ** 2
        for value in effects
    ) / (
        len(effects) - 1
    )

    if variance <= 1e-18:
        return (
            0.0
            if abs(mean) > 1e-18
            else 1.0
        )

    standard_error = math.sqrt(
        variance
        / max(
            effective_n,
            1.0,
        )
    )

    if standard_error <= 1e-18:
        return 1.0

    z = mean / standard_error

    return _normal_two_sided_p(
        z
    )


def _bonferroni(
    p_value: float,
    tests_considered: int,
) -> float:
    return min(
        1.0,
        p_value
        * max(
            1,
            tests_considered,
        ),
    )


def _parameter_stability(
    primary_effect: float,
    neighborhood_effects: Iterable[
        float
    ],
) -> float:
    neighbors = [
        value
        for value
        in neighborhood_effects
        if _finite(value)
    ]

    if not neighbors:
        return 0.0

    if abs(
        primary_effect
    ) <= 1e-18:
        return 0.0

    direction = (
        1
        if primary_effect > 0.0
        else -1
    )

    directional_scores = []

    for value in neighbors:
        if (
            value * direction
            <= 0.0
        ):
            directional_scores.append(
                0.0
            )
            continue

        magnitude_ratio = min(
            1.0,
            abs(value)
            / abs(primary_effect),
        )

        directional_scores.append(
            magnitude_ratio
        )

    return _mean(
        directional_scores
    )


def calculate_falsification_diagnostics(
    observations: Iterable[
        EvaluationObservation
    ],
    *,
    neighborhood_effects: Iterable[
        float
    ],
    tests_considered: int,
    estimated_cost_bps: float,
) -> FalsificationDiagnostics:
    if tests_considered < 1:
        raise ValueError(
            "tests_considered must be >= 1"
        )

    if estimated_cost_bps < 0.0:
        raise ValueError(
            "estimated_cost_bps must be >= 0"
        )

    observations = list(
        observations
    )

    if not observations:
        raise ValueError(
            "at least one observation is required"
        )

    effects = [
        observation.effect
        for observation
        in observations
    ]

    symbols = [
        observation.symbol
        for observation
        in observations
    ]

    time_buckets = [
        observation.time_bucket
        for observation
        in observations
    ]

    primary_effect = _mean(
        effects
    )

    direction = (
        1.0
        if primary_effect >= 0.0
        else -1.0
    )

    # effect is expressed in return units.
    # 1 bp = 0.0001 return.
    cost_return = (
        estimated_cost_bps
        * 0.0001
    )

    net_effect = (
        primary_effect
        - direction
        * cost_return
    )

    lag1 = _lag1_dependence(
        effects
    )

    effective_n = (
        _effective_sample_size(
            len(effects),
            lag1,
        )
    )

    raw_p = _effect_p_value(
        effects,
        effective_n,
    )

    adjusted_p = _bonferroni(
        raw_p,
        tests_considered,
    )

    return FalsificationDiagnostics(
        n_samples=len(
            observations
        ),
        n_events=sum(
            observation.event
            for observation
            in observations
        ),
        primary_effect=(
            primary_effect
        ),
        net_effect=net_effect,
        symbol_concentration=(
            _concentration(
                symbols
            )
        ),
        time_concentration=(
            _concentration(
                time_buckets
            )
        ),
        lag1_dependence=lag1,
        effective_sample_size=(
            effective_n
        ),
        parameter_stability=(
            _parameter_stability(
                primary_effect,
                neighborhood_effects,
            )
        ),
        raw_p_value=raw_p,
        adjusted_p_value=(
            adjusted_p
        ),
    )


def build_validation_evidence(
    frozen: FrozenHypothesis,
    *,
    dataset_id: str,
    observations: Iterable[
        EvaluationObservation
    ],
    neighborhood_effects: Iterable[
        float
    ],
    estimated_cost_bps: float,
    notes: Iterable[str] = (),
) -> ValidationEvidence:
    diagnostics = (
        calculate_falsification_diagnostics(
            observations,
            neighborhood_effects=(
                neighborhood_effects
            ),
            tests_considered=(
                frozen.specification
                .tests_considered
            ),
            estimated_cost_bps=(
                estimated_cost_bps
            ),
        )
    )

    return ValidationEvidence(
        hypothesis_id=(
            frozen.hypothesis_id
        ),
        dataset_id=dataset_id,
        specification_hash=(
            frozen.specification_hash
        ),
        n_samples=(
            diagnostics.n_samples
        ),
        n_events=(
            diagnostics.n_events
        ),
        primary_effect=(
            diagnostics.primary_effect
        ),
        adjusted_p_value=(
            diagnostics.adjusted_p_value
        ),
        symbol_concentration=(
            diagnostics.symbol_concentration
        ),
        time_concentration=(
            diagnostics.time_concentration
        ),
        parameter_stability=(
            diagnostics.parameter_stability
        ),
        estimated_cost_bps=(
            estimated_cost_bps
        ),
        effective_sample_size=(
            diagnostics.effective_sample_size
        ),
        net_effect=(
            diagnostics.net_effect
        ),
        lag1_dependence=(
            diagnostics.lag1_dependence
        ),
        notes=tuple(notes),
    )
