"""Shared-computation executor for prospective adaptive XS shadows."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from research_lab.xs_adaptive import (
    _fit_statistics,
    _models_from_statistics,
)
from research_lab.xs_shadows import ready_shadow_specs, shared_fit_groups


@dataclass(frozen=True)
class XSExecutionTelemetry:
    experiments: int
    shared_groups: int
    shared_fit_calls: int
    equivalent_independent_fit_calls: int

    @property
    def fits_avoided(self):
        return self.equivalent_independent_fit_calls-self.shared_fit_calls


class XSSharedRuntime:
    """Stateful causal executor that refits each shared group only when due."""

    def __init__(self,specs=None):
        self.specs=ready_shadow_specs(specs)
        self.groups=shared_fit_groups(self.specs)
        self._models={}
        self._fit_at={}
        self.fit_calls=0

    def update(self,prices):
        if prices is None or prices.empty:
            return pd.DataFrame()
        prices=prices.sort_index().copy()
        latest=prices.index[-1]
        returns=prices.pct_change(fill_method=None)
        current=returns.iloc[-1]
        rows=[]

        for key,members in self.groups.items():
            exemplar=members[0].config
            h=int(exemplar.horizon_minutes)
            minimum=int(exemplar.lookback_minutes)+h+1
            if len(prices) < minimum:
                continue

            last_fit=self._fit_at.get(key)
            refresh_seconds=int(exemplar.refresh_minutes)*60
            due=(
                last_fit is None
                or (latest-last_fit).total_seconds() >= refresh_seconds
            )
            if due:
                stats=_fit_statistics(prices,len(prices)-1,exemplar)
                self.fit_calls+=1
                self._models[key]={
                    spec.name:_models_from_statistics(stats,spec.config)
                    for spec in members
                }
                self._fit_at[key]=latest

            models_by_name=self._models.get(key,{})
            for spec in members:
                for model in models_by_name.get(spec.name,{}).values():
                    row=_prediction_row(spec,model,current,latest)
                    if row is not None:
                        rows.append(row)

        result=pd.DataFrame(rows)
        if not result.empty:
            result=result.sort_values(
                ["shadow_name","decision_time","target"],kind="mergesort"
            ).reset_index(drop=True)
        return result


def _prediction_row(spec,model,current,decision_time):
    values=[current.get(x) for x in model.leaders]
    if any(pd.isna(x) for x in values):
        return None
    prediction=(
        model.intercept
        + float(np.asarray(model.coefficients) @ np.asarray(values,dtype=float))
    )
    return {
        "shadow_name":spec.name,
        "dimension":spec.dimension,
        "decision_time":decision_time,
        "target":model.target,
        "predicted_return":prediction,
        "leaders":model.leaders,
        "correlations":model.correlations,
        "relationship_selected_at":model.selected_at,
    }


def generate_shared_predictions(prices,specs=None):
    """Generate shadow predictions while reusing identical expensive fits.

    Returns ``(predictions, telemetry)``.  No realized outcome is attached.
    """
    ready=ready_shadow_specs(specs)
    groups=shared_fit_groups(ready)
    if prices is None or prices.empty or not ready:
        return pd.DataFrame(),XSExecutionTelemetry(
            len(ready),len(groups),0,0
        )

    prices=prices.sort_index().copy()
    returns=prices.pct_change(fill_method=None)
    rows=[]
    shared_calls=0
    independent_calls=0

    for _,members in groups.items():
        exemplar=members[0].config
        h=int(exemplar.horizon_minutes)
        first=int(exemplar.lookback_minutes)+h
        last=len(prices)-h
        models_by_name={}

        for pos in range(first,last):
            refresh=(
                not models_by_name
                or (pos-first)%int(exemplar.refresh_minutes)==0
            )
            if refresh:
                stats=_fit_statistics(prices,pos,exemplar)
                shared_calls+=1
                independent_calls+=len(members)
                models_by_name={
                    spec.name:_models_from_statistics(stats,spec.config)
                    for spec in members
                }

            current=returns.iloc[pos]
            when=prices.index[pos]
            for spec in members:
                for model in models_by_name.get(spec.name,{}).values():
                    row=_prediction_row(spec,model,current,when)
                    if row is not None:
                        rows.append(row)

    result=pd.DataFrame(rows)
    if not result.empty:
        result=result.sort_values(
            ["shadow_name","decision_time","target"],
            kind="mergesort",
        ).reset_index(drop=True)
    return result,XSExecutionTelemetry(
        experiments=len(ready),
        shared_groups=len(groups),
        shared_fit_calls=shared_calls,
        equivalent_independent_fit_calls=independent_calls,
    )
