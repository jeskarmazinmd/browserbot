import json
from pathlib import Path
import tempfile
import unittest

from research_tools.module_factory.generated_loader import (
    load_active_generated_strategies,
)
from research_tools.module_factory.module_registry import (
    FactoryModuleRegistry,
    ModuleState,
)


class GeneratedLoaderTests(unittest.TestCase):
    def write_specs(self, path, specs):
        Path(path).write_text(
            json.dumps({
                "version": 1,
                "strategies": specs,
            })
        )

    def candidate(
        self,
        registry,
        module_id,
        hypothesis_id,
        specification_hash,
    ):
        registry.register_candidate(
            module_id=module_id,
            hypothesis_id=hypothesis_id,
            specification_hash=specification_hash,
            scientist="regime",
            score=1.0,
        )

    def test_only_shadow_modules_load(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            registry_path = root / "registry.json"
            spec_path = root / "specs.json"

            registry = FactoryModuleRegistry(
                registry_path,
                max_shadow_modules=2,
            )

            self.candidate(
                registry,
                "FM_A",
                "hypothesis:A",
                "hash-A",
            )
            self.candidate(
                registry,
                "FM_B",
                "hypothesis:B",
                "hash-B",
            )

            registry.transition(
                "FM_A",
                ModuleState.HISTORICAL_PASS,
            )
            registry.transition(
                "FM_A",
                ModuleState.SHADOW,
            )

            self.write_specs(
                spec_path,
                [
                    {
                        "module_id": "FM_A",
                        "hypothesis_id": "hypothesis:A",
                        "specification_hash": "hash-A",
                        "scientist": "regime",
                        "feature": "return_30",
                        "horizon": 20,
                        "direction": 1,
                        "threshold": None,
                    },
                    {
                        "module_id": "FM_B",
                        "hypothesis_id": "hypothesis:B",
                        "specification_hash": "hash-B",
                        "scientist": "regime",
                        "feature": "return_60",
                        "horizon": 20,
                        "direction": 1,
                        "threshold": None,
                    },
                ],
            )

            loaded = load_active_generated_strategies(
                registry_path=registry_path,
                spec_path=spec_path,
                max_shadow_modules=2,
            )

            self.assertEqual(
                [strategy.name for strategy in loaded],
                ["FM_A"],
            )

    def test_identity_mismatch_fails_closed(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            registry_path = root / "registry.json"
            spec_path = root / "specs.json"

            registry = FactoryModuleRegistry(
                registry_path,
                max_shadow_modules=1,
            )

            self.candidate(
                registry,
                "FM_A",
                "hypothesis:A",
                "hash-A",
            )
            registry.transition(
                "FM_A",
                ModuleState.HISTORICAL_PASS,
            )
            registry.transition(
                "FM_A",
                ModuleState.SHADOW,
            )

            self.write_specs(
                spec_path,
                [
                    {
                        "module_id": "FM_A",
                        "hypothesis_id": "hypothesis:A",
                        "specification_hash": "WRONG",
                        "scientist": "regime",
                        "feature": "return_30",
                        "horizon": 20,
                        "direction": 1,
                        "threshold": None,
                    }
                ],
            )

            with self.assertRaises(RuntimeError):
                load_active_generated_strategies(
                    registry_path=registry_path,
                    spec_path=spec_path,
                    max_shadow_modules=1,
                )

    def test_missing_spec_fails_closed(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            registry_path = root / "registry.json"
            spec_path = root / "specs.json"

            registry = FactoryModuleRegistry(
                registry_path,
                max_shadow_modules=1,
            )

            self.candidate(
                registry,
                "FM_A",
                "hypothesis:A",
                "hash-A",
            )
            registry.transition(
                "FM_A",
                ModuleState.HISTORICAL_PASS,
            )
            registry.transition(
                "FM_A",
                ModuleState.SHADOW,
            )

            self.write_specs(
                spec_path,
                [],
            )

            with self.assertRaises(RuntimeError):
                load_active_generated_strategies(
                    registry_path=registry_path,
                    spec_path=spec_path,
                    max_shadow_modules=1,
                )


if __name__ == "__main__":
    unittest.main()
