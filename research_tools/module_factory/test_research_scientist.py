import math
import unittest
from datetime import datetime, timedelta, timezone

from research_tools.module_factory.feature_matrix import FeatureRow
from research_tools.module_factory.research_scientist import (
    build_agenda,
    formulate_questions,
    profile_dataset,
)


class ResearchScientistTests(unittest.TestCase):
    def _rows(self):
        rows = []

        for day in (2, 3):
            base = datetime(
                2026, 1, day, 14, 30,
                tzinfo=timezone.utc,
            )

            for i in range(200):
                rows.append(
                    FeatureRow(
                        symbol=f"S{i % 40}",
                        minute=(
                            base
                            + timedelta(minutes=i)
                        ),
                        price=100.0,
                        features={
                            "return_5": (
                                (i % 50) - 25
                            ) / 100.0,
                            "volatility_10": (
                                0.1
                                + (i % 20) / 100.0
                            ),
                            "range_position_20": (
                                i % 100
                            ) / 100.0,
                            "junk_constant": 1.0,
                        },
                        forward_returns={
                            10: (
                                (i % 50) - 25
                            ) / 200.0,
                            20: (
                                (i % 50) - 25
                            ) / 180.0,
                        },
                    )
                )

        return {
            "2026-01-02": rows[:200],
            "2026-01-03": rows[200:],
        }

    def test_profile_characterizes_dataset(self):
        profile = profile_dataset(
            self._rows()
        )

        self.assertEqual(
            profile.days,
            2,
        )

        self.assertEqual(
            profile.rows,
            400,
        )

        self.assertEqual(
            profile.symbols,
            40,
        )

        self.assertIn(
            "return_5",
            profile.feature_profiles,
        )

    def test_constant_feature_is_not_research_target(self):
        profile = profile_dataset(
            self._rows()
        )

        questions = formulate_questions(
            profile,
            horizons=(10,),
        )

        targeted = {
            feature
            for question in questions
            for feature in question.features
        }

        self.assertNotIn(
            "junk_constant",
            targeted,
        )

    def test_cross_sectional_scientist_appears(self):
        agenda = build_agenda(
            self._rows(),
            horizons=(10,),
        )

        self.assertTrue(
            any(
                q.scientist
                == "cross_sectional"
                for q in agenda.questions
            )
        )

    def test_conditional_scientist_appears(self):
        agenda = build_agenda(
            self._rows(),
            horizons=(10,),
        )

        self.assertTrue(
            any(
                q.scientist
                == "conditional"
                for q in agenda.questions
            )
        )

    def test_distribution_scientist_appears(self):
        agenda = build_agenda(
            self._rows(),
            horizons=(10,),
        )

        self.assertTrue(
            any(
                q.scientist
                == "distribution"
                for q in agenda.questions
            )
        )

    def test_anomaly_scientist_appears(self):
        agenda = build_agenda(
            self._rows(),
            horizons=(10,),
        )

        self.assertTrue(
            any(
                q.scientist
                == "anomaly"
                for q in agenda.questions
            )
        )

    def test_agenda_is_bounded(self):
        agenda = build_agenda(
            self._rows(),
            horizons=(1, 5, 10, 20),
            max_questions=25,
        )

        self.assertLessEqual(
            len(agenda.questions),
            25,
        )


if __name__ == "__main__":
    unittest.main()
