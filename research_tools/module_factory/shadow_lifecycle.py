"""Evidence-gated metrics and automatic disabling for Factory shadows."""

from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path

from research_tools.module_factory.module_registry import (
    ACTIVE_SHADOW_STATES,
    FactoryModuleRegistry,
    ModuleState,
)


class FactoryShadowLifecycle:
    def __init__(
        self,
        *,
        registry_path: Path,
        outcomes_path: Path,
        max_shadow_modules: int,
        min_sessions: int = 10,
        min_events: int = 100,
        prune_mean_return_pct: float = 0.0,
        live_eligible_mean_return_pct: float = 0.02,
        live_eligible_sessions: int = 20,
        live_eligible_events: int = 250,
        live_eligible_max_drawdown_pct: float = -10.0,
        aggregate_path: Path | None = None,
    ):
        self.registry_path = Path(registry_path)
        self.outcomes_path = Path(outcomes_path)
        self.max_shadow_modules = int(max_shadow_modules)
        self.min_sessions = max(1, int(min_sessions))
        self.min_events = max(1, int(min_events))
        self.prune_mean_return_pct = float(prune_mean_return_pct)
        self.live_eligible_mean_return_pct = float(live_eligible_mean_return_pct)
        self.live_eligible_sessions = max(self.min_sessions, int(live_eligible_sessions))
        self.live_eligible_events = max(self.min_events, int(live_eligible_events))
        self.live_eligible_max_drawdown_pct = float(live_eligible_max_drawdown_pct)
        self.aggregate_path = Path(aggregate_path or self.outcomes_path.with_suffix(".aggregate.json"))

    def _aggregate(self) -> dict:
        payload = {"version": 1, "offset": 0, "modules": {}}
        if self.aggregate_path.exists():
            payload = json.loads(self.aggregate_path.read_text())
            if payload.get("version") != 1:
                raise RuntimeError("unsupported Factory lifecycle aggregate version")
        if not self.outcomes_path.exists():
            return payload
        size = self.outcomes_path.stat().st_size
        if int(payload.get("offset", 0)) > size:
            payload = {"version": 1, "offset": 0, "modules": {}}
        changed = False
        with self.outcomes_path.open("rb") as handle:
            handle.seek(int(payload.get("offset", 0)))
            while True:
                start = handle.tell()
                raw = handle.readline()
                if not raw:
                    break
                if not raw.endswith(b"\n"):
                    handle.seek(start)
                    break
                try:
                    row = json.loads(raw)
                    if row.get("execution_model", "BIDASK_EXEC_V1") != "BIDASK_EXEC_V1":
                        raise ValueError("non-executable outcome")
                    strategy_id = str(row["strategy_id"])
                    value = float(row["return_pct"])
                    session = datetime.fromisoformat(
                        str(row["entry_timestamp"]).replace("Z", "+00:00")
                    ).date().isoformat()
                    item = payload["modules"].setdefault(strategy_id, {
                        "events": 0, "return_sum": 0.0, "equity": 0.0,
                        "peak": 0.0, "max_drawdown": 0.0, "sessions": [],
                    })
                    item["events"] += 1
                    item["return_sum"] += value
                    item["equity"] += value
                    item["peak"] = max(item["peak"], item["equity"])
                    item["max_drawdown"] = min(
                        item["max_drawdown"], item["equity"] - item["peak"]
                    )
                    if session not in item["sessions"]:
                        item["sessions"].append(session)
                        item["sessions"].sort()
                except (json.JSONDecodeError, KeyError, TypeError, ValueError):
                    pass
                payload["offset"] = handle.tell()
                changed = True
        if changed:
            self.aggregate_path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.aggregate_path.with_suffix(self.aggregate_path.suffix + ".tmp")
            temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
            temporary.replace(self.aggregate_path)
        return payload

    def evaluate(self) -> dict:
        registry = FactoryModuleRegistry(
            self.registry_path,
            max_shadow_modules=self.max_shadow_modules,
        )
        grouped = self._aggregate()["modules"]

        updated = 0
        disabled = []
        watched = []
        prospective_pass = []
        live_eligible = []
        for module in registry.modules():
            metrics = grouped.get(module.module_id)
            if not metrics:
                continue
            events = int(metrics["events"])
            sessions = len(metrics["sessions"])
            total_return = float(metrics["return_sum"])
            drawdown = float(metrics["max_drawdown"])
            mean_return = total_return / events
            registry.update_shadow_metrics(
                module.module_id,
                sessions=sessions,
                events=events,
                paper_return_pct=total_return,
                max_drawdown_pct=drawdown,
                score=mean_return,
            )
            updated += 1
            current = registry.get(module.module_id)
            if (
                current.state is ModuleState.SHADOW
                and sessions >= max(1, self.min_sessions // 2)
                and events >= max(1, self.min_events // 2)
                and mean_return > self.prune_mean_return_pct
            ):
                registry.transition(module.module_id, ModuleState.WATCH)
                watched.append(module.module_id)
                current = registry.get(module.module_id)
            if (
                current.state in ACTIVE_SHADOW_STATES
                and sessions >= self.min_sessions
                and events >= self.min_events
                and mean_return <= self.prune_mean_return_pct
            ):
                registry.transition(
                    module.module_id,
                    ModuleState.DISABLED,
                    disabled_reason=(
                        f"bidask_mean_return={mean_return:.6f}% after "
                        f"{sessions} sessions/{events} outcomes"
                    ),
                )
                disabled.append(module.module_id)
            elif (
                current.state in ACTIVE_SHADOW_STATES
                and sessions >= self.live_eligible_sessions
                and events >= self.live_eligible_events
                and mean_return >= self.live_eligible_mean_return_pct
                and drawdown >= self.live_eligible_max_drawdown_pct
            ):
                # Research state only.  No production registry or live-order
                # flag is touched by this transition.
                registry.transition(module.module_id, ModuleState.LIVE_ELIGIBLE)
                live_eligible.append(module.module_id)
            elif (
                current.state in ACTIVE_SHADOW_STATES
                and sessions >= self.min_sessions
                and events >= self.min_events
                and mean_return > self.prune_mean_return_pct
            ):
                registry.transition(module.module_id, ModuleState.PROSPECTIVE_PASS)
                prospective_pass.append(module.module_id)
        return {
            "updated": updated,
            "watched": watched,
            "disabled": disabled,
            "prospective_pass": prospective_pass,
            "live_eligible": live_eligible,
        }
