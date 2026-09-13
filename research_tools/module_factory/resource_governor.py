"""
Fail-closed resource governor for Module Factory workers.

The Factory is optional research infrastructure. If host resources become
constrained, Factory work should yield rather than compete with production
collector/strategy processes.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os


@dataclass(frozen=True)
class ResourceSnapshot:
    memory_available_mb: float
    memory_total_mb: float
    load_1m: float
    cpu_count: int
    data_free_mb: float


@dataclass(frozen=True)
class ResourceDecision:
    allowed: bool
    reasons: tuple[str, ...]
    snapshot: ResourceSnapshot


class ResourceGovernor:
    def __init__(
        self,
        *,
        min_memory_available_mb: float = 768.0,
        min_data_free_mb: float = 512.0,
        max_load_per_cpu: float = 1.25,
    ):
        if min_memory_available_mb < 0:
            raise ValueError(
                "min_memory_available_mb cannot be negative"
            )

        if min_data_free_mb < 0:
            raise ValueError(
                "min_data_free_mb cannot be negative"
            )

        if max_load_per_cpu <= 0:
            raise ValueError(
                "max_load_per_cpu must be positive"
            )

        self.min_memory_available_mb = float(
            min_memory_available_mb
        )
        self.min_data_free_mb = float(
            min_data_free_mb
        )
        self.max_load_per_cpu = float(
            max_load_per_cpu
        )

    @staticmethod
    def _memory() -> tuple[float, float]:
        values = {}

        for line in Path(
            "/proc/meminfo"
        ).read_text().splitlines():
            if ":" not in line:
                continue

            name, rest = line.split(
                ":",
                1,
            )

            if name not in {
                "MemAvailable",
                "MemTotal",
            }:
                continue

            amount_kb = float(
                rest.strip().split()[0]
            )

            values[name] = (
                amount_kb / 1024.0
            )

        if (
            "MemAvailable" not in values
            or "MemTotal" not in values
        ):
            raise RuntimeError(
                "unable to read memory availability"
            )

        return (
            values["MemAvailable"],
            values["MemTotal"],
        )

    @staticmethod
    def _load() -> float:
        return float(
            Path("/proc/loadavg")
            .read_text()
            .split()[0]
        )

    @staticmethod
    def _data_free_mb(
        data_root: Path,
    ) -> float:
        stat = os.statvfs(data_root)

        return (
            stat.f_bavail
            * stat.f_frsize
            / 1024.0
            / 1024.0
        )

    def snapshot(
        self,
        *,
        data_root: Path = Path("/data"),
    ) -> ResourceSnapshot:
        available, total = self._memory()

        cpu_count = max(
            1,
            os.cpu_count() or 1,
        )

        return ResourceSnapshot(
            memory_available_mb=available,
            memory_total_mb=total,
            load_1m=self._load(),
            cpu_count=cpu_count,
            data_free_mb=self._data_free_mb(
                data_root
            ),
        )

    def decide(
        self,
        snapshot: ResourceSnapshot,
    ) -> ResourceDecision:
        reasons = []

        if (
            snapshot.memory_available_mb
            < self.min_memory_available_mb
        ):
            reasons.append(
                "memory_available_below_floor"
            )

        if (
            snapshot.data_free_mb
            < self.min_data_free_mb
        ):
            reasons.append(
                "data_free_below_floor"
            )

        load_per_cpu = (
            snapshot.load_1m
            / max(1, snapshot.cpu_count)
        )

        if (
            load_per_cpu
            > self.max_load_per_cpu
        ):
            reasons.append(
                "load_per_cpu_above_ceiling"
            )

        return ResourceDecision(
            allowed=not reasons,
            reasons=tuple(reasons),
            snapshot=snapshot,
        )

    def check(
        self,
        *,
        data_root: Path = Path("/data"),
    ) -> ResourceDecision:
        try:
            snapshot = self.snapshot(
                data_root=data_root
            )
        except Exception as exc:
            # Factory is optional. If resource state
            # cannot be established, do not run it.
            return ResourceDecision(
                allowed=False,
                reasons=(
                    "resource_measurement_failed:"
                    + type(exc).__name__,
                ),
                snapshot=ResourceSnapshot(
                    memory_available_mb=0.0,
                    memory_total_mb=0.0,
                    load_1m=float("inf"),
                    cpu_count=1,
                    data_free_mb=0.0,
                ),
            )

        return self.decide(snapshot)
