"""Cadence-aware snapshot-native strategy registry."""

from __future__ import annotations

import importlib
from strategy_diagnostics import diagnostics

from . import strategy_a
from . import strategy_b
from . import strategy_c1f1
from . import strategy_c1f1mid, strategy_c1f1r65, strategy_c1f1pb15
from . import strategy_j2t15, strategy_j2mid, strategy_j2rb30
from . import (
    strategy_c3sc,
    strategy_c3n20, strategy_c3n25, strategy_c3n30, strategy_c3n40, strategy_c3n50,
    strategy_c3n25a05, strategy_c3n25a10, strategy_c3n25a20, strategy_c3n25a50,
    strategy_c3n25t15, strategy_c3n25t60,
    strategy_c3n25s10, strategy_c3n25s15, strategy_c3n25s25,
    strategy_c3n25be,
    strategy_c3n25w20, strategy_c3n25w30,
    strategy_c3p25, strategy_c3l25,
    strategy_c3l25q2, strategy_c3l25q4,
    strategy_c3l25d05, strategy_c3l25d20,
)
from . import strategy_d
from . import strategy_h
from . import strategy_c2t9, strategy_c2t35, strategy_c1t9, strategy_gt9, strategy_et29, strategy_pt325, strategy_pt325315, strategy_pmid, strategy_ht5, strategy_qmid, strategy_qv425, strategy_lt65


FLASH_STRATEGY_MODULES = {
    module.STRATEGY_ID: module
    for module in (
        strategy_a, strategy_b, strategy_c1f1, strategy_d, strategy_h,
        strategy_c1f1mid, strategy_c1f1r65, strategy_c1f1pb15,
        strategy_j2t15, strategy_j2mid, strategy_j2rb30,
        strategy_c2t9, strategy_c2t35, strategy_c1t9, strategy_gt9, strategy_et29, strategy_pt325, strategy_pt325315, strategy_pmid, strategy_ht5, strategy_qmid, strategy_qv425, strategy_lt65,
        strategy_c3sc,
        strategy_c3n20, strategy_c3n25, strategy_c3n30, strategy_c3n40, strategy_c3n50,
        strategy_c3n25a05, strategy_c3n25a10, strategy_c3n25a20, strategy_c3n25a50,
        strategy_c3n25t15, strategy_c3n25t60,
        strategy_c3n25s10, strategy_c3n25s15, strategy_c3n25s25,
    strategy_c3n25be,
    strategy_c3n25w20, strategy_c3n25w30,
        strategy_c3p25, strategy_c3l25,
    strategy_c3l25q2, strategy_c3l25q4,
    strategy_c3l25d05, strategy_c3l25d20,
    )
}


def flash_strategy_configs():
    return {
        strategy_id: dict(module.CONFIG)
        for strategy_id, module in FLASH_STRATEGY_MODULES.items()
    }


def flash_accepts(strategy_id, event, global_max_drop_pct):
    return FLASH_STRATEGY_MODULES[strategy_id].accepts_flash(
        event,
        global_max_drop_pct,
    )


def refresh_flash_entry(strategy_id, event, current_price):
    return FLASH_STRATEGY_MODULES[strategy_id].refresh_event_for_entry(
        event,
        current_price,
    )


def validate_flash_entry(
    strategy_id,
    event,
    default_min_remaining_upside_pct,
):
    module = FLASH_STRATEGY_MODULES[strategy_id]

    try:
        return module.validate_confirmed_entry(
            event,
            default_min_remaining_upside_pct,
        )
    except TypeError:
        return module.validate_confirmed_entry(event)



STRATEGY_CLASSES = [
    ("strategy_ema1", "EMA1Strategy"),
    ("strategy_ema1t50", "Strategy"),
    ("strategy_ema1v15", "Strategy"),
    ("strategy_ema1rr", "Strategy"),
    ("strategy_ema2", "EMA2Strategy"),
    ("strategy_ema3", "EMA3Strategy"),
    ("strategy_sma1", "SMA1Strategy"),
    ("strategy_vwema1", "VWEMA1Strategy"),
    ("strategy_tf1", "TF1Strategy"),
    ("strategy_rs1", "RS1Strategy"),
    ("strategy_rs2", "RS2Strategy"),
    ("strategy_rs3", "RS3Strategy"),
    ("strategy_m1", "M1Strategy"),
    ("strategy_m2", "M2Strategy"),
    ("strategy_m3", "M3Strategy"),
    ("strategy_mc1", "MC1Strategy"),
    ("strategy_tl1", "TL1Strategy"),
    ("strategy_av1", "AV1Strategy"),
    ("strategy_td1", "TD1Strategy"),
    ("strategy_sh1", "SH1Strategy"),
    ("strategy_cv1", "CV1Strategy"),
    ("strategy_hl1", "HL1Strategy"),
    ("strategy_vt1", "VT1Strategy"),
    ("strategy_pd1", "PD1Strategy"),
    ("strategy_bo1", "BO1Strategy"),
    ("strategy_ge1", "GE1Strategy"),
    ("strategy_gm1", "GM1Strategy"),
    ("strategy_gp1", "GP1Strategy"),
    ("strategy_gr1", "GR1Strategy"),
    ("strategy_gt1", "GT1Strategy"),
    ("strategy_or1", "OR1Strategy"),
    ("strategy_spy_or5", "SPYOR5Strategy"),
    ("strategy_spy_or15", "SPYOR15Strategy"),
    ("strategy_spy_or30", "SPYOR30Strategy"),
    ("strategy_spy_mom1", "SPYMOM1Strategy"),
    ("strategy_spy_mr1", "SPYMR1Strategy"),
    ("strategy_spy_br1", "SPYBR1Strategy"),
    ("strategy_spy_xa1", "SPYXA1Strategy"),
    ("strategy_spy_ens1", "SPYENS1Strategy"),
]


# A/B/D/H remain on the established pending-rebound engine until their
# snapshot replacements reproduce the full legacy event schema.
LEGACY_FLASH_STRATEGY_IDS = frozenset({
    "A",
    "B",
    "D",
    "H",
})


# These strategies require current-cycle prices or explicitly use raw,
# time-weighted snapshot behavior. They are not activated in the runner until
# their retained state is compacted and complete-cycle tick delivery exists.
# Every snapshot strategy now consumes completed-minute observations.
# No strategy retains duplicated raw-tick history.
TICK_STRATEGY_IDS = frozenset()

REPORTING_STRATEGY_MODULES = {}

# These reporting-era definitions are now evaluated prospectively from their
# live A/B/D parent signals by strategies.derived_runtime.  Keeping this set
# explicit makes operational diagnostics distinguish active derived modules
# from definitions that remain reporting-only.
DERIVED_RUNTIME_STRATEGY_IDS = frozenset({
    "C1", "C2", "C3", "C4", "E", "F", "G", "I",
    "J1", "J2", "J3", "J4", "J5", "J6",
    "K1", "K2", "K3", "K4", "K5", "K6", "K7", "K8", "K9",
    "L", "M", "N", "O", "P", "Q", "R", "S",
})

for _strategy_id in (
    "C1", "C2", "C3", "C4", "E", "F", "G", "I",
    "J1", "J2", "J3", "J4", "J5", "J6",
    "K1", "K2", "K3", "K4", "K5", "K6", "K7", "K8", "K9",
    "L", "M", "N", "O", "P", "Q", "R", "S",
):
    REPORTING_STRATEGY_MODULES[_strategy_id] = importlib.import_module(
        f".strategy_{_strategy_id.lower()}",
        __package__,
    )


FAILED_STRATEGIES = []


def _strategy_id(strategy) -> str:
    return str(
        getattr(
            strategy,
            "name",
            getattr(strategy, "STRATEGY_ID", type(strategy).__name__),
        )
    )


def _load_strategies():
    loaded = []

    for module_name, class_name in STRATEGY_CLASSES:
        try:
            module = importlib.import_module(
                f".{module_name}",
                __package__,
            )

            cls = getattr(module, class_name)
            loaded.append(cls())

        except Exception as exc:
            FAILED_STRATEGIES.append(
                {
                    "strategy": module_name,
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )

    return loaded


ENABLED_STRATEGIES = _load_strategies()

FLASH_STRATEGIES = list(FLASH_STRATEGY_MODULES.values())

TICK_STRATEGIES = [
    strategy
    for strategy in ENABLED_STRATEGIES
    if _strategy_id(strategy) in TICK_STRATEGY_IDS
]

MINUTE_STRATEGIES = [
    strategy
    for strategy in ENABLED_STRATEGIES
    if (
        _strategy_id(strategy) not in LEGACY_FLASH_STRATEGY_IDS
        and _strategy_id(strategy) not in TICK_STRATEGY_IDS
    )
]


for failed in FAILED_STRATEGIES:
    print(
        "STRATEGY_LOAD_WARNING",
        failed["strategy"],
        failed["error"],
        flush=True,
    )


def _evaluate(snapshot, strategies):
    signals = []
    errors = []

    for strategy in strategies:
        strategy_id = _strategy_id(strategy)
        handler = getattr(strategy, "on_snapshot", None)

        if handler is None:
            errors.append(
                (
                    strategy_id,
                    RuntimeError("strategy missing on_snapshot"),
                )
            )
            continue

        try:
            result = handler(snapshot)

            if result:
                signals.extend(result)
            diagnostics.evaluated(
                strategy_id,
                snapshot.timestamp,
                len(snapshot.quotes),
                signal_count=len(result or []),
                nearest_miss=getattr(strategy, "nearest_miss", None),
            )

        except Exception as exc:
            diagnostics.evaluated(
                strategy_id,
                snapshot.timestamp,
                len(snapshot.quotes),
                error=f"{type(exc).__name__}: {exc}",
                nearest_miss=getattr(strategy, "nearest_miss", None),
            )
            errors.append(
                (
                    strategy_id,
                    exc,
                )
            )

    return signals, errors


def on_snapshot(snapshot):
    """Evaluate every loaded strategy; intended for tests and validation."""
    return _evaluate(snapshot, ENABLED_STRATEGIES)


def on_minute_snapshot(snapshot):
    """Evaluate bounded-state completed-minute strategies."""
    return _evaluate(snapshot, MINUTE_STRATEGIES)


def on_tick_snapshot(snapshot):
    """Evaluate tick/hybrid strategies after tick routing is activated."""
    return _evaluate(snapshot, TICK_STRATEGIES)
