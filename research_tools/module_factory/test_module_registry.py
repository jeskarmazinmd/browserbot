import json
from pathlib import Path
import tempfile
import unittest

from research_tools.module_factory.module_registry import (
    CapacityError,
    FactoryModuleRegistry,
    ModuleState,
)


class FactoryModuleRegistryTests(unittest.TestCase):
    def make_registry(self, root, limit=2):
        return FactoryModuleRegistry(
            Path(root) / "registry.json",
            max_shadow_modules=limit,
        )

    def register(self, registry, suffix, score=1.0):
        return registry.register_candidate(
            module_id=f"FM_{suffix}",
            hypothesis_id=f"hypothesis:{suffix}",
            specification_hash=f"hash-{suffix}",
            scientist="test-scientist",
            score=score,
        )

    def test_factory_modules_are_fail_closed(self):
        with tempfile.TemporaryDirectory() as root:
            registry = self.make_registry(root)
            module = self.register(registry, "A")

            self.assertTrue(module.paper_only)
            self.assertFalse(module.live_order_placement)

    def test_capacity_is_hard_limit(self):
        with tempfile.TemporaryDirectory() as root:
            registry = self.make_registry(root, limit=2)

            scores = {
                "A": 3.0,
                "B": 2.0,
                "C": 1.0,
            }

            for suffix in ("A", "B", "C"):
                module = self.register(
                    registry,
                    suffix,
                    score=scores[suffix],
                )
                registry.transition(
                    module.module_id,
                    ModuleState.HISTORICAL_PASS,
                )

            admitted = registry.admit_best_to_shadow(
                ["FM_A", "FM_B", "FM_C"]
            )

            self.assertEqual(
                [module.module_id for module in admitted],
                ["FM_A", "FM_B"],
            )
            self.assertEqual(
                len(registry.active_shadow_modules()),
                2,
            )
            self.assertEqual(
                registry.available_shadow_slots(),
                0,
            )

            self.assertEqual(
                registry.get("FM_C").state,
                ModuleState.HISTORICAL_PASS,
            )

            with self.assertRaises(CapacityError):
                registry.transition(
                    "FM_C",
                    ModuleState.SHADOW,
                )

    def test_disable_frees_capacity(self):
        with tempfile.TemporaryDirectory() as root:
            registry = self.make_registry(root, limit=1)

            first = self.register(registry, "A")
            second = self.register(registry, "B")

            registry.transition(
                first.module_id,
                ModuleState.HISTORICAL_PASS,
            )
            registry.transition(
                second.module_id,
                ModuleState.HISTORICAL_PASS,
            )

            registry.transition(
                first.module_id,
                ModuleState.SHADOW,
            )

            registry.transition(
                first.module_id,
                ModuleState.DISABLED,
                disabled_reason="failed prospective evidence",
            )

            registry.transition(
                second.module_id,
                ModuleState.SHADOW,
            )

            self.assertEqual(
                [
                    module.module_id
                    for module in registry.active_shadow_modules()
                ],
                ["FM_B"],
            )

    def test_registry_persists(self):
        with tempfile.TemporaryDirectory() as root:
            registry = self.make_registry(root)

            module = self.register(
                registry,
                "A",
                score=3.5,
            )
            registry.transition(
                module.module_id,
                ModuleState.HISTORICAL_PASS,
            )
            registry.transition(
                module.module_id,
                ModuleState.SHADOW,
            )
            registry.update_shadow_metrics(
                module.module_id,
                sessions=7,
                events=123,
                paper_return_pct=4.25,
                max_drawdown_pct=1.1,
            )

            reloaded = self.make_registry(root)
            restored = reloaded.get(module.module_id)

            self.assertEqual(
                restored.state,
                ModuleState.SHADOW,
            )
            self.assertEqual(restored.shadow_sessions, 7)
            self.assertEqual(restored.shadow_events, 123)
            self.assertEqual(
                restored.paper_return_pct,
                4.25,
            )

    def test_persisted_limit_cannot_raise_runtime_limit(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "registry.json"

            path.write_text(
                json.dumps({
                    "version": 1,
                    "max_shadow_modules": 1000,
                    "modules": [],
                })
            )

            registry = FactoryModuleRegistry(
                path,
                max_shadow_modules=3,
            )

            self.assertEqual(
                registry.max_shadow_modules,
                3,
            )

    def test_duplicate_id_cannot_change_identity(self):
        with tempfile.TemporaryDirectory() as root:
            registry = self.make_registry(root)
            self.register(registry, "A")

            with self.assertRaises(ValueError):
                registry.register_candidate(
                    module_id="FM_A",
                    hypothesis_id="hypothesis:OTHER",
                    specification_hash="other-hash",
                    scientist="other",
                )


if __name__ == "__main__":
    unittest.main()
