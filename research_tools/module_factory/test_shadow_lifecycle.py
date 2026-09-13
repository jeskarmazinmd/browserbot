import json
from pathlib import Path
import tempfile
import unittest

from research_tools.module_factory.module_registry import FactoryModuleRegistry, ModuleState
from research_tools.module_factory.shadow_lifecycle import FactoryShadowLifecycle


class FactoryShadowLifecycleTests(unittest.TestCase):
    def test_prunes_only_after_both_evidence_floors(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            registry_path = root / "registry.json"
            outcomes = root / "outcomes.jsonl"
            registry = FactoryModuleRegistry(registry_path, max_shadow_modules=2)
            registry.register_candidate(module_id="FM_A", hypothesis_id="h", specification_hash="s", scientist="x")
            registry.transition("FM_A", ModuleState.HISTORICAL_PASS)
            registry.transition("FM_A", ModuleState.SHADOW)
            rows = []
            for day in range(1, 11):
                for event in range(10):
                    rows.append({"strategy_id": "FM_A", "entry_timestamp": f"2026-08-{day:02d}T14:00:00+00:00", "return_pct": -0.01})
            outcomes.write_text("".join(json.dumps(row) + "\n" for row in rows))
            result = FactoryShadowLifecycle(
                registry_path=registry_path, outcomes_path=outcomes,
                max_shadow_modules=2, min_sessions=10, min_events=100,
            ).evaluate()
            self.assertEqual(result["disabled"], ["FM_A"])
            self.assertEqual(
                FactoryModuleRegistry(registry_path, max_shadow_modules=2).get("FM_A").state,
                ModuleState.DISABLED,
            )

    def test_does_not_prune_profitable_module(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            registry_path = root / "registry.json"
            outcomes = root / "outcomes.jsonl"
            registry = FactoryModuleRegistry(registry_path, max_shadow_modules=2)
            registry.register_candidate(module_id="FM_A", hypothesis_id="h", specification_hash="s", scientist="x")
            registry.transition("FM_A", ModuleState.HISTORICAL_PASS)
            registry.transition("FM_A", ModuleState.SHADOW)
            rows = [{"strategy_id": "FM_A", "entry_timestamp": f"2026-08-{day:02d}T14:00:00+00:00", "return_pct": 0.01} for day in range(1, 11) for _ in range(10)]
            outcomes.write_text("".join(json.dumps(row) + "\n" for row in rows))
            result = FactoryShadowLifecycle(
                registry_path=registry_path, outcomes_path=outcomes,
                max_shadow_modules=2,
            ).evaluate()
            self.assertEqual(result["disabled"], [])
            self.assertEqual(result["prospective_pass"], ["FM_A"])
            self.assertEqual(
                FactoryModuleRegistry(registry_path, max_shadow_modules=2).get("FM_A").state,
                ModuleState.PROSPECTIVE_PASS,
            )
