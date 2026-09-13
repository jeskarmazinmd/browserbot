import unittest

from research_tools.module_factory.resource_governor import (
    ResourceGovernor,
    ResourceSnapshot,
)


class ResourceGovernorTests(unittest.TestCase):
    def governor(self):
        return ResourceGovernor(
            min_memory_available_mb=768,
            min_data_free_mb=512,
            max_load_per_cpu=1.25,
        )

    def snapshot(
        self,
        *,
        memory=1600,
        free=2000,
        load=2,
        cpus=8,
    ):
        return ResourceSnapshot(
            memory_available_mb=memory,
            memory_total_mb=4096,
            load_1m=load,
            cpu_count=cpus,
            data_free_mb=free,
        )

    def test_healthy_machine_is_allowed(self):
        decision = self.governor().decide(
            self.snapshot()
        )

        self.assertTrue(
            decision.allowed
        )
        self.assertEqual(
            decision.reasons,
            (),
        )

    def test_low_memory_blocks_factory(self):
        decision = self.governor().decide(
            self.snapshot(memory=500)
        )

        self.assertFalse(
            decision.allowed
        )
        self.assertIn(
            "memory_available_below_floor",
            decision.reasons,
        )

    def test_low_disk_blocks_factory(self):
        decision = self.governor().decide(
            self.snapshot(free=200)
        )

        self.assertFalse(
            decision.allowed
        )
        self.assertIn(
            "data_free_below_floor",
            decision.reasons,
        )

    def test_high_normalized_load_blocks_factory(self):
        decision = self.governor().decide(
            self.snapshot(
                load=11,
                cpus=8,
            )
        )

        self.assertFalse(
            decision.allowed
        )
        self.assertIn(
            "load_per_cpu_above_ceiling",
            decision.reasons,
        )

    def test_absolute_load_is_normalized_by_cpu_count(self):
        decision = self.governor().decide(
            self.snapshot(
                load=6,
                cpus=8,
            )
        )

        self.assertTrue(
            decision.allowed
        )

    def test_multiple_constraints_are_reported(self):
        decision = self.governor().decide(
            self.snapshot(
                memory=100,
                free=100,
                load=20,
                cpus=8,
            )
        )

        self.assertFalse(
            decision.allowed
        )

        self.assertEqual(
            set(decision.reasons),
            {
                "memory_available_below_floor",
                "data_free_below_floor",
                "load_per_cpu_above_ceiling",
            },
        )

    def test_invalid_configuration_rejected(self):
        with self.assertRaises(
            ValueError
        ):
            ResourceGovernor(
                max_load_per_cpu=0
            )


if __name__ == "__main__":
    unittest.main()
