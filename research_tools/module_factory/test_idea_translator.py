import unittest
from datetime import datetime, timedelta, timezone

from research_tools.module_factory.feature_matrix import (
    FeatureRow,
)
from research_tools.module_factory.idea_library import (
    IdeaSource,
    ResearchIdea,
)
from research_tools.module_factory.idea_translator import (
    resolve_features,
    translate_idea,
)
from research_tools.module_factory.research_scientist import (
    profile_dataset,
)


class IdeaTranslatorTests(unittest.TestCase):
    def _profile(self):
        base = datetime(
            2026, 1, 2, 14, 30,
            tzinfo=timezone.utc,
        )

        rows = []

        for i in range(100):
            rows.append(
                FeatureRow(
                    symbol=f"S{i % 25}",
                    minute=(
                        base
                        + timedelta(minutes=i)
                    ),
                    price=100.0,
                    features={
                        "return_5": (
                            i - 50
                        ) / 100.0,
                        "spy_relative_return_5": (
                            i - 40
                        ) / 120.0,
                        "volatility_20": (
                            0.1
                            + (i % 20)
                            / 100.0
                        ),
                        "constant": 1.0,
                    },
                    forward_returns={
                        10: 0.0,
                        20: 0.0,
                    },
                )
            )

        return profile_dataset(
            {"2026-01-02": rows}
        )

    def test_resolves_observables(self):
        idea = ResearchIdea(
            concept="relative_move",
            mechanism="Relative moves matter.",
            observables=(
                "relative_return",
            ),
            source=IdeaSource(
                source_type="academic",
            ),
        )

        features = resolve_features(
            idea,
            self._profile(),
        )

        self.assertIn(
            "spy_relative_return_5",
            features,
        )

    def test_constant_feature_is_excluded(self):
        idea = ResearchIdea(
            concept="movement",
            mechanism="Movement matters.",
            observables=("return",),
        )

        features = resolve_features(
            idea,
            self._profile(),
        )

        self.assertNotIn(
            "constant",
            features,
        )

    def test_translation_keeps_provenance(self):
        idea = ResearchIdea(
            concept="lead_lag",
            mechanism="Delayed propagation.",
            observables=("return",),
            scientist_types=(
                "time_series",
            ),
            source=IdeaSource(
                source_type="academic",
                title="Example",
            ),
        )

        translated = translate_idea(
            idea,
            self._profile(),
            horizons=(10,),
        )

        self.assertTrue(translated)

        self.assertTrue(
            all(
                item.idea_id
                == idea.idea_id
                for item in translated
            )
        )

        self.assertTrue(
            all(
                item.source_type
                == "academic"
                for item in translated
            )
        )

    def test_conditional_creates_pairs(self):
        idea = ResearchIdea(
            concept="state_dependence",
            mechanism=(
                "Relationships change "
                "by state."
            ),
            observables=(
                "return",
                "volatility",
            ),
            scientist_types=(
                "conditional",
            ),
        )

        translated = translate_idea(
            idea,
            self._profile(),
            horizons=(20,),
        )

        self.assertTrue(
            any(
                len(
                    item.question.features
                ) == 2
                for item in translated
            )
        )

    def test_translation_is_bounded(self):
        idea = ResearchIdea(
            concept="broad_search",
            mechanism="Search broadly.",
            observables=(
                "return",
                "volatility",
            ),
            scientist_types=(
                "conditional",
                "interaction",
                "time_series",
            ),
        )

        translated = translate_idea(
            idea,
            self._profile(),
            horizons=(1, 5, 10, 20),
            max_questions=7,
        )

        self.assertLessEqual(
            len(translated),
            7,
        )


if __name__ == "__main__":
    unittest.main()

class IdeaTranslatorUniquenessTests(unittest.TestCase):
    def test_exact_translations_are_unique(self):
        from datetime import datetime, timedelta, timezone

        from research_tools.module_factory.feature_matrix import FeatureRow
        from research_tools.module_factory.idea_library import ResearchIdea
        from research_tools.module_factory.idea_translator import translate_idea
        from research_tools.module_factory.research_scientist import profile_dataset

        base = datetime(
            2026, 1, 2, 14, 30,
            tzinfo=timezone.utc,
        )

        rows = []

        for i in range(100):
            rows.append(
                FeatureRow(
                    symbol=f"S{i % 25}",
                    minute=base + timedelta(minutes=i),
                    price=100.0,
                    features={
                        "return_5": (i - 50) / 100,
                        "return_20": (i - 40) / 120,
                        "volatility_20": (
                            0.1 + (i % 20) / 100
                        ),
                    },
                    forward_returns={
                        20: 0.0,
                    },
                )
            )

        profile = profile_dataset(
            {"2026-01-02": rows}
        )

        idea = ResearchIdea(
            concept="state_test",
            mechanism="Test state dependence.",
            observables=(
                "return",
                "volatility",
            ),
            targets=(
                "future_return",
                "absolute_future_return",
                "future_cross_sectional_rank",
            ),
            scientist_types=(
                "conditional",
            ),
        )

        translated = translate_idea(
            idea,
            profile,
            horizons=(20,),
            max_questions=100,
        )

        identities = [
            (
                item.question.scientist,
                item.question.question_type,
                item.question.target,
                item.question.features,
                item.question.horizon,
            )
            for item in translated
        ]

        self.assertEqual(
            len(identities),
            len(set(identities)),
        )
