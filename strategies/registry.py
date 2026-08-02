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
