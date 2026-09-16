import importlib
import inspect
import unittest
from datetime import datetime, timedelta, timezone

from engine.events import MarketSnapshot, Quote
from strategies.registry import (
    DERIVED_RUNTIME_STRATEGY_IDS,
    FLASH_STRATEGY_MODULES,
    MINUTE_STRATEGIES,
)


IDS = {
    "SHOCKR1", "SHOCKR2", "PREVR1", "PREVR2", "VOLR1", "VOLR2",
    "TRENDX1", "TRENDX2", "ACCEL1", "ACCEL2", "PULLCONT1", "PULLCONT2",
    "BRK20", "BRK30", "COMPX1", "COMPX2", "BREADTH1", "BREADTH2",
    "OPENMOM1", "MIDREV1", "CLOSEMOM1", "ENTROPY1",
    "PAIRMR2", "PAIRTR1", "INVPAIR1", "LEADBASK2", "PEERBASK1",
    "MKTNEUT1", "SECTORROT1", "XASSETPAIR1",
}
MULTI_IDS = {
    "PAIRMR2", "PAIRTR1", "INVPAIR1", "LEADBASK2", "PEERBASK1",
    "MKTNEUT1", "SECTORROT1", "XASSETPAIR1",
}


def module_for(strategy_id):
    return importlib.import_module(f"strategies.strategy_{strategy_id.lower()}")


class Exploration30Tests(unittest.TestCase):
    def test_exactly_thirty_new_minute_strategies_are_registered(self):
        minute = {strategy.name for strategy in MINUTE_STRATEGIES}
        self.assertEqual(len(IDS), 30)
        self.assertEqual(IDS - minute, set())
        self.assertEqual(IDS & set(FLASH_STRATEGY_MODULES), set())
        self.assertEqual(IDS & set(DERIVED_RUNTIME_STRATEGY_IDS), set())

    def test_every_module_is_forward_paper_only_and_bounded(self):
        for strategy_id in IDS:
            module = module_for(strategy_id)
            self.assertTrue(module.PAPER_ONLY, strategy_id)
            self.assertFalse(module.LIVE_ORDER_PLACEMENT, strategy_id)
            self.assertEqual(module.FORWARD_START_UTC, "2026-08-10T13:30:00+00:00")
            self.assertLessEqual(len(module.UNIVERSE), 32, strategy_id)
            self.assertLessEqual(module.MAX_HISTORY, 66, strategy_id)

    def test_no_strategy_runtime_dependencies_between_experiments(self):
        for strategy_id in IDS:
            source = inspect.getsource(module_for(strategy_id))
            strategy_imports = [
                line.strip()
                for line in source.splitlines()
                if line.strip().startswith(("from strategies", "import strategies"))
            ]
            self.assertEqual(
                strategy_imports,
                ["from strategies.event_base import EventStrategy"],
                strategy_id,
            )
            for forbidden in ("derived_runtime", "snapshot_common", "research_lab.xs"):
                self.assertNotIn(forbidden, source, strategy_id)

    def test_all_strategies_survive_a_bounded_synthetic_stream(self):
        strategies = [module_for(strategy_id).Strategy() for strategy_id in sorted(IDS)]
        universe = sorted(set().union(*(set(module_for(x).UNIVERSE) for x in IDS)))
        start = datetime(2026, 8, 10, 13, 30, tzinfo=timezone.utc)
        for minute in range(70):
            # Mildly differentiated deterministic prices exercise retained state
            # without making this test assert that any particular idea must fire.
            quotes = {
                symbol: Quote(price=50.0 + index * 0.25 + minute * (0.002 + (index % 5) * 0.001))
                for index, symbol in enumerate(universe)
            }
            snapshot = MarketSnapshot(
                timestamp=start + timedelta(minutes=minute),
                quotes=quotes,
                expected_symbol_count=len(universe),
                returned_symbol_count=len(universe),
                fetch_duration_seconds=0.01,
            )
            for strategy in strategies:
                result = strategy.on_snapshot(snapshot)
                self.assertIsInstance(result, list, strategy.name)
                for event in result:
                    self.assertEqual(event.strategy_id, strategy.name)
                    if strategy.name in MULTI_IDS:
                        self.assertEqual(event.signal_type, "MULTI_LEG")
                        self.assertGreaterEqual(len(event.data["legs"]), 2)
                    else:
                        self.assertEqual(event.signal_type, "SIGNAL")


if __name__ == "__main__":
    unittest.main()
