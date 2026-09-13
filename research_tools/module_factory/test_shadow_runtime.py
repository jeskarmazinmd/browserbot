import json
from pathlib import Path
import tempfile
import unittest

from research_tools.module_factory.module_registry import (
    FactoryModuleRegistry,
    ModuleState,
)
from research_tools.module_factory.shadow_runtime import (
    FactoryShadowRuntime,
)


class FactoryShadowRuntimeTests(unittest.TestCase):
    def setup_runtime(
        self,
        root,
        *,
        max_modules=2,
        max_signals=100,
    ):
        root = Path(root)

        registry_path = root / "registry.json"
        spec_path = root / "specs.json"
        state_path = root / "state.json"
        signal_path = root / "signals.jsonl"

        registry = FactoryModuleRegistry(
            registry_path,
            max_shadow_modules=max_modules,
        )

        return (
            registry,
            spec_path,
            FactoryShadowRuntime(
                registry_path=registry_path,
                spec_path=spec_path,
                state_path=state_path,
                signal_path=signal_path,
                max_shadow_modules=max_modules,
                max_signals_per_cycle=max_signals,
            ),
            signal_path,
        )

    def add_strategy(
        self,
        registry,
        spec_path,
        *,
        module_id="FM_A",
        feature="return_30",
        direction=1,
        threshold=1.0,
    ):
        hypothesis_id = (
            f"hypothesis:{module_id}"
        )
        specification_hash = (
            f"hash-{module_id}"
        )

        registry.register_candidate(
            module_id=module_id,
            hypothesis_id=hypothesis_id,
            specification_hash=specification_hash,
            scientist="test",
            score=1.0,
        )

        registry.transition(
            module_id,
            ModuleState.HISTORICAL_PASS,
        )
        registry.transition(
            module_id,
            ModuleState.SHADOW,
        )

        if spec_path.exists():
            payload = json.loads(
                spec_path.read_text()
            )
        else:
            payload = {
                "version": 1,
                "strategies": [],
            }

        payload["strategies"].append(
            {
                "module_id": module_id,
                "hypothesis_id": hypothesis_id,
                "specification_hash":
                    specification_hash,
                "scientist": "test",
                "feature": feature,
                "horizon": 20,
                "direction": direction,
                "threshold": threshold,
            }
        )

        spec_path.write_text(
            json.dumps(payload)
        )

    def test_shadow_signal_written(self):
        with tempfile.TemporaryDirectory() as root:
            (
                registry,
                specs,
                runtime,
                signals,
            ) = self.setup_runtime(root)

            self.add_strategy(
                registry,
                specs,
            )

            emitted = runtime.evaluate(
                [
                    {
                        "symbol": "AAPL",
                        "timestamp": "t1",
                        "features": {
                            "return_30": 2.0,
                        },
                    }
                ]
            )

            self.assertEqual(
                len(emitted),
                1,
            )

            line = json.loads(
                signals.read_text().strip()
            )

            self.assertEqual(
                line["strategy_id"],
                "FM_A",
            )
            self.assertTrue(
                line["data"]["paper_only"]
            )
            self.assertFalse(
                line["data"][
                    "live_order_placement"
                ]
            )

    def test_duplicate_signal_not_reemitted(self):
        with tempfile.TemporaryDirectory() as root:
            (
                registry,
                specs,
                runtime,
                signals,
            ) = self.setup_runtime(root)

            self.add_strategy(
                registry,
                specs,
            )

            row = {
                "symbol": "AAPL",
                "timestamp": "t1",
                "features": {
                    "return_30": 2.0,
                },
            }

            self.assertEqual(
                len(runtime.evaluate([row])),
                1,
            )
            self.assertEqual(
                len(runtime.evaluate([row])),
                0,
            )

            self.assertEqual(
                len(
                    signals.read_text()
                    .strip()
                    .splitlines()
                ),
                1,
            )

    def test_signal_cycle_has_hard_ceiling(self):
        with tempfile.TemporaryDirectory() as root:
            (
                registry,
                specs,
                runtime,
                signals,
            ) = self.setup_runtime(
                root,
                max_signals=3,
            )

            self.add_strategy(
                registry,
                specs,
            )

            rows = [
                {
                    "symbol": f"S{i}",
                    "timestamp": "t1",
                    "features": {
                        "return_30": 2.0,
                    },
                }
                for i in range(100)
            ]

            emitted = runtime.evaluate(rows)

            self.assertEqual(
                len(emitted),
                3,
            )

            self.assertEqual(
                len(
                    signals.read_text()
                    .strip()
                    .splitlines()
                ),
                3,
            )

    def test_disabled_strategy_stops_immediately(self):
        with tempfile.TemporaryDirectory() as root:
            (
                registry,
                specs,
                runtime,
                signals,
            ) = self.setup_runtime(root)

            self.add_strategy(
                registry,
                specs,
            )

            registry.transition(
                "FM_A",
                ModuleState.DISABLED,
                disabled_reason="poor evidence",
            )

            emitted = runtime.evaluate(
                [
                    {
                        "symbol": "AAPL",
                        "timestamp": "t1",
                        "features": {
                            "return_30": 2.0,
                        },
                    }
                ]
            )

            self.assertEqual(
                emitted,
                (),
            )
            self.assertFalse(
                signals.exists()
            )

    def test_state_survives_restart(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)

            (
                registry,
                specs,
                runtime,
                signals,
            ) = self.setup_runtime(root)

            self.add_strategy(
                registry,
                specs,
            )

            row = {
                "symbol": "AAPL",
                "timestamp": "t1",
                "features": {
                    "return_30": 2.0,
                },
            }

            self.assertEqual(
                len(runtime.evaluate([row])),
                1,
            )

            restarted = FactoryShadowRuntime(
                registry_path=root / "registry.json",
                spec_path=root / "specs.json",
                state_path=root / "state.json",
                signal_path=root / "signals.jsonl",
                max_shadow_modules=2,
            )

            self.assertEqual(
                len(restarted.evaluate([row])),
                0,
            )


if __name__ == "__main__":
    unittest.main()
