"""Command-line entry point for the research laboratory."""

from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path

from research_lab.discovery import build_report
from research_lab.features import profile_sources
from research_lab.evidence import build_evidence
from research_lab.hypotheses import (
    generate_proposals,
    proposal_summary,
)
from research_lab.memory import ResearchMemory
from research_lab.search_space import coverage
from research_lab.models import TemporalClass


def discover(args):
    report=build_report(
        Path(args.repo_root).resolve(),
        Path(args.data_root).resolve(),
        args.schema_mode,
        args.sample_records,
    )

    print("RESEARCH LAB DISCOVERY")
    print("strategies:",len(report.strategies))
    print("data sources:",len(report.sources))

    roles=Counter()
    for source in report.sources:
        for role in source.roles:
            roles[role]+=1

    print("\nDATA ROLES")
    for role,count in sorted(roles.items()):
        print(f"{role:24} {count}")

    print("\nSTRATEGY FAMILIES")
    families=Counter(s.family or "UNSPECIFIED" for s in report.strategies)
    for family,count in sorted(families.items()):
        print(f"{family:24} {count}")

    temporal=Counter(x.temporal_class for x in report.provenance)
    print("\nTEMPORAL PROVENANCE")
    for kind in TemporalClass:
        print(f"{kind.value:24} {temporal[kind]}")

    print("\nRESEARCH CAPABILITIES")
    for item in report.capabilities:
        print(f"{item.state.value:17} {item.name:34} {item.reason}")

    print("\nBLIND SPOTS")
    if not report.blind_spots:
        print("none detected by current discovery plugins")
    for item in report.blind_spots:
        print(f"{item.severity:5} {item.category:18} {item.description}")

    print("\nPLUGIN-READY")
    print("Feature, hypothesis, evaluator, replay, diversity, capacity,")
    print("and lifecycle plugins can be added without changing discovery.")


def show_coverage(args):
    report=build_report(
        Path(args.repo_root).resolve(),
        Path(args.data_root).resolve(),
        args.schema_mode,
        args.sample_records,
    )

    records=ResearchMemory(args.memory).load()
    rows=coverage(report.capabilities,records)

    print("RESEARCH SEARCH-SPACE COVERAGE")
    print("dimensions:",len(rows))
    print("recorded hypotheses:",len(records))

    categories=sorted({x.dimension.category for x in rows})

    for category in categories:
        print(f"\n=== {category.upper()} ===")
        for item in rows:
            if item.dimension.category!=category:
                continue

            explored=(
                "UNSEARCHED"
                if item.attempts==0
                else f"{item.attempts} ATTEMPTS"
            )

            blockers=(
                ",".join(item.blockers)
                if item.blockers
                else "-"
            )

            print(
                f"{item.readiness:11} "
                f"{explored:14} "
                f"{item.dimension.name:32} "
                f"strategies={item.strategies_touched:<3} "
                f"blockers={blockers}"
            )


def propose(args):
    report=build_report(
        Path(args.repo_root).resolve(),
        Path(args.data_root).resolve(),
        args.schema_mode,
        args.sample_records,
    )

    profiles=profile_sources(
        report.sources,
        max_records_per_source=args.max_records_per_source,
    )

    evidence=build_evidence(
        report.sources,
        max_records_per_source=args.max_records_per_source,
    )

    proposals=generate_proposals(
        report.strategies,
        profiles,
        evidence,
    )
    summary=proposal_summary(proposals)

    print("RESEARCH HYPOTHESIS UNIVERSE")
    print("strategies:",len(report.strategies))
    print("feature profiles:",len(profiles))
    print("evidence trades:",len(evidence.trades))
    print("proposals before screening:",summary["total"])

    print("\nBY GENERATOR")
    for name,count in sorted(summary["by_generator"].items()):
        print(f"{name:32} {count}")

    print("\nBY DIMENSION")
    for name,count in sorted(summary["by_dimension"].items()):
        print(f"{name:32} {count}")

    print("\nTOP STRATEGIES BY GENERATED IDEAS")
    for name,count in summary["by_strategy"].most_common(20):
        print(f"{name:16} {count}")

    print("\nSAMPLE UNSCREENED IDEAS")
    for item in proposals[:args.show]:
        print(
            f"{item.strategy_id:10} "
            f"{item.dimension:28} "
            f"{item.generator:28} "
            f"{item.specification}"
        )


def main():
    parser=argparse.ArgumentParser(prog="strategy-lab")
    sub=parser.add_subparsers(dest="command",required=True)

    d=sub.add_parser("discover")
    d.add_argument("--repo-root",default=".")
    d.add_argument("--data-root",default="replay")
    d.add_argument("--schema-mode",choices=("sample","full"),default="sample")
    d.add_argument("--sample-records",type=int,default=2000)
    d.set_defaults(func=discover)

    c=sub.add_parser("coverage")
    c.add_argument("--repo-root",default=".")
    c.add_argument("--data-root",default="replay")
    c.add_argument("--schema-mode",choices=("sample","full"),default="sample")
    c.add_argument("--sample-records",type=int,default=2000)
    c.add_argument(
        "--memory",
        default="research_lab_state/hypothesis_memory.jsonl",
    )
    c.set_defaults(func=show_coverage)

    p=sub.add_parser("propose")
    p.add_argument("--repo-root",default=".")
    p.add_argument("--data-root",default="replay")
    p.add_argument("--schema-mode",choices=("sample","full"),default="sample")
    p.add_argument("--sample-records",type=int,default=2000)
    p.add_argument("--max-records-per-source",type=int,default=None)
    p.add_argument("--show",type=int,default=20)
    p.set_defaults(func=propose)

    args=parser.parse_args()
    args.func(args)


if __name__=="__main__":
    main()
