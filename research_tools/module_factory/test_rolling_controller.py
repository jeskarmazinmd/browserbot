import unittest

from unittest.mock import patch

from research_tools.module_factory.rolling_controller import (
    _candidate_specs, _generated_specs, _next_delay_seconds, _research_stride,
)


class RollingControllerTests(unittest.TestCase):
    def report(self):
        return {"discovery_dataset_ids":["d1"], "literature_idea_ids":["i1"], "families": {"regime": [{
            "feature":"return_30","regime_feature":"kurtosis_60","horizon":20,
            "low_threshold":0.2,"high_threshold":2.5,"direction_low":1,"direction_high":-1,
            "sign_reversal":True,"score":8,"ancestry":["PRICE"],
        }], "distribution": []}}

    def test_freezes_provenance_and_translates_two_immutable_branches(self):
        frozen, _ = _candidate_specs(self.report())[0]
        self.assertIn("idea:i1", frozen.specification.provenance)
        generated = _generated_specs(frozen, {"primary_effect": 1})
        self.assertEqual(len(generated), 2)
        self.assertEqual({item.direction for item in generated}, {-1, 1})
        self.assertTrue(all(item.specification_hash == frozen.specification_hash for item in generated))

    def test_research_stride_has_safe_floor(self):
        with patch.dict("os.environ", {"FACTORY_RESEARCH_STRIDE": "1"}):
            self.assertEqual(_research_stride(), 1)
        with patch.dict("os.environ", {"FACTORY_RESEARCH_STRIDE": "12"}):
            self.assertEqual(_research_stride(), 1)

    def test_resource_deferral_retries_in_fifteen_minutes(self):
        self.assertEqual(
            _next_delay_seconds({"status": "DEFERRED_RESOURCES"}),
            900.0,
        )

    def test_completed_run_retains_normal_interval(self):
        self.assertEqual(
            _next_delay_seconds(
                {"status": "OK"}, normal_interval_seconds=21600,
            ),
            21600.0,
        )

    def test_errors_back_off_but_remain_bounded(self):
        delays = [
            _next_delay_seconds(
                {"status": "ERROR"}, consecutive_errors=count,
            )
            for count in (1, 2, 3, 9)
        ]
        self.assertEqual(delays, [900.0, 1800.0, 3600.0, 3600.0])

    def test_market_hours_check_is_lightweight_hourly(self):
        self.assertEqual(
            _next_delay_seconds({"status": "DEFERRED_MARKET_HOURS"}),
            3600.0,
        )
