"""Automatic strategy discovery and metadata manifest.

Adding a ``strategy_*.py`` module makes it discoverable. A strategy can be
removed or disabled without editing the runner or writer core files.
"""
from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
from pathlib import Path
from types import ModuleType
from typing import Any


@dataclass(frozen=True)
class StrategyRecord:
    strategy_id: str
    module_name: str
    description: str
    family: str
    paper_only: bool
    config: dict[str, Any]
    scanner: bool


def _strategy_module_names() -> list[str]:
    folder = Path(__file__).resolve().parent
    return sorted(
        f"strategies.{path.stem}"
        for path in folder.glob("strategy_*.py")
        if path.stem not in {"strategy_template"}
    )


def load_modules() -> dict[str, ModuleType]:
    modules: dict[str, ModuleType] = {}
    for module_name in _strategy_module_names():
        module = import_module(module_name)
        strategy_id = str(getattr(module, "STRATEGY_ID", "")).upper().strip()
        if not strategy_id:
            raise RuntimeError(f"{module_name} is missing STRATEGY_ID")
        if strategy_id in modules:
            raise RuntimeError(f"duplicate strategy ID: {strategy_id}")
        modules[strategy_id] = module
    return modules


def build_manifest() -> dict[str, StrategyRecord]:
    records: dict[str, StrategyRecord] = {}
    for strategy_id, module in load_modules().items():
        raw = module.metadata() if hasattr(module, "metadata") else {}
        records[strategy_id] = StrategyRecord(
            strategy_id=strategy_id,
            module_name=module.__name__,
            description=str(raw.get("description", getattr(module, "DESCRIPTION", "")) or (module.__doc__ or "").strip().splitlines()[0]),
            family=str(raw.get("family", getattr(module, "FAMILY", "independent"))),
            paper_only=bool(raw.get("paper_only", getattr(module, "PAPER_ONLY", True))),
            config=dict(raw.get("config", getattr(module, "CONFIG", {})) or {}),
            scanner=callable(getattr(module, "evaluate", None)),
        )
    return records


STRATEGY_MODULES = load_modules()
STRATEGY_MANIFEST = build_manifest()


def module_for(strategy_id: str) -> ModuleType:
    return STRATEGY_MODULES[str(strategy_id).upper()]


def config_for(strategy_id: str) -> dict[str, Any]:
    return dict(STRATEGY_MANIFEST[str(strategy_id).upper()].config)


def enabled_scanners() -> list[ModuleType]:
    return [
        STRATEGY_MODULES[strategy_id]
        for strategy_id, record in STRATEGY_MANIFEST.items()
        if record.scanner and bool(getattr(STRATEGY_MODULES[strategy_id], "ENABLED", True))
    ]
