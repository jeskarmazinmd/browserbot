"""Prospective lifecycle decisions for adaptive XS experiments.

The lifecycle never rewrites history and never treats retrospective data as
proof.  It consumes post-birth evidence and returns recommendations; runtime
enable/disable remains a separate, safety-gated operation.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from math import erf, sqrt

import pandas as pd

from research_lab.xs_evaluator import (
    XSEvaluationPolicy,
    evaluate_scored_predictions,
)


@dataclass(frozen=True)
class XSExperiment:
    experiment_id: str
    family: str
    specification: dict
    born_at: str


@dataclass(frozen=True)
class XSLifecycleDecision:
    experiment_id: str
    state: str
    reason: str
    trades: int
    days: int
    adjusted_significant: bool = False


def experiment_id(family, specification):
    raw=json.dumps(
        {"family":str(family),"specification":specification},
        sort_keys=True,
        separators=(",",":"),
        default=str,
    ).encode()
    return hashlib.sha256(raw).hexdigest()[:20]


def new_experiment(family, specification, *, born_at=None):
    """Create an immutable prospective identity for one method/configuration."""
    when=born_at or datetime.now(timezone.utc).isoformat()
    parsed=pd.Timestamp(when)
    if parsed.tzinfo is None:
        parsed=parsed.tz_localize("UTC")
    else:
        parsed=parsed.tz_convert("UTC")
    return XSExperiment(
        experiment_id=experiment_id(family,specification),
        family=str(family),
        specification=dict(specification),
        born_at=parsed.isoformat(),
    )


def _one_sided_positive_pvalue(mean_bps, std_bps, n):
    if n < 2 or std_bps <= 0:
        return 0.0 if mean_bps > 0 else 1.0
    z=float(mean_bps)/(float(std_bps)/sqrt(int(n)))
    return 0.5*(1.0-erf(z/sqrt(2.0)))


def _bh_passes(pvalues, q):
    """Return experiment IDs passing Benjamini-Hochberg family FDR."""
    ordered=sorted(
        (float(p),str(eid)) for eid,p in pvalues.items()
        if pd.notna(p)
    )
    if not ordered:
        return set()
    last=-1
    m=len(ordered)
    for index,(pvalue,_) in enumerate(ordered,1):
        if pvalue <= float(q)*index/m:
            last=index
    if last < 0:
        return set()
    cutoff=ordered[last-1][0]
    return {eid for pvalue,eid in ordered if pvalue <= cutoff}


def evaluate_family(
    experiments,
    scored_by_experiment,
    policy=XSEvaluationPolicy(),
    *,
    family_false_discovery_rate=0.05,
):
    """Evaluate a family using prospective evidence plus family-level FDR.

    The FDR layer matters even though every experiment is forward tested: if
    hundreds of variants run simultaneously, some will look good by chance.
    """
    evaluations={}
    pvalues={}

    for experiment in experiments:
        scored=scored_by_experiment.get(experiment.experiment_id)
        evaluation=evaluate_scored_predictions(
            scored,
            policy,
            born_at=experiment.born_at,
        )
        evaluations[experiment.experiment_id]=evaluation

        if scored is None or scored.empty or evaluation.trades < 2:
            pvalues[experiment.experiment_id]=1.0
            continue

        birth=pd.Timestamp(experiment.born_at)
        decision=pd.to_datetime(scored["decision_time"],errors="coerce",utc=True)
        forward=scored.loc[decision >= birth].copy()
        # Reuse the evaluator's exact entry-time selection without outcomes
        # influencing selection, then estimate the same primary net-return test.
        from research_lab.xs_evaluator import select_opportunities
        selected=select_opportunities(forward,policy)
        if selected.empty:
            pvalues[experiment.experiment_id]=1.0
            continue
        realized=pd.to_numeric(selected["realized_return"],errors="coerce")
        side=pd.to_numeric(selected["side"],errors="coerce")
        net=(side*realized*10000.0-float(policy.primary_cost_bps)).dropna()
        if net.empty:
            pvalues[experiment.experiment_id]=1.0
            continue
        pvalues[experiment.experiment_id]=_one_sided_positive_pvalue(
            net.mean(),net.std(ddof=1),len(net)
        )

    significant=_bh_passes(pvalues,family_false_discovery_rate)
    decisions=[]
    for experiment in experiments:
        evaluation=evaluations[experiment.experiment_id]
        passes=experiment.experiment_id in significant
        if evaluation.paper_candidate and passes:
            state="EXPAND_ELIGIBLE"
            reason="prospective gates and family-level FDR passed"
        elif evaluation.paper_candidate:
            state="HOLD"
            reason="individual gates passed; family-level FDR did not"
        else:
            state="HOLD"
            reason=evaluation.reason
        decisions.append(XSLifecycleDecision(
            experiment_id=experiment.experiment_id,
            state=state,
            reason=reason,
            trades=evaluation.trades,
            days=evaluation.days,
            adjusted_significant=passes,
        ))
    return decisions
