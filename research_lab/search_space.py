"""Extensible map of research directions.

This is not an exhaustive list. Built-ins establish broad starting coverage;
plugins can add new dimensions indefinitely.
"""

from __future__ import annotations

from research_lab.models import (
    CoverageState,
    SearchCoverage,
    SearchDimension,
)
from research_lab.plugins import REGISTRY


BUILTIN_DIMENSIONS = (
    SearchDimension(
        "threshold_tightening","entry",
        "Tighten an existing numeric admission threshold.",
        ("tighten_existing_filters",),
    ),
    SearchDimension(
        "threshold_loosening","entry",
        "Loosen an existing threshold to recover rejected candidates.",
        ("loosen_or_remove_filters",),
    ),
    SearchDimension(
        "rule_ablation","structural",
        "Remove one or more existing conditions.",
        ("structural_ablation",),
    ),
    SearchDimension(
        "range_and_band_rules","entry",
        "Replace one-sided thresholds with ranges or bands.",
        ("accepted_entry_feature_analysis",),
    ),
    SearchDimension(
        "univariate_new_features","entry",
        "Search entry-safe features not currently used by the strategy.",
        ("accepted_entry_feature_analysis",),
    ),
    SearchDimension(
        "pairwise_interactions","interaction",
        "Search interactions between two entry-safe features.",
        ("accepted_entry_feature_analysis",),
    ),
    SearchDimension(
        "higher_order_interactions","interaction",
        "Adaptively search three-or-more-way feature interactions.",
        ("accepted_entry_feature_analysis",),
    ),
    SearchDimension(
        "nonlinear_transforms","interaction",
        "Ratios, curvature, acceleration, normalization and other transforms.",
        ("accepted_entry_feature_analysis",),
    ),
    SearchDimension(
        "winner_cohort_mining","rescue",
        "Discover entry-known characteristics of unusually good trades.",
        ("winner_failure_mining",),
    ),
    SearchDimension(
        "failure_mode_mining","rescue",
        "Discover entry-known precursors of stops and severe losses.",
        ("winner_failure_mining",),
    ),
    SearchDimension(
        "near_miss_recovery","rescue",
        "Study rejected/near-miss candidates for missed edge.",
        ("loosen_or_remove_filters",),
    ),
    SearchDimension(
        "matched_sibling_differences","structural",
        "Use same-entry sibling strategies as controlled experiments.",
        ("matched_sibling_comparison",),
    ),
    SearchDimension(
        "entry_confirmation","entry",
        "Earlier/later/persistent/alternative confirmation logic.",
        ("path_dependent_entry_exit_replay",),
    ),
    SearchDimension(
        "entry_timing","entry",
        "Delay, advance or condition entry timing.",
        ("path_dependent_entry_exit_replay",),
    ),
    SearchDimension(
        "stop_geometry","exit",
        "Fixed, tighter, wider and context-adjusted protective stops.",
        ("path_dependent_entry_exit_replay",),
    ),
    SearchDimension(
        "target_geometry","exit",
        "Alternative reward objectives and target geometry.",
        ("path_dependent_entry_exit_replay",),
    ),
    SearchDimension(
        "trailing_and_dynamic_exits","exit",
        "Trailing, breakeven and state-dependent exits.",
        ("path_dependent_entry_exit_replay",),
    ),
    SearchDimension(
        "timeouts_and_failure_exits","exit",
        "Time-based and no-progress failure management.",
        ("path_dependent_entry_exit_replay",),
    ),
    SearchDimension(
        "exit_model_substitution","exit",
        "Apply alternative existing exit models to the same entries.",
        ("path_dependent_entry_exit_replay",),
    ),
    SearchDimension(
        "time_of_day","context",
        "Entry-time session and clock effects.",
        ("winner_failure_mining",),
    ),
    SearchDimension(
        "market_direction_context","context",
        "Broad-market direction known at entry.",
        ("regime_conditioning",),
    ),
    SearchDimension(
        "market_regime_context","context",
        "Trend/chop/volatility regime effects.",
        ("regime_conditioning",),
    ),
    SearchDimension(
        "breadth_and_dispersion","context",
        "Cross-sectional breadth and dispersion context.",
        ("regime_conditioning",),
    ),
    SearchDimension(
        "relative_strength_context","context",
        "Stock performance relative to market or peers.",
        ("accepted_entry_feature_analysis",),
    ),
    SearchDimension(
        "volume_and_liquidity","context",
        "Volume, dollar-volume, liquidity and their dynamics.",
        ("accepted_entry_feature_analysis",),
    ),
    SearchDimension(
        "volatility_normalization","context",
        "Express thresholds in volatility units rather than absolute percentages.",
        ("accepted_entry_feature_analysis",),
    ),
    SearchDimension(
        "signal_sequence_and_waves","capacity",
        "Signal order, clustering and wave-position effects.",
        ("matched_sibling_comparison",),
    ),
    SearchDimension(
        "capital_pressure","capacity",
        "Concurrent deployment and capital-availability effects.",
        ("capital_constraint_analysis",),
    ),
    SearchDimension(
        "taken_vs_skipped","capacity",
        "Explain why finite capital selects better/worse subsets.",
        ("capital_constraint_analysis",),
    ),
    SearchDimension(
        "cross_family_rule_transfer","structural",
        "Transfer useful entry/exit/risk concepts between families.",
        ("cross_family_rule_transfer",),
    ),
    SearchDimension(
        "simplification","structural",
        "Search for simpler rules with equal or better behavior.",
        ("structural_ablation",),
    ),
    SearchDimension(
        "behavioral_novelty","diversity",
        "Seek profitable populations unlike existing strategies.",
        ("behavioral_diversity",),
    ),
    SearchDimension(
        "low_correlation_edges","diversity",
        "Seek low-overlap/low-correlation sources of edge.",
        ("behavioral_diversity",),
    ),
    SearchDimension(
        "loser_rescue","rescue",
        "Use failed strategies as ancestors and decompose good/bad components.",
        ("winner_failure_mining","strategy_source_introspection"),
    ),
    SearchDimension(
        "resource_efficiency","capacity",
        "Value of information and performance per compute/storage cost.",
        ("resource_capacity_model",),
    ),
)


def dimensions():
    result={item.name:item for item in BUILTIN_DIMENSIONS}

    for name,item in REGISTRY.all("search_dimension").items():
        if not isinstance(item,SearchDimension):
            raise TypeError(
                f"search dimension plugin {name} must be SearchDimension"
            )
        if item.name in result:
            raise ValueError(f"duplicate search dimension: {item.name}")
        result[item.name]=item

    return tuple(result.values())


def coverage(capabilities, memory_records=()):
    cap={item.name:item for item in capabilities}
    records=list(memory_records)
    result=[]

    for dimension in dimensions():
        required=[cap.get(name) for name in dimension.required_capabilities]

        missing=[
            name for name,item in zip(
                dimension.required_capabilities,
                required,
            )
            if item is None or item.state==CoverageState.MISSING
        ]

        conditional=[
            item.name for item in required
            if item is not None
            and item.state in {
                CoverageState.PARTIAL,
                CoverageState.PROSPECTIVE_ONLY,
            }
        ]

        if missing:
            readiness="BLOCKED"
            blockers=tuple(missing)
        elif conditional:
            readiness="CONDITIONAL"
            blockers=tuple(conditional)
        else:
            readiness="READY"
            blockers=()

        attempted=[
            r for r in records
            if r.get("dimension")==dimension.name
        ]
        touched={
            str(r.get("strategy_id"))
            for r in attempted
            if r.get("strategy_id")
        }

        result.append(SearchCoverage(
            dimension=dimension,
            readiness=readiness,
            attempts=len(attempted),
            strategies_touched=len(touched),
            blockers=blockers,
        ))

    return result
