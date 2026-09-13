"""Persistent bounded registry for autonomous Factory modules.

The registry is deliberately separate from the production strategy registry.
Factory-generated strategies begin life as paper/shadow-only experiments.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import Enum
import json
from pathlib import Path
from typing import Iterable


DEFAULT_MAX_SHADOW_MODULES = 24


class ModuleState(str, Enum):
    CANDIDATE = "CANDIDATE"
    HISTORICAL_PASS = "HISTORICAL_PASS"
    SHADOW = "SHADOW"
    WATCH = "WATCH"
    DISABLED = "DISABLED"
    PROSPECTIVE_PASS = "PROSPECTIVE_PASS"
    LIVE_ELIGIBLE = "LIVE_ELIGIBLE"
    RESOURCE_PARKED = "RESOURCE_PARKED"


ACTIVE_SHADOW_STATES = frozenset({
    ModuleState.SHADOW,
    ModuleState.WATCH,
})


@dataclass(frozen=True)
class FactoryModule:
    module_id: str
    hypothesis_id: str
    specification_hash: str
    scientist: str
    state: ModuleState
    created_at: str
    updated_at: str
    score: float = 0.0
    shadow_sessions: int = 0
    shadow_events: int = 0
    paper_return_pct: float = 0.0
    max_drawdown_pct: float = 0.0
    disabled_reason: str | None = None

    @property
    def paper_only(self) -> bool:
        return True

    @property
    def live_order_placement(self) -> bool:
        return False


class CapacityError(RuntimeError):
    pass


class FactoryModuleRegistry:
    def __init__(
        self,
        path: Path,
        *,
        max_shadow_modules: int = DEFAULT_MAX_SHADOW_MODULES,
    ):
        if max_shadow_modules < 1:
            raise ValueError("max_shadow_modules must be positive")

        self.path = Path(path)
        self.max_shadow_modules = int(max_shadow_modules)
        self._modules: dict[str, FactoryModule] = {}
        self.load()

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def load(self) -> None:
        self._modules = {}

        if not self.path.exists():
            return

        payload = json.loads(self.path.read_text())

        stored_limit = int(
            payload.get(
                "max_shadow_modules",
                self.max_shadow_modules,
            )
        )

        # Runtime configuration may lower the persisted ceiling, but a
        # persisted file must never silently raise the runtime ceiling.
        self.max_shadow_modules = min(
            self.max_shadow_modules,
            stored_limit,
        )

        for item in payload.get("modules", []):
            item = dict(item)
            item["state"] = ModuleState(item["state"])
            module = FactoryModule(**item)

            if module.module_id in self._modules:
                raise ValueError(
                    f"duplicate module_id {module.module_id}"
                )

            self._modules[module.module_id] = module

        if len(self.active_shadow_modules()) > self.max_shadow_modules:
            raise CapacityError(
                "persisted registry exceeds shadow capacity"
            )

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)

        payload = {
            "version": 1,
            "updated_at": self._now(),
            "max_shadow_modules": self.max_shadow_modules,
            "modules": [
                {
                    **asdict(module),
                    "state": module.state.value,
                }
                for module in sorted(
                    self._modules.values(),
                    key=lambda item: item.module_id,
                )
            ],
        }

        temporary = self.path.with_suffix(
            self.path.suffix + ".tmp"
        )
        temporary.write_text(
            json.dumps(
                payload,
                indent=2,
                sort_keys=True,
            )
            + "\n"
        )
        temporary.replace(self.path)

    def modules(self) -> tuple[FactoryModule, ...]:
        return tuple(
            sorted(
                self._modules.values(),
                key=lambda item: item.module_id,
            )
        )

    def get(self, module_id: str) -> FactoryModule:
        return self._modules[module_id]

    def active_shadow_modules(
        self,
    ) -> tuple[FactoryModule, ...]:
        return tuple(
            module
            for module in self.modules()
            if module.state in ACTIVE_SHADOW_STATES
        )

    def available_shadow_slots(self) -> int:
        return max(
            0,
            self.max_shadow_modules
            - len(self.active_shadow_modules()),
        )

    def register_candidate(
        self,
        *,
        module_id: str,
        hypothesis_id: str,
        specification_hash: str,
        scientist: str,
        score: float = 0.0,
    ) -> FactoryModule:
        if module_id in self._modules:
            existing = self._modules[module_id]

            identity = (
                existing.hypothesis_id,
                existing.specification_hash,
            )
            requested = (
                hypothesis_id,
                specification_hash,
            )

            if identity != requested:
                raise ValueError(
                    "module_id already belongs to another hypothesis"
                )

            return existing

        now = self._now()

        module = FactoryModule(
            module_id=module_id,
            hypothesis_id=hypothesis_id,
            specification_hash=specification_hash,
            scientist=scientist,
            state=ModuleState.CANDIDATE,
            created_at=now,
            updated_at=now,
            score=float(score),
        )

        self._modules[module_id] = module
        self.save()
        return module

    def transition(
        self,
        module_id: str,
        state: ModuleState,
        *,
        disabled_reason: str | None = None,
    ) -> FactoryModule:
        current = self.get(module_id)

        if (
            state in ACTIVE_SHADOW_STATES
            and current.state not in ACTIVE_SHADOW_STATES
            and self.available_shadow_slots() <= 0
        ):
            raise CapacityError(
                "Factory shadow-module capacity reached"
            )

        updated = FactoryModule(
            **{
                **asdict(current),
                "state": state,
                "updated_at": self._now(),
                "disabled_reason": (
                    disabled_reason
                    if state is ModuleState.DISABLED
                    else None
                ),
            }
        )

        self._modules[module_id] = updated
        self.save()
        return updated

    def update_shadow_metrics(
        self,
        module_id: str,
        *,
        sessions: int,
        events: int,
        paper_return_pct: float,
        max_drawdown_pct: float,
        score: float | None = None,
    ) -> FactoryModule:
        current = self.get(module_id)

        updated = FactoryModule(
            **{
                **asdict(current),
                "updated_at": self._now(),
                "shadow_sessions": int(sessions),
                "shadow_events": int(events),
                "paper_return_pct": float(paper_return_pct),
                "max_drawdown_pct": float(max_drawdown_pct),
                "score": (
                    current.score
                    if score is None
                    else float(score)
                ),
            }
        )

        self._modules[module_id] = updated
        self.save()
        return updated

    def admit_best_to_shadow(
        self,
        module_ids: Iterable[str],
    ) -> tuple[FactoryModule, ...]:
        candidates = [
            self.get(module_id)
            for module_id in module_ids
        ]

        eligible = [
            module
            for module in candidates
            if module.state is ModuleState.HISTORICAL_PASS
        ]

        eligible.sort(
            key=lambda module: (
                module.score,
                module.module_id,
            ),
            reverse=True,
        )

        admitted = []

        for module in eligible:
            if self.available_shadow_slots() <= 0:
                break

            admitted.append(
                self.transition(
                    module.module_id,
                    ModuleState.SHADOW,
                )
            )

        return tuple(admitted)
