"""
Residual scientist for Module Factory.

Question:
    After removing information explained by known control features,
    does another feature explain structure that remains?

The scientist residualizes BOTH:
    - the future outcome against controls
    - the candidate feature against controls

Testing residual(candidate) against residual(outcome) measures
incremental linear information rather than merely rediscovering a
feature correlated with an existing explanation.

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


def _mean(
    values: list[float],
) -> float:
    return sum(values) / len(values)


def _pearson(
    xs: list[float],
    ys: list[float],
) -> float:
    if len(xs) < 3:
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


def _solve_linear_system(
    matrix: list[list[float]],
    vector: list[float],
) -> list[float] | None:
    """
    Small Gaussian-elimination solver with partial pivoting.

    The residual scientist deliberately keeps the number of controls
    bounded, so a dependency-free solver is sufficient here.
    """
    n = len(vector)

    augmented = [
        list(matrix[i])
        + [vector[i]]
        for i in range(n)
    ]

    for column in range(n):
        pivot = max(
            range(column, n),
            key=lambda row: abs(
                augmented[row][column]
            ),
        )

        if (
            abs(
                augmented[pivot][column]
            )
            <= 1e-12
        ):
            return None

        if pivot != column:
            augmented[
                column
            ], augmented[
                pivot
            ] = (
                augmented[pivot],
                augmented[column],
            )

        divisor = augmented[
            column
        ][column]

        augmented[column] = [
            value / divisor
            for value
            in augmented[column]
        ]

        for row in range(n):
            if row == column:
                continue

            factor = augmented[
                row
            ][column]

            if abs(factor) <= 1e-18:
                continue

            augmented[row] = [
                left
                - factor * right
                for left, right
                in zip(
                    augmented[row],
                    augmented[column],
                )
            ]

    return [
        augmented[i][-1]
        for i in range(n)
    ]


def _residualize(
    target: list[float],
    controls: list[
        list[float]
    ],
) -> list[float] | None:
    if not target:
        return None

    if not controls:
        mean = _mean(target)

        return [
            value - mean
            for value in target
        ]

    n = len(target)
    p = len(controls) + 1

    design = []

    for i in range(n):
        design.append(
            [1.0]
            + [
                control[i]
                for control
                in controls
            ]
        )

    xtx = [
        [0.0] * p
        for _ in range(p)
    ]

    xty = [0.0] * p

    for row, y in zip(
        design,
        target,
    ):
        for i in range(p):
            xty[i] += (
                row[i] * y
            )

            for j in range(p):
                xtx[i][j] += (
                    row[i]
                    * row[j]
                )

    # Tiny ridge stabilization protects against nearly redundant
    # controls without materially changing the fitted explanation.
    for i in range(1, p):
        xtx[i][i] += 1e-10

    coefficients = (
        _solve_linear_system(
            xtx,
            xty,
        )
    )

    if coefficients is None:
        return None

    residuals = []

    for row, y in zip(
        design,
        target,
    ):
        fitted = sum(
            coefficient * value
            for coefficient, value
            in zip(
                coefficients,
                row,
            )
        )

        residuals.append(
            y - fitted
        )

    return residuals


@dataclass(frozen=True)
class ResidualDiscovery:
    candidate: str
    controls: tuple[str, ...]
    horizon: int
    n: int
    raw_correlation: float
    residual_correlation: float
    incremental_clarity: float
    direction: int
    score: float
    independent_time_units: int
    ancestry: tuple[str, ...]

    @property
    def discovery_id(self) -> str:
        controls = ",".join(
            self.controls
        )

        payload = (
            f"{self.candidate}|"
            f"{controls}|"
            f"{self.horizon}"
        )

        digest = hashlib.sha256(
            payload.encode()
        ).hexdigest()[:16]

        return f"residual:{digest}"


def evaluate_residual_relationship(
    rows: Iterable[
        UnifiedResearchRow
    ],
    *,
    candidate: str,
    controls: Iterable[str],
    horizon: int,
    min_samples: int = 30,
    max_controls: int = 8,
) -> ResidualDiscovery | None:
    controls = tuple(
        dict.fromkeys(controls)
    )

    if candidate in controls:
        raise ValueError(
            "candidate cannot also "
            "be a control"
        )

    if len(controls) > max_controls:
        raise ValueError(
            "too many controls"
        )

    candidate_values = []
    outcomes = []
    control_columns = [
        []
        for _ in controls
    ]

    ancestry = set()
    usable_minutes = set()

    for row in rows:
        x = row.feature(candidate)
        outcome = row.outcome(
            horizon
        )

        control_values = [
            row.feature(control)
            for control in controls
        ]

        if not (
            _finite(x)
            and _finite(outcome)
            and all(
                _finite(value)
                for value
                in control_values
            )
        ):
            continue

        candidate_values.append(x)
        outcomes.append(outcome)
        usable_minutes.add(
            row.minute
        )

        for column, value in zip(
            control_columns,
            control_values,
        ):
            column.append(value)

        ancestry.update(
            row.ancestry(candidate)
        )

        for control in controls:
            ancestry.update(
                row.ancestry(control)
            )

    n = len(outcomes)

    if n < min_samples:
        return None

    raw_correlation = _pearson(
        candidate_values,
        outcomes,
    )

    residual_outcomes = _residualize(
        outcomes,
        control_columns,
    )

    residual_candidate = _residualize(
        candidate_values,
        control_columns,
    )

    if (
        residual_outcomes is None
        or residual_candidate is None
    ):
        return None

    residual_correlation = (
        _pearson(
            residual_candidate,
            residual_outcomes,
        )
    )

    if not _finite(
        residual_correlation
    ):
        return None

    if not _finite(raw_correlation):
        raw_correlation = 0.0

    incremental_clarity = max(
        0.0,
        abs(residual_correlation)
        - abs(raw_correlation),
    )

    direction = (
        1
        if residual_correlation > 0.0
        else -1
    )

    score = (
        abs(residual_correlation)
        * (
            1.0
            + incremental_clarity
        )
        * math.sqrt(n)
    )

    return ResidualDiscovery(
        candidate=candidate,
        controls=controls,
        horizon=horizon,
        n=n,
        raw_correlation=(
            raw_correlation
        ),
        residual_correlation=(
            residual_correlation
        ),
        incremental_clarity=(
            incremental_clarity
        ),
        direction=direction,
        score=score,
        independent_time_units=len(
            usable_minutes
        ),
        ancestry=tuple(
            sorted(ancestry)
        ),
    )


def discover_residual_relationships(
    rows: Iterable[
        UnifiedResearchRow
    ],
    *,
    candidate_names: Iterable[str],
    control_names: Iterable[str],
    horizons: tuple[int, ...] = (
        1,
        5,
        10,
        20,
    ),
    min_samples: int = 30,
    min_residual_correlation: float = 0.10,
    max_candidates: int = 30,
    max_controls: int = 8,
    max_results: int = 50,
) -> list[ResidualDiscovery]:
    rows = list(rows)

    candidates = list(
        dict.fromkeys(
            candidate_names
        )
    )[:max_candidates]

    controls = tuple(
        dict.fromkeys(
            control_names
        )
    )[:max_controls]

    discoveries = []

    for candidate in candidates:
        usable_controls = tuple(
            control
            for control in controls
            if control != candidate
        )

        for horizon in horizons:
            result = (
                evaluate_residual_relationship(
                    rows,
                    candidate=candidate,
                    controls=usable_controls,
                    horizon=horizon,
                    min_samples=min_samples,
                    max_controls=max_controls,
                )
            )

            if result is None:
                continue

            if (
                abs(
                    result.residual_correlation
                )
                < min_residual_correlation
            ):
                continue

            discoveries.append(
                result
            )

    discoveries.sort(
        key=lambda item: (
            item.score,
            abs(
                item.residual_correlation
            ),
            item.incremental_clarity,
        ),
        reverse=True,
    )

    return discoveries[
        :max_results
    ]
