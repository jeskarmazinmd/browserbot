import unittest

from research_tools.module_factory.adaptive_capacity import AdaptiveCapacityScaler
from research_tools.module_factory.resource_governor import ResourceSnapshot


class AdaptiveCapacityTests(unittest.TestCase):
    def snapshot(self, *, memory=4096, storage=4096, load=0.8):
        return ResourceSnapshot(memory_available_mb=memory, memory_total_mb=8192, load_1m=load, cpu_count=8, data_free_mb=storage)

    def test_grows_slowly_after_consecutive_healthy_checks(self):
        scaler = AdaptiveCapacityScaler(hard_max=100, initial_target=5, healthy_checks_to_grow=3, scale_up_interval_seconds=0)
        self.assertEqual(scaler.recommend(self.snapshot(), now_monotonic=1).target, 5)
        self.assertEqual(scaler.recommend(self.snapshot(), now_monotonic=2).target, 5)
        self.assertEqual(scaler.recommend(self.snapshot(), now_monotonic=3).target, 10)

    def test_contracts_immediately_when_memory_capacity_falls(self):
        scaler = AdaptiveCapacityScaler(hard_max=100, initial_target=50)
        result = scaler.recommend(self.snapshot(memory=1064), now_monotonic=1)
        self.assertEqual(result.target, 5)

    def test_latency_and_backlog_reduce_capacity(self):
        scaler = AdaptiveCapacityScaler(hard_max=100, initial_target=50)
        result = scaler.recommend(self.snapshot(), cycle_seconds=2, backlog_minutes=20, now_monotonic=1)
        self.assertEqual(result.target, 45)
        self.assertIn("cycle_latency_above_budget", result.reasons)
