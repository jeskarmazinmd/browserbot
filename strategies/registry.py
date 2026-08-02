"""Snapshot-native strategy registry."""

from __future__ import annotations

import importlib


STRATEGY_CLASSES = [
    ("strategy_a", "StrategyA"),
    ("strategy_b", "StrategyB"),
    ("strategy_d", "StrategyD"),
    ("strategy_h", "StrategyH"),
    ("strategy_ema1", "EMA1Strategy"),
    ("strategy_ema2", "EMA2Strategy"),
    ("strategy_ema3", "EMA3Strategy"),
    ("strategy_sma1", "SMA1Strategy"),
    ("strategy_vwema1", "VWEMA1Strategy"),
    ("strategy_tf1", "TF1Strategy"),
    ("strategy_rs1", "RS1Strategy"),
    ("strategy_rs2", "RS2Strategy"),
    ("strategy_rs3", "RS3Strategy"),
    ("strategy_ve1", "VE1Strategy"),
    ("strategy_vr1", "VR1Strategy"),
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
]


FAILED_STRATEGIES = []


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


for failed in FAILED_STRATEGIES:
    print(
        "STRATEGY_LOAD_WARNING",
        failed["strategy"],
        failed["error"],
        flush=True,
    )


def on_snapshot(snapshot):
    signals = []
    errors = []

    for strategy in ENABLED_STRATEGIES:
        handler = getattr(strategy, "on_snapshot", None)

        if handler is None:
            errors.append(
                (
                    type(strategy).__name__,
                    RuntimeError("strategy missing on_snapshot"),
                )
            )
            continue

        try:
            result = handler(snapshot)

            if result:
                signals.extend(result)

        except Exception as exc:
            errors.append(
                (
                    type(strategy).__name__,
                    exc,
                )
            )

    return signals, errors
