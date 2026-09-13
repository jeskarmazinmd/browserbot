"""
Autonomous generational discovery loop for Module Factory.

Flow:
    primitive observations
      -> discover
      -> select
      -> remember
      -> mutate survivors
      -> evaluate children in bounded batches
      -> select
      -> remember
      -> repeat

Generated feature values are temporary.  They are never all materialized
into the permanent FeatureRow dictionaries at once.

Research only.  No live-trading imports.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from research_tools.module_factory.discovery_engine import (
    Discovery,
    discover,
)
from research_tools.module_factory.expressions import (
    ExpressionSpec,
    evaluate_expression,
)
from research_tools.module_factory.feature_matrix import FeatureRow
from research_tools.module_factory.memory import (
    ExperimentMemory,
    record_candidate_result,
)
from research_tools.module_factory.search_controller import (
    Candidate,
    SearchDecision,
    SearchPolicy,
    build_candidates,
    mutate_parent,
    select_population,
)


@dataclass(frozen=True)
class GenerationPolicy:
    generations: int = 2
    parent_limit: int = 25
    child_batch_size: int = 100
    max_children_per_generation: int = 500
    horizons: tuple[int, ...] = (1, 5, 10, 20)
    tail_fraction: float = 0.10
    buckets: int = 10
    min_observations_per_day: int = 100
    fdr_q: float = 0.05
    search: SearchPolicy = SearchPolicy()


@dataclass
class GenerationResult:
    generation: int
    tested: int
    selected: list[Candidate] = field(default_factory=list)
    rejected: list[Candidate] = field(default_factory=list)
    expressions: list[ExpressionSpec] = field(default_factory=list)


@dataclass
class FactoryRun:
    generations: list[GenerationResult] = field(default_factory=list)

    @property
    def total_tested(self) -> int:
        return sum(x.tested for x in self.generations)

    @property
    def final_population(self) -> list[Candidate]:
        if not self.generations:
            return []
        return self.generations[-1].selected


def _clone_with_feature(
    row: FeatureRow,
    feature_name: str,
    value: float,
) -> FeatureRow:
    """
    Lightweight temporary row containing one generated observable.
    """
    return FeatureRow(
        symbol=row.symbol,
        minute=row.minute,
        price=row.price,
        features={feature_name: value},
        forward_returns=row.forward_returns,
    )


def _expression_rows(
    rows_by_day: dict[str, list[FeatureRow]],
    expression: ExpressionSpec,
    expression_catalog: dict[str, ExpressionSpec],
) -> dict[str, list[FeatureRow]]:
    """
    Evaluate one expression lazily.

    Recursive evaluation permits later generations to use generated
    expressions as parents without permanently expanding FeatureRow.
    """

    cache: dict[tuple[int, str], float] = {}

    def value_for(
        row: FeatureRow,
        feature: str,
    ) -> float:
        if feature in row.features:
            value = row.features[feature]
            return (
                float(value)
                if isinstance(value, (int, float))
                else math.nan
            )

        key = (id(row), feature)

        if key in cache:
            return cache[key]

        spec = expression_catalog.get(feature)

        if spec is None:
            cache[key] = math.nan
            return math.nan

        synthetic = dict(row.features)

        synthetic[spec.left] = value_for(
            row,
            spec.left,
        )

        if spec.right:
            synthetic[spec.right] = value_for(
                row,
                spec.right,
            )

        result = evaluate_expression(
            spec,
            synthetic,
        )

        cache[key] = result
        return result

    output = {}

    for day, rows in rows_by_day.items():
        temporary = []

        for row in rows:
            value = value_for(
                row,
                expression.expression_id,
            )

            temporary.append(
                _clone_with_feature(
                    row,
                    expression.expression_id,
                    value,
                )
            )

        output[day] = temporary

    return output


def _discover_expression(
    rows_by_day: dict[str, list[FeatureRow]],
    expression: ExpressionSpec,
    catalog: dict[str, ExpressionSpec],
    policy: GenerationPolicy,
) -> list[Discovery]:

    temporary = _expression_rows(
        rows_by_day,
        expression,
        catalog,
    )

    return discover(
        temporary,
        horizons=policy.horizons,
        tail_fraction=policy.tail_fraction,
        buckets=policy.buckets,
        min_observations_per_day=(
            policy.min_observations_per_day
        ),
        fdr_q=policy.fdr_q,
    )


def _record_decision(
    memory: ExperimentMemory,
    decision: SearchDecision,
    discoveries: list[Discovery],
) -> None:

    discovery_map = {
        (x.feature, x.horizon): x
        for x in discoveries
    }

    selected_keys = {
        (x.feature, x.horizon)
        for x in decision.selected
    }

    for candidate in (
        decision.selected + decision.rejected
    ):
        key = (
            candidate.feature,
            candidate.horizon,
        )

        discovery = discovery_map.get(key)

        if discovery is None:
            continue

        record_candidate_result(
            memory,
            feature=candidate.feature,
            horizon=candidate.horizon,
            generation=candidate.generation,
            lineage=candidate.lineage,
            discovery_score=candidate.discovery_score,
            search_score=candidate.search_score,
            bh_pass=candidate.bh_pass,
            sign_consistency=(
                candidate.consistency
            ),
            worst_day_edge=(
                candidate.worst_day_edge
            ),
            observations=discovery.observations,
            selected=key in selected_keys,
            rejection_reason=(
                None
                if key in selected_keys
                else candidate.reason
            ),
        )


def _select_and_remember(
    discoveries: list[Discovery],
    *,
    catalog: dict[str, ExpressionSpec],
    memory: ExperimentMemory,
    policy: GenerationPolicy,
) -> SearchDecision:

    candidates = build_candidates(
        discoveries,
        expression_catalog=catalog,
        policy=policy.search,
    )

    decision = select_population(
        candidates,
        policy=policy.search,
    )

    _record_decision(
        memory,
        decision,
        discoveries,
    )

    return decision


def _novel_children(
    parents: list[Candidate],
    available_features: list[str],
    catalog: dict[str, ExpressionSpec],
    memory: ExperimentMemory,
    *,
    generation: int,
    policy: GenerationPolicy,
) -> list[ExpressionSpec]:

    children = {}

    for parent in parents[:policy.parent_limit]:
        produced = mutate_parent(
            parent,
            available_features,
            generation=generation,
            seed=(
                policy.search.seed
                + generation
            ),
        )

        for child in produced:
            if child.expression_id in catalog:
                continue

            # A child can be novel for some horizons even if already
            # tested for another. Keep it if any requested horizon is new.
            if all(
                memory.seen(
                    child.expression_id,
                    horizon,
                )
                for horizon in policy.horizons
            ):
                continue

            children[
                child.expression_id
            ] = child

            if (
                len(children)
                >= policy.max_children_per_generation
            ):
                return list(children.values())

    return list(children.values())


def run_factory(
    rows_by_day: dict[str, list[FeatureRow]],
    *,
    memory: ExperimentMemory,
    policy: GenerationPolicy = GenerationPolicy(),
) -> FactoryRun:

    result = FactoryRun()
    catalog: dict[str, ExpressionSpec] = {}

    # -------------------------
    # Generation 0: primitives
    # -------------------------
    primitive_discoveries = discover(
        rows_by_day,
        horizons=policy.horizons,
        tail_fraction=policy.tail_fraction,
        buckets=policy.buckets,
        min_observations_per_day=(
            policy.min_observations_per_day
        ),
        fdr_q=policy.fdr_q,
    )

    # Do not retest primitive feature/horizon pairs already in memory.
    primitive_discoveries = [
        item
        for item in primitive_discoveries
        if not memory.seen(
            item.feature,
            item.horizon,
        )
    ]

    primitive_decision = _select_and_remember(
        primitive_discoveries,
        catalog=catalog,
        memory=memory,
        policy=policy,
    )

    result.generations.append(
        GenerationResult(
            generation=0,
            tested=len(primitive_discoveries),
            selected=primitive_decision.selected,
            rejected=primitive_decision.rejected,
        )
    )

    parents = primitive_decision.selected

    available_features = sorted({
        feature
        for rows in rows_by_day.values()
        for row in rows
        for feature in row.features
    })

    # -------------------------
    # Generations 1..N
    # -------------------------
    for generation in range(
        1,
        policy.generations + 1,
    ):
        if not parents:
            break

        children = _novel_children(
            parents,
            available_features,
            catalog,
            memory,
            generation=generation,
            policy=policy,
        )

        if not children:
            break

        for child in children:
            catalog[
                child.expression_id
            ] = child

        discoveries = []

        # Bounded evaluation batches.  Values disappear after each child.
        for start in range(
            0,
            len(children),
            policy.child_batch_size,
        ):
            batch = children[
                start:
                start + policy.child_batch_size
            ]

            for child in batch:
                child_results = _discover_expression(
                    rows_by_day,
                    child,
                    catalog,
                    policy,
                )

                discoveries.extend(
                    item
                    for item in child_results
                    if not memory.seen(
                        item.feature,
                        item.horizon,
                    )
                )

        decision = _select_and_remember(
            discoveries,
            catalog=catalog,
            memory=memory,
            policy=policy,
        )

        result.generations.append(
            GenerationResult(
                generation=generation,
                tested=len(discoveries),
                selected=decision.selected,
                rejected=decision.rejected,
                expressions=children,
            )
        )

        parents = decision.selected

        available_features = sorted(
            set(available_features)
            | {
                child.expression_id
                for child in children
            }
        )

    return result


def render_run(run: FactoryRun) -> str:
    lines = [
        "MODULE FACTORY GENERATIONAL RUN",
        "=" * 72,
    ]

    for generation in run.generations:
        lines.append(
            f"Generation {generation.generation}: "
            f"tested={generation.tested} "
            f"selected={len(generation.selected)} "
            f"rejected={len(generation.rejected)} "
            f"expressions={len(generation.expressions)}"
        )

        for candidate in generation.selected[:10]:
            lines.append(
                "  "
                f"{candidate.feature:<20} "
                f"h={candidate.horizon:<3} "
                f"score={candidate.search_score:.4f} "
                f"consistency={candidate.consistency:.2f} "
                f"reason={candidate.reason}"
            )

    lines.append("-" * 72)
    lines.append(
        f"Total hypotheses tested: {run.total_tested}"
    )
    lines.append(
        f"Final research population: "
        f"{len(run.final_population)}"
    )

    return "\n".join(lines)
