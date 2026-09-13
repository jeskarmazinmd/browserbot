"""
Autonomous search controller for Module Factory.

This is the beginning of the factory's research policy.

It does not contain trading strategies.  It decides how to allocate research
compute across mathematical observables and generated expressions.

Principles:
- exploit promising discoveries
- preserve exploration
- reward independent-day consistency
- penalize pathological / numerically unstable expressions
- preserve lineage
- remember rejected regions
- bound population growth
- deterministic/reproducible selection
"""

from __future__ import annotations

import hashlib
import json
import math
import random
from dataclasses import asdict, dataclass, field

from research_tools.module_factory.discovery_engine import Discovery
from research_tools.module_factory.expressions import (
    ExpressionSpec,
)


@dataclass(frozen=True)
class SearchPolicy:
    population_limit: int = 250
    elite_fraction: float = 0.20
    exploration_fraction: float = 0.20
    min_day_consistency: float = 0.50
    complexity_penalty: float = 0.025
    instability_penalty: float = 0.20
    seed: int = 20260902


@dataclass
class Candidate:
    feature: str
    horizon: int
    generation: int
    lineage: tuple[str, ...]
    discovery_score: float
    consistency: float
    worst_day_edge: float
    bh_pass: bool
    complexity: int
    instability: float
    search_score: float
    reason: str = ""


@dataclass
class SearchDecision:
    selected: list[Candidate] = field(default_factory=list)
    rejected: list[Candidate] = field(default_factory=list)
    exploitation_count: int = 0
    exploration_count: int = 0


def expression_complexity(
    feature: str,
    catalog: dict[str, ExpressionSpec],
    _seen: set[str] | None = None,
) -> int:
    if feature not in catalog:
        return 1

    if _seen is None:
        _seen = set()

    if feature in _seen:
        return 1000

    seen = set(_seen)
    seen.add(feature)

    expression = catalog[feature]

    left = expression_complexity(
        expression.left,
        catalog,
        seen,
    )

    right = (
        expression_complexity(
            expression.right,
            catalog,
            seen,
        )
        if expression.right
        else 0
    )

    return 1 + left + right


def expression_lineage(
    feature: str,
    catalog: dict[str, ExpressionSpec],
    _seen: set[str] | None = None,
) -> tuple[str, ...]:
    if feature not in catalog:
        return (feature,)

    if _seen is None:
        _seen = set()

    if feature in _seen:
        return (feature,)

    seen = set(_seen)
    seen.add(feature)

    expression = catalog[feature]

    result = [feature]

    result.extend(
        expression_lineage(
            expression.left,
            catalog,
            seen,
        )
    )

    if expression.right:
        result.extend(
            expression_lineage(
                expression.right,
                catalog,
                seen,
            )
        )

    # Stable de-duplication.
    return tuple(dict.fromkeys(result))


def instability_fraction(
    values: list[float],
) -> float:
    if not values:
        return 1.0

    bad = sum(
        not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        for value in values
    )

    finite_values = [
        abs(float(value))
        for value in values
        if isinstance(value, (int, float))
        and math.isfinite(float(value))
    ]

    if not finite_values:
        return 1.0

    finite_values.sort()

    median = finite_values[len(finite_values) // 2]
    p99 = finite_values[
        min(
            len(finite_values) - 1,
            int(0.99 * (len(finite_values) - 1)),
        )
    ]

    explosive = (
        median > 0
        and p99 > median * 1000.0
    )

    return min(
        1.0,
        bad / len(values)
        + (0.25 if explosive else 0.0),
    )


def _candidate_id(
    feature: str,
    horizon: int,
) -> str:
    payload = json.dumps(
        {
            "feature": feature,
            "horizon": horizon,
        },
        sort_keys=True,
    )

    return hashlib.sha1(
        payload.encode()
    ).hexdigest()


def build_candidates(
    discoveries: list[Discovery],
    *,
    expression_catalog: dict[str, ExpressionSpec] | None = None,
    instability: dict[str, float] | None = None,
    policy: SearchPolicy = SearchPolicy(),
) -> list[Candidate]:

    catalog = expression_catalog or {}
    instability = instability or {}

    result = []

    for discovery in discoveries:
        complexity = expression_complexity(
            discovery.feature,
            catalog,
        )

        unstable = instability.get(
            discovery.feature,
            0.0,
        )

        score = (
            discovery.score
            + (0.10 if discovery.bh_pass else 0.0)
            + 0.10 * discovery.sign_consistency
            + 0.15 * discovery.worst_day_edge
            - policy.complexity_penalty
            * max(0, complexity - 1)
            - policy.instability_penalty
            * unstable
        )

        generation = (
            catalog[discovery.feature].generation
            if discovery.feature in catalog
            else 0
        )

        result.append(
            Candidate(
                feature=discovery.feature,
                horizon=discovery.horizon,
                generation=generation,
                lineage=expression_lineage(
                    discovery.feature,
                    catalog,
                ),
                discovery_score=discovery.score,
                consistency=discovery.sign_consistency,
                worst_day_edge=discovery.worst_day_edge,
                bh_pass=discovery.bh_pass,
                complexity=complexity,
                instability=unstable,
                search_score=score,
            )
        )

    return result


def select_population(
    candidates: list[Candidate],
    *,
    policy: SearchPolicy = SearchPolicy(),
) -> SearchDecision:

    if not candidates:
        return SearchDecision()

    eligible = []
    rejected = []

    for candidate in candidates:
        if (
            candidate.consistency
            < policy.min_day_consistency
        ):
            candidate.reason = "poor_day_consistency"
            rejected.append(candidate)
        else:
            eligible.append(candidate)

    eligible.sort(
        key=lambda item: (
            item.bh_pass,
            item.search_score,
            item.worst_day_edge,
            -item.complexity,
            _candidate_id(
                item.feature,
                item.horizon,
            ),
        ),
        reverse=True,
    )

    limit = min(
        policy.population_limit,
        len(eligible),
    )

    if limit == 0:
        return SearchDecision(
            rejected=rejected,
        )

    elite_count = min(
        limit,
        max(
            1,
            int(
                round(
                    limit
                    * policy.elite_fraction
                )
            ),
        ),
    )

    exploration_count = min(
        limit - elite_count,
        int(
            round(
                limit
                * policy.exploration_fraction
            )
        ),
    )

    selected = list(
        eligible[:elite_count]
    )

    remaining = eligible[elite_count:]

    # Deterministic random exploration.
    rng = random.Random(policy.seed)

    if exploration_count and remaining:
        exploratory = rng.sample(
            remaining,
            min(
                exploration_count,
                len(remaining),
            ),
        )

        for candidate in exploratory:
            candidate.reason = "exploration"

        selected.extend(exploratory)

        selected_keys = {
            (x.feature, x.horizon)
            for x in selected
        }

        remaining = [
            x for x in remaining
            if (x.feature, x.horizon)
            not in selected_keys
        ]

    # Fill remaining research budget by merit.
    fill = limit - len(selected)

    if fill > 0:
        selected.extend(
            remaining[:fill]
        )
        remaining = remaining[fill:]

    selected_keys = {
        (x.feature, x.horizon)
        for x in selected
    }

    for candidate in selected:
        if not candidate.reason:
            candidate.reason = (
                "elite"
                if candidate
                in eligible[:elite_count]
                else "merit"
            )

    for candidate in eligible:
        if (
            candidate.feature,
            candidate.horizon,
        ) not in selected_keys:
            candidate.reason = "population_budget"
            rejected.append(candidate)

    return SearchDecision(
        selected=selected,
        rejected=rejected,
        exploitation_count=sum(
            x.reason in {"elite", "merit"}
            for x in selected
        ),
        exploration_count=sum(
            x.reason == "exploration"
            for x in selected
        ),
    )


def mutate_parent(
    parent: Candidate,
    available_features: list[str],
    *,
    generation: int,
    seed: int,
) -> list[ExpressionSpec]:
    """
    Produce simple mathematical children from a successful observable.

    This is intentionally generic: the factory is not told what kind of
    market relationship the parent represents.
    """

    rng = random.Random(
        f"{seed}:{parent.feature}:{parent.horizon}"
    )

    partners = [
        feature
        for feature in sorted(set(available_features))
        if feature != parent.feature
    ]

    if not partners:
        return []

    sample = rng.sample(
        partners,
        min(8, len(partners)),
    )

    result = [
        ExpressionSpec(
            operation="absolute",
            left=parent.feature,
            generation=generation,
        ),
        ExpressionSpec(
            operation="square",
            left=parent.feature,
            generation=generation,
        ),
    ]

    for partner in sample:
        result.extend(
            [
                ExpressionSpec(
                    operation="subtract",
                    left=parent.feature,
                    right=partner,
                    generation=generation,
                ),
                ExpressionSpec(
                    operation="multiply",
                    left=parent.feature,
                    right=partner,
                    generation=generation,
                ),
                ExpressionSpec(
                    operation="divide",
                    left=parent.feature,
                    right=partner,
                    generation=generation,
                ),
                ExpressionSpec(
                    operation="divide",
                    left=partner,
                    right=parent.feature,
                    generation=generation,
                ),
            ]
        )

    unique = {
        expression.expression_id: expression
        for expression in result
    }

    return list(unique.values())
