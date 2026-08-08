"""Bounded shadow-experiment planning for prospective XS research.

Many logical experiments may share one expensive relationship computation.
This module plans experiments only; it does not silently activate or deploy
them.  New XS mechanisms remain visible as research lanes until an engine for
that mechanism exists and is explicitly enabled.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

from research_lab.xs_adaptive import AdaptiveXSConfig
from research_lab.xs_lifecycle import new_experiment


@dataclass(frozen=True)
class XSShadowSpec:
    name: str
    dimension: str
    engine: str
    config: AdaptiveXSConfig | None
    state: str = "READY"


@dataclass(frozen=True)
class XSComputePlan:
    shadow_experiments: int
    shared_fit_groups: int
    symbols: int
    largest_matrix_mib: float
    estimated_peak_fit_mib: float
    allowed: bool
    reason: str


RESEARCH_LANES=(
    "cross_symbol_lead_lag",
    "cross_symbol_divergence",
    "cross_symbol_peer_basket",
    "cross_symbol_residual",
    "cross_symbol_regime_adaptation",
)


def seed_shadow_specs():
    """Return a deliberately non-Cartesian first prospective XS population.

    The variants span time scale, forecast horizon, sparsity and statistical
    strictness without exploding every parameter into a combinatorial grid.
    """
    variants=(
        ("LL30H1K1",30,1,5,1,.30,.05),
        ("LL30H2K3",30,2,5,3,.30,.05),
        ("LL60H1K1",60,1,5,1,.30,.05),
        ("LL60H1K3",60,1,5,3,.30,.05),
        ("LL60H2K3",60,2,5,3,.30,.05),
        ("LL60H5K3",60,5,5,3,.30,.05),
        ("LL120H1K3",120,1,15,3,.30,.05),
        ("LL120H5K3",120,5,15,3,.30,.05),
        ("LL60LOOSE",60,1,5,3,.20,.05),
        ("LL60STRICT",60,1,5,3,.40,.01),
    )
    result=[]
    for name,lookback,horizon,refresh,top_k,min_corr,fdr in variants:
        result.append(XSShadowSpec(
            name=name,
            dimension="cross_symbol_lead_lag",
            engine="adaptive_lead_lag_v1",
            config=AdaptiveXSConfig(
                lookback_minutes=lookback,
                horizon_minutes=horizon,
                refresh_minutes=refresh,
                top_k=top_k,
                min_abs_correlation=min_corr,
                min_observations=min(30,lookback-5),
                false_discovery_rate=fdr,
            ),
        ))

    # Keep the broader search space explicit without pretending mechanisms
    # exist before their causal predictors and tests have been implemented.
    for lane in RESEARCH_LANES[1:]:
        result.append(XSShadowSpec(
            name=f"PLANNED_{lane.upper()}",
            dimension=lane,
            engine="not_implemented",
            config=None,
            state="PLANNED",
        ))
    return tuple(result)


def ready_shadow_specs(specs=None):
    source=seed_shadow_specs() if specs is None else tuple(specs)
    return tuple(x for x in source if x.state=="READY")


def _fit_key(spec):
    config=spec.config
    return (
        spec.engine,
        int(config.lookback_minutes),
        int(config.horizon_minutes),
        int(config.refresh_minutes),
        int(config.min_observations),
    )


def shared_fit_groups(specs=None):
    """Group variants that can reuse the expensive return/relationship fit."""
    groups={}
    for spec in ready_shadow_specs(specs):
        groups.setdefault(_fit_key(spec),[]).append(spec)
    return {key:tuple(value) for key,value in groups.items()}


def compute_plan(
    symbols,
    specs=None,
    *,
    max_shadows=24,
    max_shared_fit_groups=8,
    max_peak_fit_mib=256.0,
):
    """Fail closed if a proposed shadow population exceeds its compute budget."""
    ready=ready_shadow_specs(specs)
    groups=shared_fit_groups(ready)
    n=max(0,int(symbols))
    matrix_mib=(n*n*8)/(1024**2)
    # corr + p-values + standardized work arrays + boolean masks coexist.
    # This is a conservative planning estimate, not an RSS measurement; local
    # benchmark telemetry must replace it before production activation.
    peak_fit_mib=matrix_mib*3.5
    blockers=[]
    if len(ready) > int(max_shadows):
        blockers.append("shadow experiment budget exceeded")
    if len(groups) > int(max_shared_fit_groups):
        blockers.append("shared fit-group budget exceeded")
    if peak_fit_mib > float(max_peak_fit_mib):
        blockers.append("relationship fit working-set budget exceeded")
    return XSComputePlan(
        shadow_experiments=len(ready),
        shared_fit_groups=len(groups),
        symbols=n,
        largest_matrix_mib=matrix_mib,
        estimated_peak_fit_mib=peak_fit_mib,
        allowed=not blockers,
        reason="within compute budget" if not blockers else "; ".join(blockers),
    )


def activate(specs=None, *, born_at):
    """Assign a prospective birth time only to implemented, ready shadows."""
    experiments=[]
    for spec in ready_shadow_specs(specs):
        specification={
            "shadow_name":spec.name,
            "engine":spec.engine,
            "config":asdict(spec.config),
        }
        experiments.append(new_experiment(
            spec.dimension,
            specification,
            born_at=born_at,
        ))
    return tuple(experiments)
