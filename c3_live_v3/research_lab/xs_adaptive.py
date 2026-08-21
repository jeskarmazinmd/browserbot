"""Causal adaptive cross-symbol relationship selection."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class AdaptiveXSConfig:
    lookback_minutes: int = 60
    horizon_minutes: int = 1
    refresh_minutes: int = 5
    top_k: int = 3
    min_abs_correlation: float = 0.30
    min_observations: int = 30
    false_discovery_rate: float = 0.05
    ridge_alpha: float = 1e-4


@dataclass(frozen=True)
class RelationshipModel:
    target: str
    leaders: tuple[str, ...]
    correlations: tuple[float, ...]
    coefficients: tuple[float, ...]
    intercept: float
    selected_at: object


def _erf_approx(x):
    sign=np.sign(x)
    x=np.abs(x)
    t=1.0/(1.0+0.3275911*x)
    poly=(
        ((((1.061405429*t-1.453152027)*t+1.421413741)*t
        -0.284496736)*t+0.254829592)*t
    )
    return sign*(1.0-poly*np.exp(-(x*x)))


def _pvalues(corr,n):
    if n <= 3:
        return np.ones_like(corr)
    clipped=np.clip(np.abs(corr),0.0,0.999999)
    z=np.arctanh(clipped)*np.sqrt(n-3.0)
    return np.clip(1.0-_erf_approx(z/np.sqrt(2.0)),0.0,1.0)


def _bh_threshold(pvalues,q):
    values=np.asarray(pvalues,dtype=float)
    values=values[np.isfinite(values)]
    if values.size == 0:
        return None
    ordered=np.sort(values)
    critical=float(q)*np.arange(1,len(ordered)+1)/len(ordered)
    passed=np.flatnonzero(ordered <= critical)
    return None if passed.size == 0 else float(ordered[passed[-1]])


def _fit_statistics(prices,decision_pos,config):
    """Compute the expensive config-independent relationship statistics."""
    h=int(config.horizon_minutes)
    end=decision_pos-h
    start=end-int(config.lookback_minutes)+1
    if start < 1:
        return None

    returns=prices.pct_change(fill_method=None)
    future=prices.shift(-h)/prices-1.0
    x=returns.iloc[start:end+1]
    y=future.iloc[start:end+1]

    common=[
        c for c in prices.columns
        if x[c].notna().all()
        and y[c].notna().all()
        and len(x) >= int(config.min_observations)
    ]
    if len(common) < 2:
        return None

    xv=x[common].to_numpy(dtype=float)
    yv=y[common].to_numpy(dtype=float)
    xm=xv.mean(axis=0)
    ym=yv.mean(axis=0)
    xs=xv.std(axis=0,ddof=1)
    ys=yv.std(axis=0,ddof=1)
    valid=(xs > 0) & (ys > 0)
    if valid.sum() < 2:
        return None

    names=np.asarray(common,dtype=object)[valid]
    xv=xv[:,valid]
    yv=yv[:,valid]
    xm=xm[valid]
    ym=ym[valid]
    xs=xs[valid]
    ys=ys[valid]

    zx=(xv-xm)/xs
    zy=(yv-ym)/ys
    corr=np.clip((zx.T@zy)/(len(xv)-1),-1.0,1.0)
    np.fill_diagonal(corr,0.0)

    p=_pvalues(corr,len(xv))
    offdiag=~np.eye(len(names),dtype=bool)
    return {
        "names":names,
        "xv":xv,
        "yv":yv,
        "corr":corr,
        "p":p,
        "offdiag":offdiag,
        "selected_at":prices.index[decision_pos],
    }


def _models_from_statistics(stats,config):
    """Apply cheap per-experiment selection/regression to shared statistics."""
    if stats is None:
        return {}
    names=stats["names"]
    xv=stats["xv"]
    yv=stats["yv"]
    corr=stats["corr"]
    p=stats["p"]
    offdiag=stats["offdiag"]
    threshold=_bh_threshold(p[offdiag],config.false_discovery_rate)
    if threshold is None:
        return {}

    significant=(
        (p <= threshold)
        & (np.abs(corr) >= float(config.min_abs_correlation))
        & offdiag
    )

    result={}
    for target_idx,target in enumerate(names):
        candidates=np.flatnonzero(significant[:,target_idx])
        if candidates.size == 0:
            continue
        order=candidates[np.argsort(-np.abs(corr[candidates,target_idx]))]
        chosen=order[:int(config.top_k)]

        design=xv[:,chosen]
        outcome=yv[:,target_idx]
        design_mean=design.mean(axis=0)
        outcome_mean=float(outcome.mean())
        centered=design-design_mean
        centered_y=outcome-outcome_mean
        gram=centered.T@centered
        gram += float(config.ridge_alpha)*np.eye(len(chosen))
        coef=np.linalg.solve(gram,centered.T@centered_y)

        result[str(target)]=RelationshipModel(
            target=str(target),
            leaders=tuple(str(names[i]) for i in chosen),
            correlations=tuple(float(corr[i,target_idx]) for i in chosen),
            coefficients=tuple(float(v) for v in coef),
            intercept=outcome_mean-float(design_mean@coef),
            selected_at=stats["selected_at"],
        )
    return result


def _fit_models(prices,decision_pos,config):
    """Compatibility wrapper for one independently evaluated configuration."""
    return _models_from_statistics(
        _fit_statistics(prices,decision_pos,config),
        config,
    )


def generate_predictions(prices,config=AdaptiveXSConfig()):
    """Generate decisions without attaching future realized outcomes."""
    if prices is None or prices.empty:
        return pd.DataFrame()

    prices=prices.sort_index().copy()
    returns=prices.pct_change(fill_method=None)
    first=int(config.lookback_minutes)+int(config.horizon_minutes)
    last=len(prices)-int(config.horizon_minutes)
    models={}
    rows=[]

    for pos in range(first,last):
        if not models or (pos-first)%int(config.refresh_minutes)==0:
            models=_fit_models(prices,pos,config)

        current=returns.iloc[pos]
        for target,model in models.items():
            values=[current.get(x) for x in model.leaders]
            if any(pd.isna(x) for x in values):
                continue
            prediction=(
                model.intercept
                + float(np.asarray(model.coefficients) @ np.asarray(values,dtype=float))
            )
            rows.append({
                "decision_time":prices.index[pos],
                "target":target,
                "predicted_return":prediction,
                "leaders":model.leaders,
                "correlations":model.correlations,
                "relationship_selected_at":model.selected_at,
            })

    return pd.DataFrame(rows)


def score_predictions(predictions,prices,horizon_minutes=1):
    """Attach realized future returns only after decisions already exist."""
    if predictions is None or predictions.empty:
        return pd.DataFrame()

    future=prices.shift(-int(horizon_minutes))/prices-1.0
    rows=[]
    for row in predictions.to_dict("records"):
        t=row["decision_time"]
        target=row["target"]
        if t not in future.index or target not in future.columns:
            continue
        realized=future.at[t,target]
        if pd.isna(realized):
            continue
        item=dict(row)
        item["realized_return"]=float(realized)
        rows.append(item)
    return pd.DataFrame(rows)
