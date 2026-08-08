"""Human-controlled strategy-family research analyst.

This module ranks *research directions*.  It never creates strategy modules,
changes registries, promotes experiments, or disables runtime strategies.
Historical accepted-trade outcomes are used only to prioritize hypotheses for
future paper testing; they are never counted as evidence for a new child.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from dataclasses import dataclass
from math import sqrt
from pathlib import Path
from statistics import fmean
from zoneinfo import ZoneInfo


NY=ZoneInfo("America/New_York")


@dataclass(frozen=True)
class SubsetScreen:
    supported: bool
    trades: int=0
    baseline_trades: int=0
    eligible_trades: int=0
    coverage_fraction: float | None=None
    days: int=0
    mean_return_pct: float | None=None
    baseline_mean_return_pct: float | None=None
    uplift_pct_points: float | None=None
    positive_day_fraction: float | None=None
    capital_compound_return_pct: float | None=None
    baseline_capital_compound_return_pct: float | None=None
    capital_uplift_pct_points: float | None=None
    score: float | None=None
    reason: str=""


@dataclass(frozen=True)
class RankedIdea:
    strategy_id: str
    dimension: str
    generator: str
    specification: dict
    rationale: str
    historical_testability: str
    screen: SubsetScreen
    lane: str


def _number(value):
    try:
        result=float(value)
        return result if result==result else None
    except (TypeError,ValueError):
        return None


def _field_value(trade,field):
    safe=getattr(trade,"safe_fields",{}) or {}
    if field in safe:
        return safe[field]
    # Evidence flattening may retain either a fully qualified field path or a
    # terminal alias.  Never inspect post-entry fields here.
    tail=str(field).rsplit(".",1)[-1]
    return safe.get(tail)


def _accepted_subset(proposal,trades):
    spec=proposal.specification
    operator=spec.get("operator")

    if operator in {">=","<=","between","equals"}:
        field=spec.get("field")
        if not field:
            return None,None,"missing entry field"

        def observed(trade):
            value=_field_value(trade,field)
            if operator=="equals":
                return value is not None
            return _number(value) is not None

        def keep(trade):
            value=_field_value(trade,field)
            if operator=="equals":
                return value==spec.get("value")
            value=_number(value)
            if value is None:
                return False
            if operator==">=":
                return value>=float(spec["threshold"])
            if operator=="<=":
                return value<=float(spec["threshold"])
            return float(spec["lower"])<=value<=float(spec["upper"])

        eligible=[x for x in trades if observed(x)]
        return eligible,[x for x in eligible if keep(x)],"entry-known accepted subset"

    if operator=="entry_time_window":
        start=int(spec["start_minute_et"])
        end=int(spec["end_minute_et"])

        def keep_time(trade):
            local=trade.entry_time.astimezone(NY)
            minute=local.hour*60+local.minute
            return start<=minute<end

        return list(trades),[x for x in trades if keep_time(x)],"entry-time accepted subset"

    return None,None,"operator requires a different evaluator or prospective replay"


def _compound(values):
    result=1.0
    for value in values:
        result*=1.0+float(value)/100.0
    return (result-1.0)*100.0


def _capital_daily(trades,capital_simulator):
    by_day=defaultdict(list)
    for trade in trades:
        day=trade.entry_time.astimezone(NY).date().isoformat()
        by_day[day].append(trade)
    result={}
    for day,items in by_day.items():
        simulation=capital_simulator(items)
        result[day]=(float(simulation.end_equity)/5000.0-1.0)*100.0
    return result


def screen_accepted_subset(
    proposal,
    trades,
    min_trades=30,
    min_days=2,
    min_feature_coverage=0.80,
    capital_simulator=None,
):
    """Screen a causally filterable accepted subset without certifying it."""
    trades=list(trades)
    eligible,subset,basis=_accepted_subset(proposal,trades)
    if subset is None:
        return SubsetScreen(False,reason=basis)

    base=[x for x in eligible if _number(getattr(x,"outcome_pct",None)) is not None]
    kept=[x for x in subset if _number(getattr(x,"outcome_pct",None)) is not None]
    all_usable=[x for x in trades if _number(getattr(x,"outcome_pct",None)) is not None]
    coverage=len(base)/len(all_usable) if all_usable else 0.0
    days={x.entry_time.astimezone(NY).date().isoformat() for x in kept}
    if coverage<float(min_feature_coverage):
        return SubsetScreen(
            True,
            trades=len(kept),
            baseline_trades=len(all_usable),
            eligible_trades=len(base),
            coverage_fraction=coverage,
            days=len(days),
            reason=(
                f"{basis}; feature coverage {coverage:.1%} below "
                f"{float(min_feature_coverage):.0%}; availability-confounded"
            ),
        )
    if len(kept)<int(min_trades) or len(days)<int(min_days) or not base:
        return SubsetScreen(
            True,
            trades=len(kept),
            baseline_trades=len(all_usable),
            eligible_trades=len(base),
            coverage_fraction=coverage,
            days=len(days),
            reason=f"{basis}; insufficient sample/day span for ranking",
        )

    baseline=fmean(float(x.outcome_pct) for x in base)
    mean=fmean(float(x.outcome_pct) for x in kept)
    uplift=mean-baseline
    capital_return=None
    baseline_capital=None
    capital_uplift=None
    if capital_simulator is not None:
        baseline_daily=_capital_daily(base,capital_simulator)
        subset_daily=_capital_daily(kept,capital_simulator)
        # A child with zero accepted trades on an otherwise eligible day earns
        # zero that day; this prevents selective disappearance of bad days.
        aligned_subset=[subset_daily.get(day,0.0) for day in sorted(baseline_daily)]
        baseline_capital=_compound(baseline_daily[day] for day in sorted(baseline_daily))
        capital_return=_compound(aligned_subset)
        capital_uplift=capital_return-baseline_capital
        positive_fraction=(
            sum(value>0 for value in aligned_subset)/len(aligned_subset)
            if aligned_subset else 0.0
        )
    else:
        by_day=defaultdict(list)
        for trade in kept:
            day=trade.entry_time.astimezone(NY).date().isoformat()
            by_day[day].append(float(trade.outcome_pct))
        positive_days=sum(fmean(values)>0 for values in by_day.values())
        positive_fraction=positive_days/len(by_day) if by_day else 0.0

    # Ranking heuristic only: reward uplift, independent sample support, and
    # day-to-day stability.  Capped sample factor prevents huge strategies
    # from winning merely because they fire more often.
    support=min(1.0,sqrt(len(kept)/100.0))
    stability=0.5+0.5*positive_fraction
    ranking_uplift=capital_uplift if capital_uplift is not None else uplift
    score=ranking_uplift*support*stability
    return SubsetScreen(
        True,
        trades=len(kept),
        baseline_trades=len(all_usable),
        eligible_trades=len(base),
        coverage_fraction=coverage,
        days=len(days),
        mean_return_pct=mean,
        baseline_mean_return_pct=baseline,
        uplift_pct_points=uplift,
        positive_day_fraction=positive_fraction,
        capital_compound_return_pct=capital_return,
        baseline_capital_compound_return_pct=baseline_capital,
        capital_uplift_pct_points=capital_uplift,
        score=score,
        reason=(
            f"{basis}; hypothesis-generation score only, "
            "not forward evidence"
        ),
    )


def analyze_parent(
    parent_id,proposals,evidence,*,show=8,min_trades=30,capital_simulator=None
):
    """Return a diverse shortlist for one explicitly user-selected parent."""
    trades=evidence.trades_by_strategy().get(parent_id,[])
    relevant=[x for x in proposals if x.strategy_id==parent_id]
    empirical=[]
    exploratory=[]

    for proposal in relevant:
        screen=screen_accepted_subset(
            proposal,trades,min_trades=min_trades,capital_simulator=capital_simulator
        )
        item=RankedIdea(
            strategy_id=parent_id,
            dimension=proposal.dimension,
            generator=proposal.generator,
            specification=proposal.specification,
            rationale=proposal.rationale,
            historical_testability=proposal.historical_testability,
            screen=screen,
            lane=(
                "EMPIRICAL" if screen.score is not None
                else "LOW_EVIDENCE" if screen.supported
                else "EXPLORATORY"
            ),
        )
        if screen.supported and screen.score is not None:
            empirical.append(item)
        else:
            exploratory.append(item)

    empirical.sort(
        key=lambda x:(
            -(x.screen.score if x.screen.score is not None else -1e99),
            x.dimension,
            x.generator,
            repr(x.specification),
        )
    )
    exploratory.sort(key=lambda x:(x.dimension,x.generator,repr(x.specification)))

    # Diversify before filling spare slots.  One superficially excellent field
    # cannot crowd every other research mechanism out of the shortlist.
    result=[]
    seen_dimensions=set()
    empirical_target=max(1,(int(show)+1)//2)
    for item in empirical:
        if item.dimension in seen_dimensions:
            continue
        result.append(item)
        seen_dimensions.add(item.dimension)
        if len(result)>=empirical_target:
            break

    exploratory_target=max(1,int(show)//3)
    exploratory_added=0
    for item in exploratory:
        if item.dimension in seen_dimensions:
            continue
        result.append(item)
        seen_dimensions.add(item.dimension)
        exploratory_added+=1
        if exploratory_added>=exploratory_target or len(result)>=int(show):
            break

    for pool in (empirical,exploratory):
        for item in pool:
            if len(result)>=int(show):
                break
            if item not in result:
                result.append(item)
    return result


def retirement_watchlist(
    evidence,
    *,
    min_trades=100,
    min_days=2,
    capital_results=None,
    maximum_compound_return_pct=-2.0,
):
    """Advisory-only loser screen.  Nothing here changes runtime state.

    When exact capital reconstructions are supplied they are authoritative for
    this screen; raw average trade return is only a lightweight test fallback.
    """
    if capital_results is not None:
        grouped=defaultdict(list)
        for (day,strategy),result in capital_results.items():
            daily=(float(result.end_equity)/5000.0-1.0)*100.0
            grouped[strategy].append((day,daily,int(result.signals)))
        rows=[]
        for strategy,items in grouped.items():
            if len(items)<int(min_days):
                continue
            count=sum(x[2] for x in items)
            if count<int(min_trades):
                continue
            days={day:value for day,value,_ in items}
            compound=_compound(value for _,value,_ in items)
            if (
                compound<=float(maximum_compound_return_pct)
                and all(value<0 for value in days.values())
            ):
                rows.append((compound,strategy,count,days))
        rows.sort()
        return rows

    rows=[]
    for strategy,trades in evidence.trades_by_strategy().items():
        usable=[x for x in trades if _number(getattr(x,"outcome_pct",None)) is not None]
        if len(usable)<min_trades:
            continue
        by_day=defaultdict(list)
        for trade in usable:
            day=trade.entry_time.astimezone(NY).date().isoformat()
            by_day[day].append(float(trade.outcome_pct))
        if len(by_day)<min_days:
            continue
        day_means={day:fmean(values) for day,values in by_day.items()}
        overall=fmean(float(x.outcome_pct) for x in usable)
        if overall<0 and all(value<0 for value in day_means.values()):
            rows.append((overall,strategy,len(usable),day_means))
    rows.sort()
    return rows


def _print_idea(index,item):
    screen=item.screen
    if screen.score is None:
        evidence=screen.reason
    else:
        evidence=(
            f"subset={screen.trades}/{screen.baseline_trades} "
            f"coverage={screen.coverage_fraction:.0%} days={screen.days} "
            f"mean={screen.mean_return_pct:+.3f}% "
            f"uplift={screen.uplift_pct_points:+.3f}pp "
            f"positive_days={screen.positive_day_fraction:.0%}"
        )
        if screen.capital_compound_return_pct is not None:
            evidence+=(
                f" cap={screen.capital_compound_return_pct:+.2f}% "
                f"cap_uplift={screen.capital_uplift_pct_points:+.2f}pp"
            )
    print(
        f"{index:2}. {item.lane:11} {item.dimension:30} "
        f"{item.generator}\n"
        f"    {evidence}\n"
        f"    idea={item.specification}\n"
        f"    why={item.rationale}"
    )


def main(argv=None):
    parser=argparse.ArgumentParser(prog="family-analyst")
    parser.add_argument("--repo-root",default=".")
    parser.add_argument("--data-root",default="research_data")
    parser.add_argument("--parent",action="append",required=True)
    parser.add_argument("--show",type=int,default=8)
    parser.add_argument("--max-records-per-source",type=int,default=None)
    parser.add_argument("--retirement-watchlist",action="store_true")
    args=parser.parse_args(argv)

    # Heavy repository discovery stays in the established research framework.
    from research_lab.discovery import build_report
    from research_lab.evidence import build_evidence
    from research_lab.features import profile_sources
    from research_lab.hypotheses import generate_proposals
    from research_lab.capital import simulate_day,simulate_evidence

    report=build_report(
        Path(args.repo_root).resolve(),Path(args.data_root).resolve(),"sample",2000
    )
    profiles=profile_sources(
        report.sources,max_records_per_source=args.max_records_per_source
    )
    evidence=build_evidence(
        report.sources,max_records_per_source=args.max_records_per_source
    )
    proposals=generate_proposals(report.strategies,profiles,evidence)

    print("HUMAN-CONTROLLED FAMILY ANALYST")
    print("Historical screens generate hypotheses only; no child is activated.")
    for parent in args.parent:
        ideas=analyze_parent(
            parent,proposals,evidence,show=args.show,capital_simulator=simulate_day
        )
        print(f"\n=== {parent} : {len(ideas)} DIVERSE DIRECTIONS ===")
        for index,item in enumerate(ideas,1):
            _print_idea(index,item)

    if args.retirement_watchlist:
        print("\n=== ADVISORY RETIREMENT WATCHLIST ===")
        print("No strategy is disabled by this command.")
        capital=simulate_evidence(evidence)
        for overall,strategy,count,days in retirement_watchlist(
            evidence,capital_results=capital
        ):
            compact=",".join(f"{day}:{value:+.3f}%" for day,value in sorted(days.items()))
            print(f"{strategy:12} compound={overall:+.3f}% N={count:5} days={compact}")


if __name__=="__main__":
    main()
