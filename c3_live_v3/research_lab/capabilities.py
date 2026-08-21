"""Research-capability and coverage accounting.

Capabilities describe what kinds of questions the currently discovered data
can support. They are intentionally separate from hypothesis generation.
"""

from __future__ import annotations

from typing import Any

from research_lab.models import (
    CoverageState,
    ResearchCapability,
    TemporalClass,
)
from research_lab.plugins import REGISTRY


def _roles(sources):
    return set().union(*(s.roles for s in sources)) if sources else set()


def _fields(sources):
    return {field for source in sources for field in source.fields}


def _has_leaf(fields, *names):
    wanted=set(names)
    return any(field.rsplit(".",1)[-1].replace("[]","") in wanted for field in fields)


def _builtin_capabilities(strategies, sources, provenance):
    roles=_roles(sources)
    fields=_fields(sources)

    safe_fields={
        item.field for item in provenance
        if item.temporal_class in {
            TemporalClass.ENTRY_KNOWN,
            TemporalClass.PAST_DERIVED,
        }
    }

    research_fields={
        x for x in safe_fields
        if x.startswith("research_metrics.")
    }

    has_outcome=bool(
        {"paper_outcome","research_outcome"} & roles
        and _has_leaf(fields,"ret_pct","return_pct","pnl","pnl_usd")
    )

    identity={
        "strategy_id","symbol","signal_timestamp",
    }
    leaves={
        field.rsplit(".",1)[-1].replace("[]","")
        for field in fields
    }
    matched_identity=identity <= leaves

    caps=[]

    caps.append(ResearchCapability(
        "strategy_source_introspection",
        CoverageState.AVAILABLE if strategies else CoverageState.MISSING,
        "strategy source is parsed without importing runtime dependencies",
        evidence=(f"{len(strategies)} strategies discovered",),
    ))

    if research_fields and has_outcome:
        caps.append(ResearchCapability(
            "accepted_entry_feature_analysis",
            CoverageState.AVAILABLE,
            "entry-time research features and realized outcomes coexist",
            evidence=(f"{len(research_fields)} research metric paths",),
        ))
        caps.append(ResearchCapability(
            "tighten_existing_filters",
            CoverageState.AVAILABLE,
            "accepted trades can be retrospectively filtered more strictly",
            evidence=("entry-safe research metrics","realized outcomes"),
        ))
    elif has_outcome:
        caps.append(ResearchCapability(
            "accepted_entry_feature_analysis",
            CoverageState.PARTIAL,
            "outcomes exist but rich entry-time research metrics are incomplete",
            gaps=("richer entry-state snapshots",),
        ))
        caps.append(ResearchCapability(
            "tighten_existing_filters",
            CoverageState.PARTIAL,
            "some entry fields exist but research feature coverage is incomplete",
            gaps=("strategy-specific entry metrics",),
        ))
    else:
        caps.append(ResearchCapability(
            "accepted_entry_feature_analysis",
            CoverageState.MISSING,
            "no joined entry-feature/outcome evidence was discovered",
        ))
        caps.append(ResearchCapability(
            "tighten_existing_filters",
            CoverageState.MISSING,
            "accepted-trade feature/outcome evidence is unavailable",
        ))

    if "near_miss" in roles:
        caps.append(ResearchCapability(
            "loosen_or_remove_filters",
            CoverageState.AVAILABLE,
            "near-miss evidence can expose candidates rejected by current rules",
            evidence=("near-miss dataset",),
        ))
    else:
        caps.append(ResearchCapability(
            "loosen_or_remove_filters",
            CoverageState.PROSPECTIVE_ONLY,
            "accepted trades cannot reveal outcomes for candidates never admitted",
            gaps=("near-miss/rejected-candidate outcomes",),
        ))

    caps.append(ResearchCapability(
        "winner_failure_mining",
        CoverageState.AVAILABLE if has_outcome else CoverageState.MISSING,
        "realized outcomes support winner/loser cohort analysis"
        if has_outcome else
        "realized outcome data is unavailable",
    ))

    if has_outcome and matched_identity:
        caps.append(ResearchCapability(
            "matched_sibling_comparison",
            CoverageState.AVAILABLE,
            "strategy/symbol/timestamp identity permits matched-trade comparisons",
            evidence=("strategy_id","symbol","signal_timestamp"),
        ))
        caps.append(ResearchCapability(
            "behavioral_diversity",
            CoverageState.AVAILABLE,
            "signal populations can be compared for overlap and distinctiveness",
            evidence=("strategy/symbol/time identities",),
        ))
    else:
        caps.append(ResearchCapability(
            "matched_sibling_comparison",
            CoverageState.PARTIAL,
            "outcome identity is insufficient for reliable matched comparisons",
            gaps=("strategy/symbol/signal timestamp identity",),
        ))
        caps.append(ResearchCapability(
            "behavioral_diversity",
            CoverageState.PARTIAL,
            "signal overlap cannot be fully reconstructed",
        ))

    market_path=bool({"minute_market_data","quote_tape"} & roles)
    caps.append(ResearchCapability(
        "path_dependent_entry_exit_replay",
        CoverageState.AVAILABLE if market_path else CoverageState.PROSPECTIVE_ONLY,
        "market-path data is available for replay"
        if market_path else
        "entry/exit path mutations require market-path data not currently discovered",
        gaps=() if market_path else ("minute or quote-path history",),
    ))

    regime="regime" in roles
    caps.append(ResearchCapability(
        "regime_conditioning",
        CoverageState.AVAILABLE if regime and has_outcome
        else CoverageState.PARTIAL if regime or has_outcome
        else CoverageState.MISSING,
        "regime observations can be joined to trade outcomes"
        if regime and has_outcome else
        "both regime history and trade outcomes are required",
        gaps=() if regime and has_outcome else tuple(
            x for x,present in (
                ("regime history",regime),
                ("trade outcomes",has_outcome),
            ) if not present
        ),
    ))

    capital="capital_performance" in roles
    caps.append(ResearchCapability(
        "capital_constraint_analysis",
        CoverageState.AVAILABLE if capital and has_outcome
        else CoverageState.PARTIAL if has_outcome
        else CoverageState.MISSING,
        "finite-capital evidence and trade outcomes are available"
        if capital and has_outcome else
        "trade outcomes alone do not prove exact capital-selection behavior",
        gaps=() if capital and has_outcome else ("finite-capital history/selection evidence",),
    ))

    resource="resource" in roles
    caps.append(ResearchCapability(
        "resource_capacity_model",
        CoverageState.AVAILABLE if resource
        else CoverageState.PROSPECTIVE_ONLY,
        "resource telemetry is available"
        if resource else
        "resource capacity requires telemetry or benchmark instrumentation",
        gaps=() if resource else ("resource telemetry","per-strategy timing"),
    ))

    caps.append(ResearchCapability(
        "structural_ablation",
        CoverageState.PROSPECTIVE_ONLY,
        "source structure can generate ablations; historical validity depends on rejected-candidate/path data",
        evidence=("strategy source",),
    ))

    caps.append(ResearchCapability(
        "cross_family_rule_transfer",
        CoverageState.PROSPECTIVE_ONLY,
        "source rules can be recombined into independent experiments; replayability is data-dependent",
        evidence=("strategy source",),
    ))

    return caps


def evaluate_capabilities(strategies, sources, provenance):
    capabilities=_builtin_capabilities(strategies,sources,provenance)

    context={
        "strategies":strategies,
        "sources":sources,
        "provenance":provenance,
        "capabilities":tuple(capabilities),
    }

    for name,detector in REGISTRY.all("capability_detector").items():
        result=detector(context)
        if result is None:
            continue
        if isinstance(result,ResearchCapability):
            result=[result]
        for item in result:
            if not isinstance(item,ResearchCapability):
                raise TypeError(
                    f"capability detector {name} returned "
                    f"{type(item).__name__}, expected ResearchCapability"
                )
            capabilities.append(item)

    # Plugin capabilities may deliberately add alternatives, but duplicate
    # names would make a coverage report ambiguous.
    seen=set()
    for item in capabilities:
        if item.name in seen:
            raise ValueError(f"duplicate research capability: {item.name}")
        seen.add(item.name)

    return capabilities
