import json
import unittest
from pathlib import Path
from unittest.mock import patch

from research_tools.module_factory.real_validation_batch_runner import (
    reconstruct_frozen,
)
from research_tools.module_factory.frozen_validation_dispatch import (
    validate_frozen_specification,
)


MANIFEST = Path(
    "research_data/"
    "factory_validation_batch_001_corrected.json"
)


class FrozenValidationDispatchTests(
    unittest.TestCase
):

    @classmethod
    def setUpClass(cls):
        payload = json.loads(
            MANIFEST.read_text()
        )

        cls.frozen = {
            item["specification"]["scientist"]:
                reconstruct_frozen(item)
            for item in payload["hypotheses"]
        }

    def test_regime_exact_parameters(self):
        with patch(
            "research_tools.module_factory."
            "frozen_validation_dispatch."
            "validate_fixed_regime",
            return_value="ok",
        ) as call:
            result = (
                validate_frozen_specification(
                    self.frozen["regime"],
                    (),
                )
            )

        self.assertEqual(result, "ok")

        call.assert_called_once_with(
            (),
            feature="return_30",
            regime_feature="kurtosis_60",
            horizon=20,
            low_threshold=(
                0.1822926125006723
            ),
            high_threshold=(
                2.574872538199741
            ),
            direction_low=1,
            direction_high=-1,
        )

    def test_time_series_exact_parameters(self):
        with patch(
            "research_tools.module_factory."
            "frozen_validation_dispatch."
            "validate_fixed_lag",
            return_value="ok",
        ) as call:
            result = (
                validate_frozen_specification(
                    self.frozen["time_series"],
                    (),
                )
            )

        self.assertEqual(result, "ok")

        call.assert_called_once_with(
            (),
            feature="return_60",
            horizon=20,
            lag=3,
            direction=1,
        )

    def test_distribution_exact_parameters(self):
        with patch(
            "research_tools.module_factory."
            "frozen_validation_dispatch."
            "validate_fixed_distribution_mean",
            return_value="ok",
        ) as call:
            result = (
                validate_frozen_specification(
                    self.frozen["distribution"],
                    (),
                )
            )

        self.assertEqual(result, "ok")

        call.assert_called_once_with(
            (),
            feature="acceleration_20",
            horizon=10,
            low_threshold=(
                -1.1736489981426645
            ),
            high_threshold=(
                0.6343565865712053
            ),
            direction_low=-1,
            direction_high=-1,
        )

    def test_residual_exact_parameters(self):
        with patch(
            "research_tools.module_factory."
            "frozen_validation_dispatch."
            "validate_fixed_residual_claim",
            return_value="ok",
        ) as call:
            result = (
                validate_frozen_specification(
                    self.frozen["residual"],
                    (),
                )
            )

        self.assertEqual(result, "ok")

        call.assert_called_once_with(
            (),
            candidate="skew_60",
            controls=(
                "kurtosis_60",
                "kurtosis_30",
                "kurtosis_20",
                "return_60",
                "kurtosis_10",
            ),
            horizon=20,
            expected_direction=-1,
        )

    def test_anomaly_exact_parameters(self):
        with patch(
            "research_tools.module_factory."
            "frozen_validation_dispatch."
            "validate_fixed_anomaly_large_move",
            return_value="ok",
        ) as call:
            result = (
                validate_frozen_specification(
                    self.frozen["anomaly"],
                    (),
                )
            )

        self.assertEqual(result, "ok")

        call.assert_called_once_with(
            (),
            features=(
                "acceleration_20",
                "kurtosis_30",
            ),
            horizon=20,
            anomaly_threshold=(
                2.813088332788578
            ),
            move_threshold=(
                0.5809267081665892
            ),
            expected_direction=-1,
        )


if __name__ == "__main__":
    unittest.main()
