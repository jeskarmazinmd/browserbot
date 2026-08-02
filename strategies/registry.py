"""Snapshot-native strategy registry.

Each strategy receives MarketSnapshot objects directly and emits SignalEvent
objects. The registry does not know strategy logic.
"""

from __future__ import annotations

import importlib


STRATEGY_MODULE_NAMES = [
    "strategy_a",
    "strategy_b",
    "strategy_d",
    "strategy_h",
    "strategy_tf1",
    "strategy_ema1",
    "strategy_ema2",
    "strategy_ema3",
    "strategy_sma1",
    "strategy_vwema1",
]


FAILED_STRATEGIES = []


def _load_strategies():
    loaded = []

    for name in STRATEGY_MODULE_NAMES:
        try:
            loaded.append(importlib.import_module(f".{name}", __package__))
        except Exception as exc:
            FAILED_STRATEGIES.append(
                {
                    "strategy": name,
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
    """Feed one snapshot into every enabled strategy."""

    signals = []
    errors = []

    for strategy in ENABLED_STRATEGIES:
        handler = getattr(strategy, "on_snapshot", None)

        if handler is None:
            errors.append(
                (
                    getattr(strategy, "STRATEGY_ID", strategy.__name__),
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
                    getattr(strategy, "STRATEGY_ID", strategy.__name__),
                    exc,
                )
            )

    return signals, errors
