"""Prospective evidence gates for adaptive cross-symbol predictions.

This module deliberately consumes *scored* predictions.  Relationship learning
and prediction generation stay in xs_adaptive.py so realized outcomes cannot
leak back into the predictor.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import sqrt

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class XSEvaluationPolicy:
    """Conservative defaults for deciding whether an XS method merits expansion."""

    long_only: bool = True
    min_prediction_bps: float = 5.0
    max_opportunities_per_minute: int = 5
    round_trip_cost_bps: tuple[float, ...] = (0.0, 5.0, 10.0, 20.0)
    primary_cost_bps: float = 10.0
    min_trades: int = 100
    min_days: int = 3
    min_positive_day_fraction: float = 0.60
    min_primary_net_mean_bps: float = 0.0
    min_lower_confidence_bps: float = 0.0


@dataclass(frozen=True)
class XSEvaluation:
    state: str
    reason: str
    trades: int
    days: int
    positive_day_fraction: float
    gross_mean_bps: float
    primary_net_mean_bps: float
    primary_lower_confidence_bps: float
    primary_win_rate: float
    worst_day_bps: float
    cost_stress_mean_bps: tuple[tuple[float, float], ...]

    @property
    def paper_candidate(self) -> bool:
        return self.state == "PAPER_CANDIDATE"


def _empty(reason: str) -> XSEvaluation:
    return XSEvaluation(
        state="INSUFFICIENT_EVIDENCE",
        reason=reason,
        trades=0,
        days=0,
        positive_day_fraction=0.0,
        gross_mean_bps=0.0,
        primary_net_mean_bps=0.0,
        primary_lower_confidence_bps=0.0,
        primary_win_rate=0.0,
        worst_day_bps=0.0,
        cost_stress_mean_bps=(),
    )


def select_opportunities(predictions, policy=XSEvaluationPolicy()):
    """Select only decisions that could have been selected at decision time.

    Ranking uses predicted return only.  ``realized_return`` is carried through
    for later evaluation but is never used to decide which rows survive.
    """
    if predictions is None or predictions.empty:
        return pd.DataFrame()

    required={"decision_time", "target", "predicted_return"}
    missing=required-set(predictions.columns)
    if missing:
        raise ValueError(f"missing prediction columns: {sorted(missing)}")

    work=predictions.copy()
    work["decision_time"]=pd.to_datetime(work["decision_time"],utc=True)
    work["predicted_return"]=pd.to_numeric(
        work["predicted_return"],errors="coerce"
    )
    work=work.dropna(subset=["decision_time", "target", "predicted_return"])

    threshold=float(policy.min_prediction_bps)/10000.0
    if policy.long_only:
        work=work[work["predicted_return"] >= threshold].copy()
        work["side"]=1.0
        work["selection_edge"]=work["predicted_return"]
    else:
        work=work[work["predicted_return"].abs() >= threshold].copy()
        work["side"]=np.sign(work["predicted_return"])
        work["selection_edge"]=work["predicted_return"].abs()

    if work.empty:
        return work

    # Stable tie-breaking matters: target name is known at decision time.
    work=work.sort_values(
        ["decision_time", "selection_edge", "target"],
        ascending=[True, False, True],
        kind="mergesort",
    )
    limit=max(1,int(policy.max_opportunities_per_minute))
    work=work.groupby("decision_time",sort=False,group_keys=False).head(limit)
    return work.reset_index(drop=True)


def evaluate_scored_predictions(
    scored,
    policy=XSEvaluationPolicy(),
    *,
    born_at,
):
    """Evaluate only predictions frozen on/after an experiment's birth time."""
    if scored is None or scored.empty:
        return _empty("no scored predictions")
    if "realized_return" not in scored.columns:
        raise ValueError("scored predictions require realized_return")

    birth=pd.Timestamp(born_at)
    if birth.tzinfo is None:
        birth=birth.tz_localize("UTC")
    else:
        birth=birth.tz_convert("UTC")

    work=scored.copy()
    decisions=pd.to_datetime(work["decision_time"],errors="coerce",utc=True)
    work=work.loc[decisions >= birth].copy()
    if work.empty:
        return _empty("no post-birth prospective predictions")

    chosen=select_opportunities(work,policy)
    if chosen.empty:
        return _empty("no predictions passed the entry-time selection rule")

    chosen=chosen.copy()
    chosen["realized_return"]=pd.to_numeric(
        chosen["realized_return"],errors="coerce"
    )
    chosen=chosen.dropna(subset=["realized_return"])
    if chosen.empty:
        return _empty("selected predictions have no realized outcomes")

    chosen["gross_bps"]=chosen["side"]*chosen["realized_return"]*10000.0
    chosen["day"]=chosen["decision_time"].dt.date

    primary=float(policy.primary_cost_bps)
    chosen["primary_net_bps"]=chosen["gross_bps"]-primary
    n=len(chosen)
    days=int(chosen["day"].nunique())
    gross=float(chosen["gross_bps"].mean())
    net=float(chosen["primary_net_bps"].mean())
    win=float((chosen["primary_net_bps"] > 0).mean())

    # A simple 95% lower confidence bound is intentionally a gate rather than
    # a claim of iid market returns.  Day-stability below is a separate guard.
    std=float(chosen["primary_net_bps"].std(ddof=1)) if n > 1 else 0.0
    lower=net-1.96*(std/sqrt(n)) if n > 1 else net

    daily=chosen.groupby("day",sort=True)["primary_net_bps"].mean()
    positive_fraction=float((daily > 0).mean()) if len(daily) else 0.0
    worst=float(daily.min()) if len(daily) else 0.0
    stress=tuple(
        (float(cost),float((chosen["gross_bps"]-float(cost)).mean()))
        for cost in policy.round_trip_cost_bps
    )

    blockers=[]
    if n < int(policy.min_trades):
        blockers.append(f"trades {n} < {int(policy.min_trades)}")
    if days < int(policy.min_days):
        blockers.append(f"days {days} < {int(policy.min_days)}")
    if positive_fraction < float(policy.min_positive_day_fraction):
        blockers.append("insufficient positive-day stability")
    if net <= float(policy.min_primary_net_mean_bps):
        blockers.append("primary cost-stressed mean is not positive")
    if lower <= float(policy.min_lower_confidence_bps):
        blockers.append("primary lower confidence bound is not positive")

    state="PAPER_CANDIDATE" if not blockers else "RESEARCH_ONLY"
    reason="all paper-candidate gates passed" if not blockers else "; ".join(blockers)
    return XSEvaluation(
        state=state,
        reason=reason,
        trades=n,
        days=days,
        positive_day_fraction=positive_fraction,
        gross_mean_bps=gross,
        primary_net_mean_bps=net,
        primary_lower_confidence_bps=lower,
        primary_win_rate=win,
        worst_day_bps=worst,
        cost_stress_mean_bps=stress,
    )
