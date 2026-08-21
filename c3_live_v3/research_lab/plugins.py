"""Open plugin registry for future research capabilities.

The core intentionally imposes very little structure on plugin payloads.
New feature generators, hypothesis generators, evaluators, replay engines,
diversity measures, and capacity estimators can be registered later without
changing the discovery core.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Callable


class PluginRegistry:
    def __init__(self):
        self._plugins: dict[str, dict[str, Any]] = defaultdict(dict)

    def register(self, kind: str, name: str, plugin: Any) -> Any:
        if name in self._plugins[kind]:
            raise ValueError(f"duplicate {kind} plugin: {name}")
        self._plugins[kind][name] = plugin
        return plugin

    def decorator(self, kind: str, name: str) -> Callable[[Any], Any]:
        def add(plugin: Any) -> Any:
            return self.register(kind, name, plugin)
        return add

    def get(self, kind: str, name: str) -> Any:
        return self._plugins[kind][name]

    def all(self, kind: str) -> dict[str, Any]:
        return dict(self._plugins.get(kind, {}))

    def kinds(self) -> tuple[str, ...]:
        return tuple(sorted(self._plugins))


REGISTRY = PluginRegistry()
