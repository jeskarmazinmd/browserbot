import json
from pathlib import Path
import tempfile
import unittest

from research_tools.module_factory.generated_loader import (
    load_active_generated_strategies,
)
from research_tools.module_factory.generated_strategy import (
    GeneratedStrategySpec,
)
from research_tools.module_factory.module_registry import (
    FactoryModuleRegistry,
    ModuleState,
)
from research_tools.module_factory.population_manager import (
    FactoryPopulationManager,
)


class FactoryPopulationManagerTests(unittest.TestCase):

    def setup(self, root, limit=2):
        root = Path(root)
        manager = FactoryPopulationManager(
            registry_path=root / "registry.json",
            spec_path=root / "specs.json",
            max_shadow_modules=limit,
        )
        return root, manager

    def spec(self, suffix, score_feature="return_30"):
        return GeneratedStrategySpec(
            module_id=f"FM_{suffix}",
            hypothesis_id=f"hypothesis:{suffix}",
            specification_hash=f"hash-{suffix}",
            scientist="factory",
            feature=score_feature,
            horizon=20,
            direction=1,
            threshold=1.0,
        )

    def test_register_pass_installs_spec_before_activation(self):
        with tempfile.TemporaryDirectory() as directory:
            root, manager = self.setup(directory)

            module = manager.register_historical_pass(
                spec=self.spec("A"),
                score=3.0,
            )

            self.assertEqual(
                module.state,
                ModuleState.HISTORICAL_PASS,
            )

            payload = json.loads(
                (root / "specs.json").read_text()
            )
            self.assertEqual(
                payload["strategies"][0]["module_id"],
                "FM_A",
            )

            # Historical pass is not active yet.
            loaded = load_active_generated_strategies(
                registry_path=root / "registry.json",
                spec_path=root / "specs.json",
                max_shadow_modules=2,
            )
            self.assertEqual(loaded, ())

    def test_resource_reconcile_parks_low_score_and_restores_best(self):
        with tempfile.TemporaryDirectory() as directory:
            root, manager = self.setup(directory, limit=3)
            for suffix, score in (("A", 1.0), ("B", 5.0), ("C", 3.0)):
                manager.register_historical_pass(spec=self.spec(suffix), score=score)
            manager.admit_best(["FM_A", "FM_B", "FM_C"])
            reduced = manager.reconcile_resource_capacity(1)
            self.assertEqual(set(reduced["parked"]), {"FM_A", "FM_C"})
            self.assertEqual(
                FactoryModuleRegistry(root / "registry.json", max_shadow_modules=3).get("FM_A").state,
                ModuleState.RESOURCE_PARKED,
            )
            expanded = manager.reconcile_resource_capacity(2)
            self.assertEqual(expanded["restored"], ["FM_C"])

    def test_admit_makes_strategy_visible_to_runtime(self):
        with tempfile.TemporaryDirectory() as directory:
            root, manager = self.setup(directory)

            manager.register_historical_pass(
                spec=self.spec("A"),
                score=3.0,
            )
            admitted = manager.admit_best(["FM_A"])

            self.assertEqual(
                [item.module_id for item in admitted],
                ["FM_A"],
            )

            loaded = load_active_generated_strategies(
                registry_path=root / "registry.json",
                spec_path=root / "specs.json",
                max_shadow_modules=2,
            )
            self.assertEqual(
                [strategy.strategy_id for strategy in loaded],
                ["FM_A"],
            )

    def test_disable_removes_strategy_without_deleting_spec(self):
        with tempfile.TemporaryDirectory() as directory:
            root, manager = self.setup(directory)

            manager.register_historical_pass(
                spec=self.spec("A"),
                score=3.0,
            )
            manager.admit_best(["FM_A"])
            manager.disable(
                "FM_A",
                reason="failed prospective evidence",
            )

            loaded = load_active_generated_strategies(
                registry_path=root / "registry.json",
                spec_path=root / "specs.json",
                max_shadow_modules=2,
            )
            self.assertEqual(loaded, ())

            payload = json.loads(
                (root / "specs.json").read_text()
            )
            self.assertEqual(
                payload["strategies"][0]["module_id"],
                "FM_A",
            )

            registry = FactoryModuleRegistry(
                root / "registry.json",
                max_shadow_modules=2,
            )
            self.assertEqual(
                registry.get("FM_A").state,
                ModuleState.DISABLED,
            )

    def test_best_candidates_fill_bounded_population(self):
        with tempfile.TemporaryDirectory() as directory:
            root, manager = self.setup(
                directory,
                limit=2,
            )

            for suffix, score in (
                ("A", 1.0),
                ("B", 5.0),
                ("C", 3.0),
            ):
                manager.register_historical_pass(
                    spec=self.spec(suffix),
                    score=score,
                )

            admitted = manager.admit_best(
                ["FM_A", "FM_B", "FM_C"]
            )

            self.assertEqual(
                [item.module_id for item in admitted],
                ["FM_B", "FM_C"],
            )

    def test_same_identity_is_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            _, manager = self.setup(directory)

            spec = self.spec("A")
            manager.register_historical_pass(
                spec=spec,
                score=3.0,
            )
            manager.register_historical_pass(
                spec=spec,
                score=3.0,
            )

    def test_spec_cannot_mutate_in_place(self):
        with tempfile.TemporaryDirectory() as directory:
            _, manager = self.setup(directory)

            manager.register_historical_pass(
                spec=self.spec("A"),
                score=3.0,
            )

            mutated = GeneratedStrategySpec(
                module_id="FM_A",
                hypothesis_id="hypothesis:A",
                specification_hash="hash-A",
                scientist="factory",
                feature="return_60",
                horizon=20,
                direction=1,
                threshold=1.0,
            )

            with self.assertRaises(ValueError):
                manager.install_spec(mutated)


if __name__ == "__main__":
    unittest.main()
