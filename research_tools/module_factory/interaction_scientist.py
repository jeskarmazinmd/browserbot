"""
Interaction scientist for Module Factory.

Purpose:
    Find predictive structure that depends on combinations of variables
    rather than merely rediscovering a strong single feature.

This scientist is deliberately:
    - direction agnostic
    - bounded
    - compatible with UnifiedResearchRow
    - skeptical of redundant interactions
    - independent of any particular market-data provider

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


OPS = (
    "multiply",
    "subtract",
    "divide",
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

    covariance = sum(
        a * b
        for a, b in zip(dx, dy)
    )

    return covariance / math.sqrt(
        vx * vy
    )


def _interaction_value(
    left: float,
    right: float,
    operation: str,
) -> float:
    if (
        not _finite(left)
        or not _finite(right)
    ):
        return math.nan

    if operation == "multiply":
        return left * right

    if operation == "subtract":
        return left - right

    if operation == "divide":
        if abs(right) <= 1e-12:
            return math.nan

        return left / right

    raise ValueError(
        f"unsupported operation: {operation}"
    )


def _canonical_pair(
    left: str,
    right: str,
    operation: str,
) -> tuple[str, str]:
    if operation == "multiply":
        return tuple(
            sorted((left, right))
        )

    return left, right


@dataclass(frozen=True)
class InteractionDiscovery:
    left: str
    right: str
    operation: str
    horizon: int
    n: int
    interaction_correlation: float
    left_correlation: float
    right_correlation: float
    incremental_edge: float
    direction: int
    score: float
    independent_time_units: int
    ancestry: tuple[str, ...]

    @property
    def discovery_id(self) -> str:
        left, right = _canonical_pair(
            self.left,
            self.right,
            self.operation,
        )

        payload = (
            f"{left}|{right}|"
            f"{self.operation}|"
            f"{self.horizon}"
        )

        digest = hashlib.sha256(
            payload.encode()
        ).hexdigest()[:16]

        return f"interaction:{digest}"


def evaluate_interaction(
    rows: Iterable[
        UnifiedResearchRow
    ],
    *,
    left: str,
    right: str,
    operation: str,
    horizon: int,
    min_samples: int = 30,
) -> InteractionDiscovery | None:
    if operation not in OPS:
        raise ValueError(
            f"unsupported operation: {operation}"
        )

    interaction_values = []
    left_values = []
    right_values = []
    outcomes = []

    ancestry = set()
    usable_minutes = set()

    for row in rows:
        left_value = row.feature(left)
        right_value = row.feature(right)
        outcome = row.outcome(horizon)

        interaction = _interaction_value(
            left_value,
            right_value,
            operation,
        )

        if not (
            _finite(interaction)
            and _finite(left_value)
            and _finite(right_value)
            and _finite(outcome)
        ):
            continue

        interaction_values.append(
            interaction
        )
        left_values.append(
            left_value
        )
        right_values.append(
            right_value
        )
        outcomes.append(
            outcome
        )
        usable_minutes.add(
            row.minute
        )

        ancestry.update(
            row.ancestry(left)
        )
        ancestry.update(
            row.ancestry(right)
        )

    n = len(outcomes)

    if n < min_samples:
        return None

    interaction_corr = _pearson(
        interaction_values,
        outcomes,
    )

    left_corr = _pearson(
        left_values,
        outcomes,
    )

    right_corr = _pearson(
        right_values,
        outcomes,
    )

    if not _finite(interaction_corr):
        return None

    left_abs = (
        abs(left_corr)
        if _finite(left_corr)
        else 0.0
    )

    right_abs = (
        abs(right_corr)
        if _finite(right_corr)
        else 0.0
    )

    strongest_component = max(
        left_abs,
        right_abs,
    )

    incremental_edge = max(
        0.0,
        abs(interaction_corr)
        - strongest_component,
    )

    direction = (
        1
        if interaction_corr > 0
        else -1
    )

    # Reward interaction strength, but require genuine incremental
    # information rather than cosmetic transformation.
    score = (
        abs(interaction_corr)
        * incremental_edge
        * math.sqrt(n)
    )

    return InteractionDiscovery(
        left=left,
        right=right,
        operation=operation,
        horizon=horizon,
        n=n,
        interaction_correlation=(
            interaction_corr
        ),
        left_correlation=left_corr,
        right_correlation=right_corr,
        incremental_edge=(
            incremental_edge
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


def discover_interactions(
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
    operations: tuple[str, ...] = OPS,
    min_samples: int = 30,
    min_incremental_edge: float = 0.02,
    max_features: int = 24,
    max_results: int = 50,
) -> list[InteractionDiscovery]:
    rows = list(rows)

    names = list(
        dict.fromkeys(
            feature_names
        )
    )[:max_features]

    discoveries = []

    for i, left in enumerate(names):
        for right in names[i + 1:]:
            for operation in operations:
                pair_left, pair_right = (
                    _canonical_pair(
                        left,
                        right,
                        operation,
                    )
                )

                for horizon in horizons:
                    result = (
                        evaluate_interaction(
                            rows,
                            left=pair_left,
                            right=pair_right,
                            operation=operation,
                            horizon=horizon,
                            min_samples=min_samples,
                        )
                    )

                    if result is None:
                        continue

                    if (
                        result.incremental_edge
                        < min_incremental_edge
                    ):
                        continue

                    discoveries.append(
                        result
                    )

    discoveries.sort(
        key=lambda item: (
            item.score,
            item.incremental_edge,
            abs(
                item.interaction_correlation
            ),
        ),
        reverse=True,
    )

    return discoveries[
        :max_results
    ]
