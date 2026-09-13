"""Conservative spare-resource capacity model for Factory shadow modules."""

from __future__ import annotations

from dataclasses import dataclass
import time

from research_tools.module_factory.resource_governor import ResourceSnapshot


@dataclass(frozen=True)
class CapacityRecommendation:
    target: int
    raw_target: int
    cpu_capacity: int
    memory_capacity: int
    storage_capacity: int
    reasons: tuple[str, ...]


class AdaptiveCapacityScaler:
    def __init__(
        self, *, hard_max: int = 100, initial_target: int = 5,
        memory_reserve_mb: float = 1024, storage_reserve_mb: float = 1024,
        estimated_memory_mb_per_module: float = 8,
        estimated_daily_storage_mb_per_module: float = 2,
        max_load_per_cpu: float = 1.25, scale_up_step: int = 5,
        healthy_checks_to_grow: int = 3, scale_up_interval_seconds: float = 900,
        max_cycle_seconds: float = 1.0, max_backlog_minutes: int = 10,
    ):
        self.hard_max = max(1, int(hard_max))
        self.target = min(self.hard_max, max(0, int(initial_target)))
        self.memory_reserve_mb = float(memory_reserve_mb)
        self.storage_reserve_mb = float(storage_reserve_mb)
        self.memory_per_module = max(0.1, float(estimated_memory_mb_per_module))
        self.storage_per_module = max(0.1, float(estimated_daily_storage_mb_per_module))
        self.max_load_per_cpu = float(max_load_per_cpu)
        self.scale_up_step = max(1, int(scale_up_step))
        self.healthy_checks_to_grow = max(1, int(healthy_checks_to_grow))
        self.scale_up_interval_seconds = max(0.0, float(scale_up_interval_seconds))
        self.max_cycle_seconds = max(0.01, float(max_cycle_seconds))
        self.max_backlog_minutes = max(1, int(max_backlog_minutes))
        self._healthy_checks = 0
        self._last_growth = 0.0

    def recommend(
        self, snapshot: ResourceSnapshot, *, cycle_seconds: float = 0.0,
        backlog_minutes: int = 0, now_monotonic: float | None = None,
    ) -> CapacityRecommendation:
        load_per_cpu = snapshot.load_1m / max(1, snapshot.cpu_count)
        cpu_fraction = max(0.0, min(1.0, 1.0 - load_per_cpu / self.max_load_per_cpu))
        cpu_capacity = int(self.hard_max * cpu_fraction)
        memory_capacity = int(max(0.0, snapshot.memory_available_mb - self.memory_reserve_mb) / self.memory_per_module)
        storage_capacity = int(max(0.0, snapshot.data_free_mb - self.storage_reserve_mb) / self.storage_per_module)
        raw = max(0, min(self.hard_max, cpu_capacity, memory_capacity, storage_capacity))
        reasons = []
        if cycle_seconds > self.max_cycle_seconds:
            raw = min(raw, max(0, self.target - self.scale_up_step))
            reasons.append("cycle_latency_above_budget")
        if backlog_minutes > self.max_backlog_minutes:
            raw = min(raw, max(0, self.target - self.scale_up_step))
            reasons.append("minute_backlog_above_budget")

        clock = time.monotonic() if now_monotonic is None else float(now_monotonic)
        if raw < self.target:
            self.target = raw
            self._healthy_checks = 0
        elif raw > self.target:
            self._healthy_checks += 1
            if (
                self._healthy_checks >= self.healthy_checks_to_grow
                and clock - self._last_growth >= self.scale_up_interval_seconds
            ):
                self.target = min(raw, self.target + self.scale_up_step)
                self._healthy_checks = 0
                self._last_growth = clock
        else:
            self._healthy_checks = min(self._healthy_checks + 1, self.healthy_checks_to_grow)
        return CapacityRecommendation(
            target=self.target, raw_target=raw, cpu_capacity=cpu_capacity,
            memory_capacity=memory_capacity, storage_capacity=storage_capacity,
            reasons=tuple(reasons),
        )
