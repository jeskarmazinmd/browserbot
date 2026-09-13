import csv
import gzip
from datetime import datetime, timedelta, timezone
import tempfile
from pathlib import Path
from types import SimpleNamespace
import unittest

from research_tools.module_factory.causal_compiler import compile_frozen_hypothesis
from research_tools.module_factory.executable_quote_feed import ExecutableMinuteQuoteFeed
from research_tools.module_factory.module_registry import FactoryModuleRegistry, ModuleState
from research_tools.module_factory.population_manager import FactoryPopulationManager
from research_tools.module_factory.prospective_tracker import FactoryProspectiveTracker
from research_tools.module_factory.shadow_lifecycle import FactoryShadowLifecycle
from research_tools.module_factory.shadow_runtime import FactoryShadowRuntime


class AutonomousFactoryE2ETests(unittest.TestCase):
    def test_compile_track_decide_disable_and_refill(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            registry_path, spec_path = root / "registry.json", root / "specs.json"
            manager = FactoryPopulationManager(
                registry_path=registry_path, spec_path=spec_path, max_shadow_modules=1
            )

            def frozen(name, direction=1):
                return SimpleNamespace(
                    hypothesis_id=f"hypothesis:{name}", specification_hash=f"hash-{name}",
                    specification=SimpleNamespace(
                        scientist="causal", features=("edge",), horizon=1,
                        direction=direction, parameters={"generated_rules": [{
                            "label": "MAIN", "direction": direction, "threshold": 0.5
                        }]},
                    ),
                )

            first = compile_frozen_hypothesis(frozen("first"))[0]
            second = compile_frozen_hypothesis(frozen("second"))[0]
            manager.register_historical_pass(spec=first, score=2.0)
            manager.register_historical_pass(spec=second, score=1.0)
            manager.refill()

            journal = root / "signals.jsonl"
            runtime = FactoryShadowRuntime(
                registry_path=registry_path, spec_path=spec_path,
                state_path=root / "runtime.json", signal_path=journal,
                max_shadow_modules=1,
            )
            start = datetime(2026, 9, 3, 14, 0, tzinfo=timezone.utc)
            emitted = runtime.evaluate([{
                "symbol": "AAA", "timestamp": start, "features": {"edge": 1.0}
            }])
            self.assertEqual(len(emitted), 1)

            archive = root / "quotes"
            archive.mkdir()
            fields = ["market_minute_utc", "observed_at_utc", "symbol", "bid", "ask", "quote_time_ms"]
            with gzip.open(archive / "minute_market_quotes_20260903.csv.gz", "wt", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=fields)
                writer.writeheader()
                for minute, bid, ask in ((start, 99.0, 100.0), (start + timedelta(minutes=1), 98.0, 99.0)):
                    observed = minute + timedelta(seconds=59)
                    writer.writerow({
                        "market_minute_utc": minute.isoformat(),
                        "observed_at_utc": observed.isoformat(), "symbol": "AAA",
                        "bid": bid, "ask": ask,
                        "quote_time_ms": int(observed.timestamp() * 1000),
                    })
            feed = ExecutableMinuteQuoteFeed(archive)
            tracker = FactoryProspectiveTracker(
                state_path=root / "active.json", outcomes_path=root / "outcomes.jsonl"
            )
            self.assertEqual(tracker.reconcile_signal_journal(journal, feed)["enrolled"], 1)
            quotes = feed.quotes_for_minute(start + timedelta(minutes=1))
            self.assertEqual(len(tracker.consume_executable_minute(start + timedelta(minutes=1), quotes)), 1)

            decision = FactoryShadowLifecycle(
                registry_path=registry_path, outcomes_path=root / "outcomes.jsonl",
                max_shadow_modules=1, min_sessions=1, min_events=1,
            ).evaluate()
            self.assertEqual(decision["disabled"], [first.module_id])
            self.assertEqual([item.module_id for item in manager.refill()], [second.module_id])
            registry = FactoryModuleRegistry(registry_path, max_shadow_modules=1)
            self.assertEqual(registry.get(first.module_id).state, ModuleState.DISABLED)
            self.assertEqual(registry.get(second.module_id).state, ModuleState.SHADOW)


if __name__ == "__main__":
    unittest.main()
