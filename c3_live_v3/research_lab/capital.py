"""Exact reconstruction of the production paper-accounting capital model.

Parity with this model proves accounting consistency, not that the underlying
paper prices were executable in the real market.
"""

from __future__ import annotations

import heapq
import math
from collections import defaultdict
from dataclasses import dataclass
from zoneinfo import ZoneInfo


NY=ZoneInfo("America/New_York")


@dataclass(frozen=True)
class CapitalDecision:
    setup_id: str
    strategy_id: str
    taken: bool
    shares: int
    reason: str
    equity_before: float
    cash_before: float
    deployed_before: float
    active_positions_before: int
    risk_shares: int
    position_shares: int
    cash_shares: int


@dataclass
class CapitalDayResult:
    strategy_id: str
    day: str
    signals: int
    taken: int
    skipped: int
    end_equity: float
    decisions: tuple[CapitalDecision,...]


def simulate_day(
    trades,
    *,
    starting_cash=5000.0,
    risk_fraction=0.01,
    max_position_fraction=0.20,
):
    prepared=[]

    for fallback_sequence,trade in enumerate(trades):
        if (
            not trade.entered
            or trade.entry_price is None
            or trade.stop_price is None
            or trade.exit_price is None
            or trade.exit_time is None
            or trade.entry_price<=0
            or trade.exit_price<=0
            or trade.exit_time<trade.entry_time
        ):
            continue

        sequence=(
            trade.entry_sequence
            if trade.entry_sequence is not None
            else fallback_sequence
        )

        prepared.append((
            trade.entry_time,
            int(sequence),
            trade.setup_id,
            trade,
        ))

    prepared.sort(key=lambda x:(x[0],x[1],x[2]))

    cash=float(starting_cash)
    deployed=0.0
    active=[]
    decisions=[]

    def release_until(timestamp):
        nonlocal cash,deployed
        while active and active[0][0]<=timestamp:
            _,_,shares,entry,exit_price=heapq.heappop(active)
            cash+=shares*exit_price
            deployed-=shares*entry

    for order,(_,_,_,trade) in enumerate(prepared):
        release_until(trade.entry_time)

        equity=cash+deployed
        risk_per_share=abs(trade.entry_price-trade.stop_price)

        if risk_per_share<=0 or not math.isfinite(risk_per_share):
            decisions.append(CapitalDecision(
                trade.setup_id,trade.strategy_id,
                False,0,"INVALID_RISK",
                equity,cash,deployed,len(active),
                0,0,0,
            ))
            continue

        risk_shares=math.floor(
            equity*risk_fraction/risk_per_share
        )
        position_shares=math.floor(
            equity*max_position_fraction/trade.entry_price
        )
        cash_shares=math.floor(cash/trade.entry_price)

        shares=min(
            risk_shares,
            position_shares,
            cash_shares,
        )

        if shares<1:
            reason=(
                "NO_CASH"
                if cash_shares<1
                else "SIZE_BELOW_ONE_SHARE"
            )
            decisions.append(CapitalDecision(
                trade.setup_id,trade.strategy_id,
                False,0,reason,
                equity,cash,deployed,len(active),
                risk_shares,position_shares,cash_shares,
            ))
            continue

        decisions.append(CapitalDecision(
            trade.setup_id,trade.strategy_id,
            True,shares,"TAKEN",
            equity,cash,deployed,len(active),
            risk_shares,position_shares,cash_shares,
        ))

        cost=shares*trade.entry_price
        cash-=cost
        deployed+=cost

        heapq.heappush(
            active,
            (
                trade.exit_time,
                order,
                shares,
                trade.entry_price,
                trade.exit_price,
            ),
        )

    while active:
        _,_,shares,entry,exit_price=heapq.heappop(active)
        cash+=shares*exit_price
        deployed-=shares*entry

    taken=sum(x.taken for x in decisions)
    strategy=prepared[0][3].strategy_id if prepared else ""
    day=(
        prepared[0][0].astimezone(NY).date().isoformat()
        if prepared else ""
    )

    return CapitalDayResult(
        strategy_id=strategy,
        day=day,
        signals=len(prepared),
        taken=taken,
        skipped=len(prepared)-taken,
        end_equity=cash+deployed,
        decisions=tuple(decisions),
    )


def simulate_evidence(evidence):
    grouped=defaultdict(lambda:defaultdict(list))

    for trade in evidence.trades:
        day=trade.entry_time.astimezone(NY).date().isoformat()
        grouped[day][trade.strategy_id].append(trade)

    result={}
    for day,strategies in grouped.items():
        for sid,trades in strategies.items():
            result[(day,sid)]=simulate_day(trades)

    return result
