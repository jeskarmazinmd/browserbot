"""Load only Factory modules that are currently admitted to shadow."""

from __future__ import annotations

from pathlib import Path

from research_tools.module_factory.generated_strategy import (
    GeneratedStrategy,
    GeneratedStrategySpec,
)
from research_tools.module_factory.module_registry import (
    FactoryModuleRegistry,
    ModuleState,
)


def load_generated_specs(
    spec_path: Path,
) -> dict[str, GeneratedStrategySpec]:
    import json

    path = Path(spec_path)

    if not path.exists():
        return {}

    payload = json.loads(path.read_text())
    items = payload.get("strategies", [])

    specs: dict[str, GeneratedStrategySpec] = {}

    for item in items:
        spec = GeneratedStrategySpec(
            module_id=str(item["module_id"]),
            hypothesis_id=str(item["hypothesis_id"]),
            specification_hash=str(
                item["specification_hash"]
            ),
            scientist=str(item["scientist"]),
            feature=str(item["feature"]),
            horizon=int(item["horizon"]),
            direction=int(item["direction"]),
            threshold=(
                None
                if item.get("threshold") is None
                else float(item["threshold"])
            ),
            expression=item.get("expression"),
            predicate=item.get("predicate"),
        )

        if spec.module_id in specs:
            raise ValueError(
                f"duplicate generated strategy {spec.module_id}"
            )

        specs[spec.module_id] = spec

    return specs


def load_active_generated_strategies(
    *,
    registry_path: Path,
    spec_path: Path,
    max_shadow_modules: int,
) -> tuple[GeneratedStrategy, ...]:
    registry = FactoryModuleRegistry(
        registry_path,
        max_shadow_modules=max_shadow_modules,
    )

    specs = load_generated_specs(spec_path)

    active = registry.active_shadow_modules()

    if len(active) > max_shadow_modules:
        raise RuntimeError(
            "Factory active strategy population exceeds runtime limit"
        )

    strategies = []

    for module in active:
        if module.state not in {
            ModuleState.SHADOW,
            ModuleState.WATCH,
        }:
            continue

        spec = specs.get(module.module_id)

        if spec is None:
            raise RuntimeError(
                f"missing generated spec for {module.module_id}"
            )

        if (
            spec.hypothesis_id != module.hypothesis_id
            or spec.specification_hash
            != module.specification_hash
        ):
            raise RuntimeError(
                f"identity mismatch for {module.module_id}"
            )

        strategy = GeneratedStrategy(spec)

        if strategy.PAPER_ONLY is not True:
            raise RuntimeError(
                f"{module.module_id} is not paper-only"
            )

        if strategy.LIVE_ORDER_PLACEMENT is not False:
            raise RuntimeError(
                f"{module.module_id} can place live orders"
            )

        strategies.append(strategy)

    return tuple(strategies)
