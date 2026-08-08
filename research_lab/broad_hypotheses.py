"""Evidence-aware generators spanning context, rescue and diversity."""

from __future__ import annotations

import math
from collections import Counter,defaultdict
from zoneinfo import ZoneInfo

from research_lab.models import HypothesisProposal


NY=ZoneInfo("America/New_York")


def _quantile(values,q):
    ordered=sorted(values)
    if not ordered:
        return None
    return float(ordered[round((len(ordered)-1)*q)])


def _numeric_profiles(profiles):
    result=defaultdict(list)
    for profile in profiles:
        if (
            profile.kind=="numeric"
            and profile.outcomes>=20
            and profile.unique_count>=5
        ):
            result[profile.strategy_id].append(profile)
    return result


def range_band_proposals(profiles):
    result=[]
    for sid,items in _numeric_profiles(profiles).items():
        for profile in items:
            for low,high in (
                ("q10","q90"),
                ("q20","q80"),
                ("q40","q60"),
            ):
                result.append(HypothesisProposal(
                    sid,
                    "range_and_band_rules",
                    "range_band_search",
                    {
                        "operator":"between",
                        "field":profile.field,
                        "lower":profile.numeric_quantiles[low],
                        "upper":profile.numeric_quantiles[high],
                        "quantiles":[low,high],
                    },
                    "Test whether edge is concentrated inside an entry-safe "
                    "feature band rather than beyond a one-sided threshold.",
                    evidence_fields=(profile.field,),
                    historical_testability="HISTORICAL_ACCEPTED_SUBSET",
                ))
    return result


def interaction_search_proposals(profiles):
    result=[]
    for sid,items in _numeric_profiles(profiles).items():
        fields=sorted({x.field for x in items})
        if len(fields)>=2:
            result.append(HypothesisProposal(
                sid,
                "pairwise_interactions",
                "adaptive_pairwise_search",
                {
                    "operator":"search_pairwise_interactions",
                    "field_pool":fields,
                    "orientations":[">=/>=",">=/<=","<=/>=","<=/<="],
                },
                "Search the complete eligible two-feature pool adaptively "
                "instead of hard-coding a small pair list.",
                evidence_fields=tuple(fields),
                historical_testability="HISTORICAL_DERIVABLE",
            ))
        if len(fields)>=3:
            result.append(HypothesisProposal(
                sid,
                "higher_order_interactions",
                "adaptive_higher_order_search",
                {
                    "operator":"search_higher_order_interactions",
                    "field_pool":fields,
                    "minimum_order":3,
                    "search_mode":"adaptive_not_fixed_cap",
                },
                "Allow three-or-more-way entry interactions without fixing "
                "today's idea universe to an arbitrary combination cap.",
                evidence_fields=tuple(fields),
                historical_testability="HISTORICAL_DERIVABLE",
            ))
    return result


def time_of_day_proposals(evidence):
    phases=(
        ("OPEN",570,630),
        ("LATE_MORNING",630,720),
        ("MIDDAY",720,840),
        ("AFTERNOON",840,930),
        ("CLOSE",930,960),
    )
    result=[]

    for sid,trades in evidence.trades_by_strategy().items():
        if len(trades)<20:
            continue

        counts=Counter()
        for trade in trades:
            local=trade.entry_time.astimezone(NY)
            minute=local.hour*60+local.minute
            for name,start,end in phases:
                if start<=minute<end:
                    counts[name]+=1
                    break

        for name,start,end in phases:
            if counts[name]<10:
                continue
            result.append(HypothesisProposal(
                sid,
                "time_of_day",
                "session_partition",
                {
                    "operator":"entry_time_window",
                    "session_phase":name,
                    "start_minute_et":start,
                    "end_minute_et":end,
                    "observed_trades":counts[name],
                },
                "Test a predeclared session-time partition using only the "
                "clock known when the signal occurs.",
                historical_testability="HISTORICAL_ACCEPTED_SUBSET",
            ))

    return result


def _regime_dimension(field):
    name=field.lower()
    if "session_phase" in name:
        return "time_of_day"
    if ".breadth." in name or ".dispersion." in name or "labels.breadth" in name:
        return "breadth_and_dispersion"
    if ".returns." in name or ".trend." in name:
        return "market_direction_context"
    return "market_regime_context"


def regime_context_proposals(evidence):
    numeric=defaultdict(list)
    categorical=defaultdict(Counter)

    for trade in evidence.trades:
        regime=evidence.regime_at(trade.entry_time)
        if regime is None:
            continue

        for field,value in regime.fields.items():
            key=(trade.strategy_id,field)

            if isinstance(value,bool):
                categorical[key][value]+=1
            elif isinstance(value,(int,float)):
                number=float(value)
                if math.isfinite(number):
                    numeric[key].append(number)
            elif isinstance(value,str):
                categorical[key][value]+=1

    result=[]

    for (sid,field),values in numeric.items():
        if len(values)<20 or len(set(values))<5:
            continue

        for q in (.20,.50,.80):
            threshold=_quantile(values,q)
            for operator in (">=","<="):
                result.append(HypothesisProposal(
                    sid,
                    _regime_dimension(field),
                    "regime_numeric_threshold",
                    {
                        "operator":operator,
                        "field":field,
                        "threshold":threshold,
                        "quantile":q,
                        "observations":len(values),
                        "asof_join":"latest_regime_at_or_before_entry",
                    },
                    "Test independently timestamped market context that was "
                    "already observable when the trade entered.",
                    evidence_fields=(field,),
                    historical_testability="HISTORICAL_ASOF_JOIN",
                ))

    for (sid,field),counts in categorical.items():
        total=sum(counts.values())
        if total<20 or len(counts)<2:
            continue

        for value,count in counts.most_common(12):
            if count<10:
                continue
            result.append(HypothesisProposal(
                sid,
                _regime_dimension(field),
                "regime_categorical_partition",
                {
                    "operator":"equals",
                    "field":field,
                    "value":value,
                    "observations":count,
                    "asof_join":"latest_regime_at_or_before_entry",
                },
                "Test an entry-time market-state category without using "
                "information recorded after entry.",
                evidence_fields=(field,),
                historical_testability="HISTORICAL_ASOF_JOIN",
            ))

    return result


def cohort_mining_proposals(evidence):
    result=[]
    for sid,trades in evidence.trades_by_strategy().items():
        if len(trades)<40:
            continue

        result.append(HypothesisProposal(
            sid,
            "winner_cohort_mining",
            "winner_signature_search",
            {
                "operator":"discover_entry_signature",
                "cohort":"top_outcome_quantile",
                "quantile":0.80,
                "eligible_entry_fields":"all_provenance_safe",
            },
            "Search for entry-known characteristics disproportionately "
            "represented among unusually successful historical trades.",
            historical_testability="HISTORICAL_COHORT_MINING",
        ))

        result.append(HypothesisProposal(
            sid,
            "failure_mode_mining",
            "failure_signature_search",
            {
                "operator":"discover_entry_signature",
                "cohort":"bottom_outcome_quantile",
                "quantile":0.20,
                "eligible_entry_fields":"all_provenance_safe",
            },
            "Search for entry-known precursors of stops and severe losses.",
            historical_testability="HISTORICAL_COHORT_MINING",
        ))

        result.append(HypothesisProposal(
            sid,
            "loser_rescue",
            "component_rescue_search",
            {
                "operator":"decompose_winner_and_loser_components",
                "preserve_ancestor":True,
            },
            "Treat every strategy as a reusable ancestor and look for "
            "profitable substructure rather than discarding its ideas.",
            historical_testability="HISTORICAL_AND_REPLAY",
        ))

    return result


def sibling_proposals(evidence):
    result=[]
    for (left,right),count in evidence.controlled_sibling_overlap_counts().items():
        if count<20:
            continue
        result.append(HypothesisProposal(
            left,
            "matched_sibling_differences",
            "controlled_sibling_comparison",
            {
                "operator":"compare_controlled_lineage",
                "peer_strategy":right,
                "matched_events":count,
                "match_basis":"common_source_signal",
            },
            "Use common-source strategy descendants as natural experiments "
            "for isolating rule differences.",
            historical_testability="HISTORICAL_MATCHED_COMPARISON",
        ))
    return result


def wave_proposals(evidence):
    result=[]

    for sid,trades in evidence.trades_by_strategy().items():
        if len(trades)<20:
            continue

        batches=Counter(x.signal_time for x in trades)
        multi=[size for size in batches.values() if size>=2]

        if len(multi)<5:
            continue

        common={
            "multi_signal_batches":len(multi),
            "signals_in_batches":sum(multi),
            "largest_batch":max(multi),
        }

        for operator in (
            "wave_position",
            "wave_size",
            "first_vs_later",
        ):
            result.append(HypothesisProposal(
                sid,
                "signal_sequence_and_waves",
                "signal_wave_search",
                {
                    "operator":operator,
                    **common,
                },
                "Test whether clustered signals contain sequence or crowding "
                "information before imposing a fixed wave rule.",
                historical_testability="HISTORICAL_SEQUENCE",
            ))

    return result


def near_miss_proposals(evidence):
    counts=Counter()

    for item in evidence.near_misses:
        row=item.get("row") or {}
        sid=str(row.get("strategy_id") or "").strip()
        if not sid:
            setup=str(row.get("setup_id") or row.get("key") or "")
            if "|" in setup:
                sid=setup.split("|",1)[0]
        if sid:
            counts[sid]+=1

    result=[]
    for sid,count in counts.items():
        if count<3:
            continue
        result.append(HypothesisProposal(
            sid,
            "near_miss_recovery",
            "near_miss_boundary_search",
            {
                "operator":"replay_rejected_boundary_population",
                "near_miss_records":count,
            },
            "Search immediately outside current admission boundaries for "
            "missed edge rather than only tightening accepted trades.",
            historical_testability="NEAR_MISS_OR_REPLAY_REQUIRED",
        ))

    return result


def diversity_proposals(evidence):
    result=[]
    overlaps=evidence.coincident_overlap_counts()
    by_strategy=defaultdict(list)

    for (left,right),count in overlaps.items():
        if count<20:
            continue
        by_strategy[left].append((right,count))
        by_strategy[right].append((left,count))

        result.append(HypothesisProposal(
            left,
            "low_correlation_edges",
            "pair_diversification_search",
            {
                "operator":"measure_joint_edge_and_return_correlation",
                "peer_strategy":right,
                "coincident_signals":count,
            },
            "Search for complementary edge rather than ranking strategies "
            "only by standalone return.",
            historical_testability="HISTORICAL_PAIR_ANALYSIS",
        ))

    for sid,peers in by_strategy.items():
        result.append(HypothesisProposal(
            sid,
            "behavioral_novelty",
            "novel_population_search",
            {
                "operator":"seek_low_overlap_profitable_population",
                "reference_peers":[
                    name for name,_ in
                    sorted(peers,key=lambda x:x[1],reverse=True)[:20]
                ],
                "novelty_objective":"signal_population_divergence",
            },
            "Explicitly reward viable behavior unlike existing strategies "
            "to reduce convergence on one local optimum.",
            historical_testability="HISTORICAL_DIVERSITY_ANALYSIS",
        ))

    return result


def generate_broad_proposals(strategies,profiles,evidence):
    if evidence is None:
        return []

    result=[]
    result.extend(range_band_proposals(profiles))
    result.extend(interaction_search_proposals(profiles))
    result.extend(time_of_day_proposals(evidence))
    result.extend(regime_context_proposals(evidence))
    result.extend(cohort_mining_proposals(evidence))
    result.extend(sibling_proposals(evidence))
    result.extend(wave_proposals(evidence))
    result.extend(near_miss_proposals(evidence))
    result.extend(diversity_proposals(evidence))
    return result
