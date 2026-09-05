from pathlib import Path
import unittest

from strategies.derived_runtime import derive_signals
from strategies.pruning import (
    DEPENDENCY_PROTECTED_STRATEGY_IDS,
    PRUNED_OUTPUT_STRATEGY_IDS,
    active_output_ids,
)
from strategies.registry import FLASH_STRATEGY_MODULES, ENABLED_STRATEGIES


def strategy_id(strategy):
    return str(
        getattr(
            strategy,
            "name",
            getattr(strategy, "STRATEGY_ID", type(strategy).__name__),
        )
    )


def parent(strategy_id):
    return {
        "strategy_id": strategy_id,
        "symbol": "XYZ",
        "timestamp": "2026-09-08T14:00:00+00:00",
        "setup_id": f"{strategy_id}|XYZ|2026-09-08T14:00:00+00:00",
        "entry_price": 100.0,
        "target_price": 106.0,
        "stop_price": 95.0,
        "volume_data_status_flash": "OK",
        "flash_volume_ratio": 1.0,
        "rebound_volume_ratio": 0.5,
        "market_5m_return_pct": 0.1,
        "market_1m_return_pct": 0.05,
    }


class PerformancePruningDependencyTests(unittest.TestCase):
    def test_exact_reviewed_inventory_and_protected_paths(self):
        self.assertEqual(len(PRUNED_OUTPUT_STRATEGY_IDS), 64)
        self.assertFalse(
            PRUNED_OUTPUT_STRATEGY_IDS & DEPENDENCY_PROTECTED_STRATEGY_IDS
        )
        self.assertTrue({
            "A", "B", "D", "M2", "C3N25S10", "C3N25S10DUP",
            "C3N25S10NH015", "C3N25S10NH015DUP",
        }.issubset(DEPENDENCY_PROTECTED_STRATEGY_IDS))
        self.assertIn("H", PRUNED_OUTPUT_STRATEGY_IDS)

    def test_main_registries_emit_no_pruned_outputs(self):
        registered = set(FLASH_STRATEGY_MODULES)
        registered.update(strategy_id(row) for row in ENABLED_STRATEGIES)
        self.assertFalse(registered & PRUNED_OUTPUT_STRATEGY_IDS)

        # Verify the generic family is centrally filtered without importing its
        # NumPy-backed detectors; this test remains runnable in the lean local
        # test environment used for patch validation.
        generic_source = Path("strategies/generic_registry.py").read_text()
        self.assertIn("if not output_is_pruned(module.STRATEGY_ID)", generic_source)

    def test_derived_parents_keep_survivors_without_pruned_leaves(self):
        emitted = {
            signal["strategy_id"]
            for source in ("A", "B", "D")
            for signal in derive_signals(parent(source))
        }
        self.assertFalse(emitted & PRUNED_OUTPUT_STRATEGY_IDS)
        self.assertTrue({"R", "S", "C1", "C2", "C3", "C4", "G", "J1", "J2", "J6"}.issubset(emitted))

    def test_worker_filter_preserves_order_and_nonfailed_siblings(self):
        self.assertEqual(
            active_output_ids(("FUTMES1", "FUTMESR1", "FUTMGCR1")),
            ("FUTMESR1",),
        )
        self.assertEqual(
            active_output_ids(("STBETA1", "STSECTOR1", "STHEDGE2")),
            ("STSECTOR1", "STHEDGE2"),
        )

    def test_live_and_observer_sources_are_not_modified_by_pruning(self):
        runner = Path("live_strategy_runner.py").read_text()
        observer = Path("nh015_execution_observer.py").read_text()
        self.assertIn('LIVE_NH015_STRATEGY_ID', runner)
        self.assertIn('trader.place_ioc_limit_buy_order(', runner)
        self.assertNotIn('STRATEGY_H', runner)
        self.assertIn('STRATEGY_ID = "C3N25S10NH015"', observer)
        self.assertNotIn("strategies.pruning", observer)


if __name__ == "__main__":
    unittest.main()
