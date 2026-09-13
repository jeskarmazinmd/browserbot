"""Bounded paper-only runtime for Factory-generated strategies.

This runtime consumes observations supplied by the existing bot/data
pipeline. It has no broker client and no market-data network client.
"""

from __future__ import annotations

from dataclasses import asdict
import json
import os
from pathlib import Path
from typing import Any, Iterable, Mapping

from research_tools.module_factory.generated_loader import (
    load_active_generated_strategies,
)


class FactoryShadowRuntime:
    def __init__(
        self,
        *,
        registry_path: Path,
        spec_path: Path,
        state_path: Path,
        signal_path: Path,
        max_shadow_modules: int,
        max_signals_per_cycle: int = 100,
    ):
        if max_shadow_modules < 1:
            raise ValueError(
                "max_shadow_modules must be positive"
            )

        if max_signals_per_cycle < 1:
            raise ValueError(
                "max_signals_per_cycle must be positive"
            )

        self.registry_path = Path(registry_path)
        self.spec_path = Path(spec_path)
        self.state_path = Path(state_path)
        self.signal_path = Path(signal_path)

        self.max_shadow_modules = int(
            max_shadow_modules
        )
        self.max_signals_per_cycle = int(
            max_signals_per_cycle
        )

        self.seen = set()
        self._load_state()

    def _load_state(self):
        if not self.state_path.exists():
            return

        payload = json.loads(
            self.state_path.read_text()
        )

        self.seen = set(
            payload.get("seen", [])
        )

    def _save_state(self):
        self.state_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        temporary = self.state_path.with_suffix(
            self.state_path.suffix + ".tmp"
        )

        temporary.write_text(
            json.dumps(
                {
                    "version": 1,
                    "seen": sorted(self.seen),
                },
                indent=2,
                sort_keys=True,
            )
            + "\n"
        )

        temporary.replace(self.state_path)

    def _append_signal(self, signal):
        self.signal_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        payload = asdict(signal)

        with self.signal_path.open("a") as handle:
            handle.write(
                json.dumps(
                    payload,
                    default=str,
                    sort_keys=True,
                )
                + "\n"
            )
            handle.flush()
            os.fsync(handle.fileno())

    @staticmethod
    def _signal_key(signal) -> str:
        return (
            f"{signal.strategy_id}|"
            f"{signal.symbol}|"
            f"{signal.timestamp}"
        )

    def evaluate(
        self,
        rows: Iterable[Mapping[str, Any]],
    ):
        strategies = load_active_generated_strategies(
            registry_path=self.registry_path,
            spec_path=self.spec_path,
            max_shadow_modules=self.max_shadow_modules,
        )

        if len(strategies) > self.max_shadow_modules:
            raise RuntimeError(
                "Factory runtime capacity exceeded"
            )

        emitted = []

        for row in rows:
            symbol = row.get("symbol")
            timestamp = row.get("timestamp")
            features = row.get("features", {})

            if not symbol or timestamp is None:
                continue

            if not isinstance(features, Mapping):
                continue

            for strategy in strategies:
                if (
                    len(emitted)
                    >= self.max_signals_per_cycle
                ):
                    self._save_state()
                    return tuple(emitted)

                signal = strategy.evaluate_row(
                    symbol=str(symbol),
                    timestamp=timestamp,
                    features=features,
                )

                if signal is None:
                    continue

                key = self._signal_key(signal)

                if key in self.seen:
                    continue

                self.seen.add(key)
                self._append_signal(signal)
                emitted.append(signal)

        self._save_state()
        return tuple(emitted)
