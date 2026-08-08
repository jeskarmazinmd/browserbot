"""Broad hypothesis generation before performance screening."""

from __future__ import annotations

from collections import Counter
from itertools import combinations
from typing import Any

from research_lab.models import HypothesisProposal
from research_lab.plugins import REGISTRY


_OPERATIONAL_KEYS={
    "live_order_placement",
}


def _numeric(value):
    if isinstance(value,bool):
        return None
    try:
        return float(value)
    except (TypeError,ValueError):
        return None


def _parameter_items(strategy):
    seen=set()

    for key,value in strategy.config.items():
        if key in _OPERATIONAL_KEYS:
            continue
        if _numeric(value) is not None:
            seen.add(key)
            yield key,value,"CONFIG"

    ignored={
        "STRATEGY_ID","PAPER_ONLY",
    }

    for key,value in strategy.constants.items():
        if key in ignored or key=="CONFIG":
            continue
        if key in seen:
            continue
        if _numeric(value) is not None:
            yield key,value,"CONSTANT"


def _dimension_for_parameter(name):
    key=name.lower()

    if "stop" in key:
        return "stop_geometry"
    if "target" in key:
        return "target_geometry"
    if any(x in key for x in ("trail","breakeven")):
        return "trailing_and_dynamic_exits"
    if any(x in key for x in ("timeout","checkpoint","seconds","hold")):
        return "timeouts_and_failure_exits"
    return "threshold_tightening"


def parameter_neighborhood(strategies,profiles):
    proposals=[]

    for strategy in strategies:
        for key,value,source in _parameter_items(strategy):
            baseline=float(value)

            if baseline==0:
                continue

            for factor in (.50,.75,1.25,1.50):
                candidate=baseline*factor
                direction="lower" if factor<1 else "higher"

                proposals.append(HypothesisProposal(
                    strategy.strategy_id,
                    _dimension_for_parameter(key),
                    "parameter_neighborhood",
                    {
                        "operator":"parameter_mutation",
                        "parameter":key,
                        "source":source,
                        "baseline":baseline,
                        "candidate":candidate,
                        "relative_factor":factor,
                        "direction":direction,
                    },
                    "Explore the local parameter neighborhood without assuming "
                    "that higher or lower is inherently better.",
                    historical_testability="DATA_DEPENDENT",
                ))

    return proposals


def source_ablation(strategies,profiles):
    proposals=[]

    for strategy in strategies:
        for key,value,source in _parameter_items(strategy):
            name=key.lower()

            # Risk/exit geometry should be replaced, not literally removed.
            if any(x in name for x in ("stop","target","exit")):
                continue

            proposals.append(HypothesisProposal(
                strategy.strategy_id,
                "rule_ablation",
                "source_ablation",
                {
                    "operator":"remove_or_neutralize_parameter_constraint",
                    "parameter":key,
                    "source":source,
                    "baseline":value,
                },
                "Test whether this condition contributes useful information "
                "or merely excludes profitable candidates.",
                historical_testability="NEAR_MISS_OR_REPLAY_REQUIRED",
            ))

    return proposals


def entry_feature_thresholds(strategies,profiles):
    proposals=[]

    for profile in profiles:
        if (
            profile.kind!="numeric"
            or profile.count<20
            or profile.unique_count<5
            or profile.outcomes<20
        ):
            continue

        for q in ("q20","q40","q60","q80"):
            value=profile.numeric_quantiles[q]

            for operator in (">=","<="):
                proposals.append(HypothesisProposal(
                    profile.strategy_id,
                    "univariate_new_features",
                    "entry_feature_thresholds",
                    {
                        "operator":operator,
                        "field":profile.field,
                        "threshold":value,
                        "quantile":q,
                    },
                    "Search an entry-safe measured feature in both directions "
                    "without presuming its relationship to outcome.",
                    evidence_fields=(profile.field,),
                    historical_testability="HISTORICAL_ACCEPTED_SUBSET",
                ))

    return proposals


def categorical_partitions(strategies,profiles):
    proposals=[]

    for profile in profiles:
        if (
            profile.kind!="categorical"
            or profile.outcomes<20
            or not 2<=profile.unique_count<=12
        ):
            continue

        for value in profile.categories:
            proposals.append(HypothesisProposal(
                profile.strategy_id,
                "univariate_new_features",
                "categorical_partitions",
                {
                    "operator":"equals",
                    "field":profile.field,
                    "value":value,
                },
                "Test an observed entry-safe categorical context.",
                evidence_fields=(profile.field,),
                historical_testability="HISTORICAL_ACCEPTED_SUBSET",
            ))

    return proposals


def nonlinear_transform_ideas(strategies,profiles):
    proposals=[]
    by_strategy={}

    for profile in profiles:
        if (
            profile.kind=="numeric"
            and profile.outcomes>=20
            and profile.unique_count>=5
        ):
            by_strategy.setdefault(
                profile.strategy_id,[]
            ).append(profile.field)

    for strategy,fields in by_strategy.items():
        # Generate ideas broadly but cap quadratic explosion per strategy.
        fields=sorted(fields)[:30]

        for left,right in combinations(fields,2):
            for operation in ("difference","ratio"):
                proposals.append(HypothesisProposal(
                    strategy,
                    "nonlinear_transforms",
                    "pair_transforms",
                    {
                        "operator":operation,
                        "left":left,
                        "right":right,
                    },
                    "Create an orthogonal derived feature from two entry-safe "
                    "measurements; evaluate before any module is generated.",
                    evidence_fields=(left,right),
                    historical_testability="HISTORICAL_DERIVABLE",
                ))

    return proposals


def cross_family_exit_transfer(strategies,profiles):
    models={}

    for strategy in strategies:
        model=strategy.constants.get("EXIT_MODEL")
        if isinstance(model,str) and model:
            models.setdefault(model,set()).add(strategy.strategy_id)

    if len(models)<2:
        return []

    proposals=[]

    for strategy in strategies:
        current=strategy.constants.get("EXIT_MODEL")
        if not isinstance(current,str) or not current:
            continue

        for candidate,owners in sorted(models.items()):
            if candidate==current:
                continue

            proposals.append(HypothesisProposal(
                strategy.strategy_id,
                "cross_family_rule_transfer",
                "exit_model_transfer",
                {
                    "operator":"replace_exit_model",
                    "baseline":current,
                    "candidate":candidate,
                    "observed_in":sorted(owners),
                },
                "Test a structurally different exit concept observed elsewhere "
                "while keeping the generated experiment standalone.",
                historical_testability="PATH_REPLAY_OR_PROSPECTIVE",
            ))

    return proposals


BUILTIN_GENERATORS=(
    parameter_neighborhood,
    source_ablation,
    entry_feature_thresholds,
    categorical_partitions,
    nonlinear_transform_ideas,
    cross_family_exit_transfer,
)


def generate_proposals(strategies,profiles):
    proposals=[]

    for generator in BUILTIN_GENERATORS:
        proposals.extend(generator(strategies,profiles))

    context={
        "strategies":strategies,
        "profiles":profiles,
        "proposals_so_far":tuple(proposals),
    }

    for name,generator in REGISTRY.all("hypothesis_generator").items():
        generated=generator(context) or ()
        for item in generated:
            if not isinstance(item,HypothesisProposal):
                raise TypeError(
                    f"hypothesis generator {name} returned "
                    f"{type(item).__name__}"
                )
            proposals.append(item)

    # Exact specification dedupe. Distinct generators may independently
    # discover the same idea; that is one hypothesis, not two.
    unique={}
    for item in proposals:
        key=(
            item.strategy_id,
            item.dimension,
            repr(sorted(item.specification.items())),
        )
        unique.setdefault(key,item)

    return list(unique.values())


def proposal_summary(proposals):
    return {
        "total":len(proposals),
        "by_generator":Counter(x.generator for x in proposals),
        "by_dimension":Counter(x.dimension for x in proposals),
        "by_strategy":Counter(x.strategy_id for x in proposals),
    }
