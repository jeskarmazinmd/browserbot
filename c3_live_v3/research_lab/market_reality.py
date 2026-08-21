"""Independent market-reality and lifecycle safety gates."""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from research_lab.capital import simulate_evidence


class RealityState(str,Enum):
    VERIFIED="VERIFIED"
    PARTIAL="PARTIAL"
    MISSING="MISSING"


@dataclass(frozen=True)
class RealityCheck:
    name: str
    state: RealityState
    reason: str
    evidence: tuple[str,...]=()
    gaps: tuple[str,...]=()


@dataclass
class MarketRealityReport:
    checks: dict[str,RealityCheck]


@dataclass(frozen=True)
class LifecycleGate:
    action: str
    allowed: bool
    blockers: tuple[str,...]


def validate_paper_accounting(evidence,history_path):
    path=Path(history_path)

    if not path.exists():
        return RealityCheck(
            "paper_accounting",
            RealityState.MISSING,
            "no finite-capital reference history is available",
            gaps=("capital history",),
        )

    try:
        history=json.loads(path.read_text())
    except Exception as exc:
        return RealityCheck(
            "paper_accounting",
            RealityState.MISSING,
            f"capital history cannot be read: {type(exc).__name__}",
        )

    actual=simulate_evidence(evidence)
    compared=0
    mismatches=[]

    for day,strategies in history.get("days",{}).items():
        for sid,expected in strategies.items():
            result=actual.get((day,sid))
            if result is None:
                mismatches.append(f"{day}:{sid}:missing")
                continue

            compared+=1
            checks=(
                (result.signals,expected.get("signals"),0),
                (result.taken,expected.get("taken"),0),
                (result.skipped,expected.get("skipped"),0),
                (
                    result.end_equity,
                    expected.get("end_equity"),
                    1e-6,
                ),
            )

            for got,want,tolerance in checks:
                if want is None or abs(got-want)>tolerance:
                    mismatches.append(f"{day}:{sid}")
                    break

    if mismatches:
        return RealityCheck(
            "paper_accounting",
            RealityState.MISSING,
            "independent capital reconstruction disagrees with production",
            evidence=(f"comparisons={compared}",),
            gaps=tuple(mismatches[:20]),
        )

    if compared==0:
        return RealityCheck(
            "paper_accounting",
            RealityState.MISSING,
            "no comparable capital records were found",
        )

    return RealityCheck(
        "paper_accounting",
        RealityState.VERIFIED,
        "independent reconstruction exactly matches production accounting",
        evidence=(f"exact_comparisons={compared}",),
    )


def audit_market_reality(report,evidence,capital_history_path):
    checks={}

    accounting=validate_paper_accounting(
        evidence,
        capital_history_path,
    )
    checks[accounting.name]=accounting

    market_sources=[
        source for source in report.sources
        if {"minute_market_data","quote_tape"} & source.roles
    ]

    if not market_sources:
        checks["market_path"]=RealityCheck(
            "market_path",
            RealityState.MISSING,
            "no raw intraday market path is available for trade replay",
            gaps=(
                "timestamped surrounding market observations",
                "coverage across entry/exit intervals",
            ),
        )
    else:
        checks["market_path"]=RealityCheck(
            "market_path",
            RealityState.PARTIAL,
            "market-path sources exist but completeness/fidelity has not "
            "yet been independently validated",
            evidence=tuple(str(x.path) for x in market_sources),
            gaps=("coverage and staleness validation",),
        )

    market_fields={
        field.lower()
        for source in market_sources
        for field in source.fields
    }

    has_bid=any(
        x in market_fields
        for x in {"bid","bid_price","bidprice"}
    )
    has_ask=any(
        x in market_fields
        for x in {"ask","ask_price","askprice"}
    )

    if has_bid and has_ask:
        checks["executable_quotes"]=RealityCheck(
            "executable_quotes",
            RealityState.PARTIAL,
            "bid/ask fields exist but executable size, staleness and "
            "fill realism remain unvalidated",
            gaps=("size/liquidity validation","latency validation"),
        )
    else:
        checks["executable_quotes"]=RealityCheck(
            "executable_quotes",
            RealityState.MISSING,
            "historical evidence lacks validated executable bid/ask quotes",
            gaps=("bid","ask","quote age","available size"),
        )

    if evidence.trades:
        checks["execution_stress"]=RealityCheck(
            "execution_stress",
            RealityState.PARTIAL,
            "paper entries/exits can be stress-tested with hypothetical "
            "slippage, but this does not prove actual executability",
            gaps=("empirical slippage distribution",),
        )
    else:
        checks["execution_stress"]=RealityCheck(
            "execution_stress",
            RealityState.MISSING,
            "no trade evidence exists for stress testing",
        )

    checks["prospective_oos"]=RealityCheck(
        "prospective_oos",
        RealityState.MISSING,
        "strategy-version birth dates and immutable prospective evaluation "
        "windows are not yet enforced by the research lab",
        gaps=("versioned strategy birth time","minimum forward evidence"),
    )

    checks["live_fill_validation"]=RealityCheck(
        "live_fill_validation",
        RealityState.MISSING,
        "paper outcomes have not been reconciled against a controlled "
        "sample of actual broker fills",
        gaps=("actual entry fills","actual exit fills"),
    )

    return MarketRealityReport(checks)


_ACTION_REQUIREMENTS={
    "PAPER_EXPERIMENT":(
        "paper_accounting",
    ),
    "DISABLE_RUNTIME":(
        "paper_accounting",
        "market_path",
        "executable_quotes",
        "prospective_oos",
    ),
    "LIVE_CAPITAL":(
        "paper_accounting",
        "market_path",
        "executable_quotes",
        "prospective_oos",
        "live_fill_validation",
    ),
}


def gate_action(report,action):
    if action not in _ACTION_REQUIREMENTS:
        raise ValueError(f"unknown lifecycle action: {action}")

    blockers=[]

    for name in _ACTION_REQUIREMENTS[action]:
        check=report.checks.get(name)
        if check is None or check.state!=RealityState.VERIFIED:
            blockers.append(name)

    return LifecycleGate(
        action=action,
        allowed=not blockers,
        blockers=tuple(blockers),
    )
