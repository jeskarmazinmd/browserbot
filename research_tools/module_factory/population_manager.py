"""Atomic-ish population management for autonomous Factory strategies.

This is the write-side counterpart to generated_loader.

The Factory uses this manager to:
- persist executable generated strategy specifications
- register immutable module identities
- admit historically-approved modules to SHADOW
- move modules to WATCH
- disable/prune modules

Important ordering rule:
The executable specification is durably installed BEFORE registry state can
make a module active.  Therefore the running shadow worker cannot observe an
active module whose specification has not yet been written.

Factory modules remain paper/shadow only.
"""

from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path
from typing import Any, Mapping

from research_tools.module_factory.generated_strategy import (
    GeneratedStrategySpec,
)
from research_tools.module_factory.module_registry import (
    FactoryModule,
    FactoryModuleRegistry,
    ModuleState,
)


class FactoryPopulationManager:
    def __init__(
        self,
        *,
        registry_path: Path,
        spec_path: Path,
        max_shadow_modules: int,
    ):
        self.registry_path = Path(registry_path)
        self.spec_path = Path(spec_path)
        self.max_shadow_modules = int(max_shadow_modules)

    def _registry(self) -> FactoryModuleRegistry:
        return FactoryModuleRegistry(
            self.registry_path,
            max_shadow_modules=self.max_shadow_modules,
        )

    def _load_spec_payload(self) -> dict[str, Any]:
        if not self.spec_path.exists():
            return {
                "version": 2,
                "strategies": [],
            }

        payload = json.loads(self.spec_path.read_text())
        strategies = payload.get("strategies", [])
        if not isinstance(strategies, list):
            raise RuntimeError(
                "invalid generated strategy specification file"
            )

        return {
            "version": max(
                2,
                int(payload.get("version", 1)),
            ),
            "strategies": strategies,
        }

    def _save_spec_payload(
        self,
        payload: Mapping[str, Any],
    ) -> None:
        self.spec_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )
        temporary = self.spec_path.with_suffix(
            self.spec_path.suffix + ".tmp"
        )
        temporary.write_text(
            json.dumps(
                payload,
                indent=2,
                sort_keys=True,
            )
            + "\n"
        )
        temporary.replace(self.spec_path)

    @staticmethod
    def _spec_payload(
        spec: GeneratedStrategySpec,
    ) -> dict[str, Any]:
        return asdict(spec)

    def install_spec(
        self,
        spec: GeneratedStrategySpec,
    ) -> None:
        """Durably install an immutable executable specification."""

        payload = self._load_spec_payload()
        strategies = list(payload["strategies"])

        for existing in strategies:
            if existing.get("module_id") != spec.module_id:
                continue

            identity = (
                str(existing.get("hypothesis_id")),
                str(existing.get("specification_hash")),
            )
            requested = (
                spec.hypothesis_id,
                spec.specification_hash,
            )

            if identity != requested:
                raise ValueError(
                    "generated module_id already belongs "
                    "to another hypothesis"
                )

            # Same immutable identity: idempotent only when
            # executable specification is exactly identical.
            if existing != self._spec_payload(spec):
                raise ValueError(
                    "generated strategy specification "
                    "cannot mutate in place"
                )
            return

        strategies.append(self._spec_payload(spec))
        strategies.sort(
            key=lambda item: str(item["module_id"])
        )

        self._save_spec_payload({
            "version": 2,
            "strategies": strategies,
        })

    def register_historical_pass(
        self,
        *,
        spec: GeneratedStrategySpec,
        score: float,
    ) -> FactoryModule:
        """Install executable spec and register a historical survivor."""

        # Critical ordering:
        # spec first, inactive registry identity second.
        self.install_spec(spec)

        registry = self._registry()
        module = registry.register_candidate(
            module_id=spec.module_id,
            hypothesis_id=spec.hypothesis_id,
            specification_hash=spec.specification_hash,
            scientist=spec.scientist,
            score=float(score),
        )

        if module.state is ModuleState.CANDIDATE:
            module = registry.transition(
                module.module_id,
                ModuleState.HISTORICAL_PASS,
            )

        return module

    def admit_best(
        self,
        module_ids,
    ) -> tuple[FactoryModule, ...]:
        """Fill available shadow slots with highest-scoring survivors."""

        registry = self._registry()
        return registry.admit_best_to_shadow(module_ids)

    def watch(
        self,
        module_id: str,
    ) -> FactoryModule:
        registry = self._registry()
        return registry.transition(
            module_id,
            ModuleState.WATCH,
        )

    def refill(self, *, target: int | None = None) -> tuple[FactoryModule, ...]:
        """Fill every currently permitted slot from the best survivors."""
        registry = self._registry()
        ceiling = self.max_shadow_modules if target is None else max(
            0, min(int(target), self.max_shadow_modules)
        )
        slots = max(0, ceiling - len(registry.active_shadow_modules()))
        waiting = sorted(
            (item for item in registry.modules()
             if item.state is ModuleState.HISTORICAL_PASS),
            key=lambda item: (item.score, item.module_id), reverse=True,
        )
        return registry.admit_best_to_shadow(
            item.module_id for item in waiting[:slots]
        )

    def disable(
        self,
        module_id: str,
        *,
        reason: str,
    ) -> FactoryModule:
        registry = self._registry()
        return registry.transition(
            module_id,
            ModuleState.DISABLED,
            disabled_reason=reason,
        )

    def update_metrics(
        self,
        module_id: str,
        *,
        sessions: int,
        events: int,
        paper_return_pct: float,
        max_drawdown_pct: float,
        score: float | None = None,
    ) -> FactoryModule:
        registry = self._registry()
        return registry.update_shadow_metrics(
            module_id,
            sessions=sessions,
            events=events,
            paper_return_pct=paper_return_pct,
            max_drawdown_pct=max_drawdown_pct,
            score=score,
        )

    def reconcile_resource_capacity(self, target: int) -> dict[str, list[str]]:
        """Park/restore modules without treating resource pressure as failure."""
        target = max(0, min(int(target), self.max_shadow_modules))
        registry = self._registry()
        active = sorted(
            registry.active_shadow_modules(),
            key=lambda item: (item.score, item.module_id),
        )
        parked = []
        while len(active) > target:
            module = active.pop(0)
            registry.transition(module.module_id, ModuleState.RESOURCE_PARKED)
            parked.append(module.module_id)

        available = target - len(active)
        restored = []
        if available > 0:
            waiting = sorted(
                (
                    item for item in registry.modules()
                    if item.state in {ModuleState.RESOURCE_PARKED, ModuleState.HISTORICAL_PASS}
                ),
                key=lambda item: (item.score, item.module_id),
                reverse=True,
            )
            for module in waiting[:available]:
                registry.transition(module.module_id, ModuleState.SHADOW)
                restored.append(module.module_id)
        return {"parked": parked, "restored": restored}
