"""
End-to-end bounded Module Factory shadow worker.

Pipeline:
existing collector tape
    -> completed minute feed
    -> rolling live features
    -> FactoryShadowRuntime
    -> paper-only signal journal

No broker client.
No market-data client.
No order placement.
No discovery or validation data access.
"""

from __future__ import annotations

import json
import os
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from research_tools.module_factory.live_feature_engine import (
    LiveFeatureEngine,
)
from research_tools.module_factory.live_minute_feed import (
    CompletedMinute,
    LiveMinuteTapeFeed,
    today_tape,
)
from research_tools.module_factory.shadow_runtime import (
    FactoryShadowRuntime,
)
from research_tools.module_factory.resource_governor import (
    ResourceDecision,
    ResourceGovernor,
)
from research_tools.module_factory.executable_quote_feed import ExecutableMinuteQuoteFeed
from research_tools.module_factory.prospective_tracker import FactoryProspectiveTracker
from research_tools.module_factory.shadow_lifecycle import FactoryShadowLifecycle
from research_tools.module_factory.population_manager import FactoryPopulationManager
from research_tools.module_factory.module_registry import FactoryModuleRegistry, ModuleState
from research_tools.module_factory.adaptive_capacity import AdaptiveCapacityScaler


DEFAULT_MAX_SHADOW_MODULES = 100
DEFAULT_MAX_SIGNALS_PER_CYCLE = 100
DEFAULT_POLL_SECONDS = 2.0
DEFAULT_MAX_MINUTES_PER_CYCLE = 5


@dataclass(frozen=True)
class WorkerCycleResult:
    completed_minutes: int
    feature_rows: int
    signals: int
    elapsed_seconds: float
    resource_allowed: bool = True
    resource_reasons: tuple[str, ...] = ()
    executable_entries: int = 0
    executable_exits: int = 0
    rejected_entries: int = 0
    backlog_minutes: int = 0


class FactoryShadowWorker:
    def __init__(
        self,
        *,
        tape_path: Path,
        registry_path: Path,
        spec_path: Path,
        state_path: Path,
        signal_path: Path,
        worker_state_path: Path | None = None,
        max_shadow_modules: int = DEFAULT_MAX_SHADOW_MODULES,
        max_signals_per_cycle: int = DEFAULT_MAX_SIGNALS_PER_CYCLE,
        max_minutes_per_cycle: int = DEFAULT_MAX_MINUTES_PER_CYCLE,
        history_minutes: int = 75,
        start_at_end: bool = True,
        resource_governor: ResourceGovernor | None = None,
        resource_data_root: Path = Path("/data"),
        executable_quote_root: Path | None = None,
        prospective_state_path: Path | None = None,
        prospective_outcomes_path: Path | None = None,
        health_path: Path | None = None,
        healthy_checks_to_resume: int = 3,
        min_prune_sessions: int = 10,
        min_prune_events: int = 100,
        capacity_scaler: AdaptiveCapacityScaler | None = None,
    ):
        if max_minutes_per_cycle < 1:
            raise ValueError(
                "max_minutes_per_cycle must be positive"
            )

        self.max_minutes_per_cycle = int(
            max_minutes_per_cycle
        )

        self.worker_state_path = (
            Path(worker_state_path)
            if worker_state_path is not None
            else Path(state_path).with_name(
                "worker_state.json"
            )
        )

        self._pending_minutes = deque()
        self._load_worker_state()

        self.resource_governor = resource_governor
        self.resource_data_root = Path(
            resource_data_root
        )
        self.health_path = Path(health_path) if health_path else None
        self.healthy_checks_to_resume = max(1, int(healthy_checks_to_resume))
        self._resource_paused = False
        self._healthy_streak = 0
        self._last_cycle_seconds = 0.0
        self._capacity_recommendation = None

        self.feed = LiveMinuteTapeFeed(
            tape_path,
            history_minutes=history_minutes,
            start_at_end=start_at_end,
        )

        self.features = LiveFeatureEngine(
            max_history_minutes=max(
                61,
                history_minutes,
            )
        )

        self.runtime = FactoryShadowRuntime(
            registry_path=registry_path,
            spec_path=spec_path,
            state_path=state_path,
            signal_path=signal_path,
            max_shadow_modules=max_shadow_modules,
            max_signals_per_cycle=max_signals_per_cycle,
        )
        factory_root = Path(state_path).parent
        self.executable_feed = ExecutableMinuteQuoteFeed(
            Path(executable_quote_root or (self.resource_data_root / "research_market")),
            max_quote_age_seconds=float(os.environ.get("FACTORY_MAX_QUOTE_AGE_SECONDS", "90")),
        )
        self.prospective = FactoryProspectiveTracker(
            state_path=Path(prospective_state_path or (factory_root / "bidask_active.json")),
            outcomes_path=Path(prospective_outcomes_path or (factory_root / "bidask_outcomes.jsonl")),
        )
        self.lifecycle = FactoryShadowLifecycle(
            registry_path=Path(registry_path),
            outcomes_path=self.prospective.outcomes_path,
            max_shadow_modules=max_shadow_modules,
            min_sessions=min_prune_sessions,
            min_events=min_prune_events,
        )
        self.population = FactoryPopulationManager(
            registry_path=Path(registry_path), spec_path=Path(spec_path),
            max_shadow_modules=max_shadow_modules,
        )
        self.capacity_scaler = capacity_scaler or AdaptiveCapacityScaler(
            hard_max=max_shadow_modules,
            initial_target=min(5, max_shadow_modules),
            memory_reserve_mb=(
                getattr(resource_governor, "min_memory_available_mb", 1024)
                if resource_governor is not None else 1024
            ),
            storage_reserve_mb=(
                getattr(resource_governor, "min_data_free_mb", 1024)
                if resource_governor is not None else 1024
            ),
            max_load_per_cpu=(
                getattr(resource_governor, "max_load_per_cpu", 1.25)
                if resource_governor is not None else 1.25
            ),
        )
        # Close the journal->tracker crash window before processing another
        # market minute. Reconciliation is safe to repeat.
        self.prospective.reconcile_signal_journal(
            self.runtime.signal_path, self.executable_feed
        )

    def _write_health(self, payload: dict) -> None:
        if self.health_path is None:
            return
        self.health_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.health_path.with_suffix(self.health_path.suffix + ".tmp")
        temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
        temporary.replace(self.health_path)

    def _load_worker_state(self) -> None:
        if not self.worker_state_path.exists():
            return

        payload = json.loads(
            self.worker_state_path.read_text()
        )

        if payload.get("version") != 1:
            raise RuntimeError(
                "Unsupported Factory worker state version"
            )

        pending = payload.get("pending_minutes", [])

        if not isinstance(pending, list):
            raise RuntimeError(
                "Invalid Factory worker pending state"
            )

        restored = deque()

        for item in pending:
            if not isinstance(item, dict):
                raise RuntimeError(
                    "Invalid Factory worker minute state"
                )

            minute_raw = item.get("minute")
            prices_raw = item.get("prices")

            if (
                not isinstance(minute_raw, str)
                or not isinstance(prices_raw, dict)
            ):
                raise RuntimeError(
                    "Invalid Factory worker minute payload"
                )

            restored.append(
                CompletedMinute(
                    minute=datetime.fromisoformat(
                        minute_raw
                    ),
                    prices={
                        str(symbol): float(price)
                        for symbol, price
                        in prices_raw.items()
                    },
                )
            )

        self._pending_minutes = restored

    def _save_worker_state(self) -> None:
        self.worker_state_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        temporary = self.worker_state_path.with_suffix(
            self.worker_state_path.suffix + ".tmp"
        )

        payload = {
            "version": 1,
            "pending_minutes": [
                {
                    "minute": item.minute.isoformat(),
                    "prices": item.prices,
                }
                for item in self._pending_minutes
            ],
        }

        temporary.write_text(
            json.dumps(
                payload,
                indent=2,
                sort_keys=True,
            )
            + "\n"
        )

        temporary.replace(
            self.worker_state_path
        )

    def close(self):
        self.feed.close()

    def cycle(self) -> WorkerCycleResult:
        started = time.monotonic()

        if self.resource_governor is not None:
            decision = self.resource_governor.check(
                data_root=self.resource_data_root
            )

            if not decision.allowed:
                self._resource_paused = True
                self._healthy_streak = 0
            elif self._resource_paused:
                self._healthy_streak += 1
                if self._healthy_streak >= self.healthy_checks_to_resume:
                    self._resource_paused = False

            if self._resource_paused:
                reasons = decision.reasons or ("waiting_for_consecutive_healthy_checks",)
                self._write_health({
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                    "status": "PAUSED", "paper_only": True,
                    "broker_execution_enabled": False,
                    "reasons": reasons, "healthy_streak": self._healthy_streak,
                    "healthy_checks_to_resume": self.healthy_checks_to_resume,
                    "backlog_minutes": len(self._pending_minutes),
                    "resources": decision.snapshot.__dict__,
                })
                return WorkerCycleResult(
                    completed_minutes=0,
                    feature_rows=0,
                    signals=0,
                    elapsed_seconds=(
                        time.monotonic() - started
                    ),
                    resource_allowed=False,
                    resource_reasons=reasons,
                    backlog_minutes=len(self._pending_minutes),
                )

            self._capacity_recommendation = self.capacity_scaler.recommend(
                decision.snapshot,
                cycle_seconds=self._last_cycle_seconds,
                backlog_minutes=len(self._pending_minutes),
            )
            self.population.reconcile_resource_capacity(
                self._capacity_recommendation.target
            )

        if not self._pending_minutes:
            polled = self.feed.poll()

            if polled:
                self._pending_minutes.extend(polled)

                # Persist read-ahead before any minute
                # is processed. This makes deferred
                # completed minutes restart-recoverable.
                self._save_worker_state()

        completed_count = 0
        feature_count = 0
        signal_count = 0
        executable_entries = 0
        executable_exits = 0
        rejected_entries = 0

        reconciled = self.prospective.reconcile_signal_journal(
            self.runtime.signal_path, self.executable_feed
        )
        executable_entries += reconciled["enrolled"]
        rejected_entries += reconciled["rejected"]

        while (
            self._pending_minutes
            and completed_count
            < self.max_minutes_per_cycle
        ):
            # Do not remove the minute until all
            # downstream processing succeeds.
            minute = self._pending_minutes[0]

            executable_quotes = self.executable_feed.quotes_for_minute(minute.minute)
            executable_exits += len(
                self.prospective.consume_executable_minute(minute.minute, executable_quotes)
            )

            rows = self.features.consume(minute)
            feature_count += len(rows)

            runtime_rows = (
                {
                    "symbol": row.symbol,
                    "timestamp": row.timestamp,
                    "features": row.features,
                }
                for row in rows
            )

            emitted = self.runtime.evaluate(
                runtime_rows
            )
            reconciled = self.prospective.reconcile_signal_journal(
                self.runtime.signal_path, self.executable_feed
            )
            executable_entries += reconciled["enrolled"]
            rejected_entries += reconciled["rejected"]

            signal_count += len(emitted)

            self._pending_minutes.popleft()
            completed_count += 1

            # Commit successful processing. A crash
            # before this save causes safe replay,
            # rather than silent minute loss.
            self._save_worker_state()

        result = WorkerCycleResult(
            completed_minutes=completed_count,
            feature_rows=feature_count,
            signals=signal_count,
            elapsed_seconds=(
                time.monotonic() - started
            ),
            executable_entries=executable_entries,
            executable_exits=executable_exits,
            rejected_entries=rejected_entries,
            backlog_minutes=len(self._pending_minutes),
        )
        self._last_cycle_seconds = result.elapsed_seconds
        lifecycle = self.lifecycle.evaluate() if executable_exits else {
            "updated": 0, "watched": [], "disabled": [],
            "prospective_pass": [], "live_eligible": [],
        }
        target = (
            self._capacity_recommendation.target
            if self._capacity_recommendation is not None
            else self.population.max_shadow_modules
        )
        refilled = [item.module_id for item in self.population.refill(target=target)]
        self._write_health({
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "status": "RUNNING", "paper_only": True,
            "broker_execution_enabled": False,
            "execution_model": "BIDASK_EXEC_V1",
            "pricing": "LONG ask->bid; SHORT bid->ask",
            "completed_minutes": result.completed_minutes,
            "signals": result.signals,
            "executable_entries": result.executable_entries,
            "executable_exits": result.executable_exits,
            "rejected_entries": result.rejected_entries,
            "active_observations": self.prospective.active_count,
            "backlog_minutes": result.backlog_minutes,
            "adaptive_capacity": (
                self._capacity_recommendation.__dict__
                if self._capacity_recommendation is not None else None
            ),
            "metrics_updated": lifecycle["updated"],
            "modules_disabled": lifecycle["disabled"],
            "modules_watched": lifecycle["watched"],
            "modules_prospective_pass": lifecycle["prospective_pass"],
            "modules_live_eligible": lifecycle["live_eligible"],
            "modules_refilled": refilled,
        })
        return result


def _positive_int(
    name: str,
    default: int,
) -> int:
    value = int(
        os.environ.get(name, str(default))
    )

    if value < 1:
        raise ValueError(
            f"{name} must be positive"
        )

    return value


def _positive_float(
    name: str,
    default: float,
) -> float:
    value = float(
        os.environ.get(name, str(default))
    )

    if value <= 0:
        raise ValueError(
            f"{name} must be positive"
        )

    return value


def build_worker_from_environment(
    *,
    data_root: Path = Path("/data"),
    tape: Path | None = None,
    start_at_end: bool = True,
) -> FactoryShadowWorker:
    factory_root = (
        data_root / "module_factory"
    )

    return FactoryShadowWorker(
        tape_path=(
            tape
            if tape is not None
            else today_tape(data_root)
        ),
        registry_path=(
            factory_root / "module_registry.json"
        ),
        spec_path=(
            factory_root / "generated_strategies.json"
        ),
        state_path=(
            factory_root / "shadow_runtime_state.json"
        ),
        signal_path=(
            factory_root / "shadow_signals.jsonl"
        ),
        worker_state_path=(
            factory_root / "worker_state.json"
        ),
        max_shadow_modules=_positive_int(
            "FACTORY_MAX_SHADOW_MODULES",
            DEFAULT_MAX_SHADOW_MODULES,
        ),
        max_signals_per_cycle=_positive_int(
            "FACTORY_MAX_SIGNALS_PER_CYCLE",
            DEFAULT_MAX_SIGNALS_PER_CYCLE,
        ),
        max_minutes_per_cycle=_positive_int(
            "FACTORY_MAX_MINUTES_PER_CYCLE",
            DEFAULT_MAX_MINUTES_PER_CYCLE,
        ),
        history_minutes=_positive_int(
            "FACTORY_HISTORY_MINUTES",
            75,
        ),
        start_at_end=start_at_end,
        executable_quote_root=data_root / "research_market",
        health_path=factory_root / "health.json",
        healthy_checks_to_resume=_positive_int(
            "FACTORY_HEALTHY_CHECKS_TO_RESUME", 3,
        ),
        min_prune_sessions=_positive_int("FACTORY_MIN_PRUNE_SESSIONS", 10),
        min_prune_events=_positive_int("FACTORY_MIN_PRUNE_EVENTS", 100),
        resource_governor=ResourceGovernor(
            min_memory_available_mb=float(
                os.environ.get(
                    "FACTORY_MIN_MEMORY_AVAILABLE_MB",
                    "1024",
                )
            ),
            min_data_free_mb=float(
                os.environ.get(
                    "FACTORY_MIN_DATA_FREE_MB",
                    "1024",
                )
            ),
            max_load_per_cpu=float(
                os.environ.get(
                    "FACTORY_MAX_LOAD_PER_CPU",
                    "1.25",
                )
            ),
        ),
        resource_data_root=data_root,
    )


def run_forever(
    worker: FactoryShadowWorker,
    *,
    poll_seconds: float = DEFAULT_POLL_SECONDS,
    stop: Callable[[], bool] | None = None,
):
    try:
        while True:
            if stop is not None and stop():
                return

            result = worker.cycle()

            if not result.resource_allowed:
                print(
                    "FACTORY_SHADOW_YIELD "
                    + json.dumps(
                        {
                            "reasons":
                                result.resource_reasons,
                            "elapsed_seconds":
                                round(
                                    result.elapsed_seconds,
                                    6,
                                ),
                        },
                        sort_keys=True,
                    ),
                    flush=True,
                )

            elif (
                result.completed_minutes
                or result.signals
            ):
                print(
                    "FACTORY_SHADOW_CYCLE "
                    + json.dumps(
                        {
                            "completed_minutes":
                                result.completed_minutes,
                            "feature_rows":
                                result.feature_rows,
                            "signals":
                                result.signals,
                            "elapsed_seconds":
                                round(
                                    result.elapsed_seconds,
                                    6,
                                ),
                        },
                        sort_keys=True,
                    ),
                    flush=True,
                )

            time.sleep(poll_seconds)
    finally:
        worker.close()


def main():
    poll_seconds = _positive_float(
        "FACTORY_POLL_SECONDS",
        DEFAULT_POLL_SECONDS,
    )

    worker = build_worker_from_environment()

    print(
        "FACTORY_SHADOW_WORKER_STARTED "
        + json.dumps(
            {
                "paper_only": True,
                "live_order_placement": False,
                "tape": str(
                    worker.feed.tape_path
                ),
                "max_minutes_per_cycle":
                    worker.max_minutes_per_cycle,
            },
            sort_keys=True,
        ),
        flush=True,
    )

    run_forever(
        worker,
        poll_seconds=poll_seconds,
    )


if __name__ == "__main__":
    main()
