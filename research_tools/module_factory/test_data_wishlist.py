import tempfile
import unittest
from pathlib import Path

from research_tools.module_factory.data_capabilities import (
    assess_idea,
    current_factory_capabilities,
)
from research_tools.module_factory.data_wishlist import (
    DataWishlist,
    entries_for_idea,
)
from research_tools.module_factory.idea_library import (
    IdeaSource,
    ResearchIdea,
)


class DataWishlistTests(unittest.TestCase):
    def _idea(
        self,
        concept,
        observables,
        *,
        novelty=0.5,
    ):
        return ResearchIdea(
            concept=concept,
            mechanism="Research mechanism.",
            observables=observables,
            source=IdeaSource(
                source_type="academic",
                title="Source",
            ),
            novelty=novelty,
        )

    def test_full_idea_creates_no_wishlist(self):
        idea = self._idea(
            "price",
            ("return",),
        )

        assessment = assess_idea(
            idea,
            current_factory_capabilities(),
        )

        self.assertEqual(
            entries_for_idea(
                idea,
                assessment,
            ),
            [],
        )

    def test_missing_volume_creates_entry(self):
        idea = self._idea(
            "price_volume",
            (
                "return",
                "volume",
            ),
        )

        assessment = assess_idea(
            idea,
            current_factory_capabilities(),
        )

        entries = entries_for_idea(
            idea,
            assessment,
        )

        self.assertTrue(
            any(
                entry.capability
                == "volume"
                for entry in entries
            )
        )

    def test_rank_aggregates_demand(self):
        wishlist = DataWishlist()

        for concept in (
            "volume_a",
            "volume_b",
            "volume_c",
        ):
            idea = self._idea(
                concept,
                ("volume",),
            )

            assessment = assess_idea(
                idea,
                current_factory_capabilities(),
            )

            wishlist.add_many(
                entries_for_idea(
                    idea,
                    assessment,
                )
            )

        ranked = (
            wishlist.rank_capabilities()
        )

        self.assertEqual(
            ranked[0].capability,
            "volume",
        )

        self.assertEqual(
            ranked[0].ideas,
            3,
        )

    def test_persistence_and_reload(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = (
                Path(tmp)
                / "wishlist.jsonl"
            )

            wishlist = DataWishlist(path)

            idea = self._idea(
                "options_state",
                (
                    "return",
                    "options_iv",
                ),
            )

            assessment = assess_idea(
                idea,
                current_factory_capabilities(),
            )

            wishlist.add_many(
                entries_for_idea(
                    idea,
                    assessment,
                )
            )

            reloaded = DataWishlist(path)

            self.assertEqual(
                len(reloaded),
                len(wishlist),
            )

            self.assertEqual(
                reloaded.rank_capabilities()[
                    0
                ].capability,
                "options",
            )

    def test_novel_idea_has_more_importance(self):
        low = self._idea(
            "low",
            ("volume",),
            novelty=0.1,
        )

        high = self._idea(
            "high",
            ("volume",),
            novelty=0.9,
        )

        caps = (
            current_factory_capabilities()
        )

        low_entry = entries_for_idea(
            low,
            assess_idea(low, caps),
        )[0]

        high_entry = entries_for_idea(
            high,
            assess_idea(high, caps),
        )[0]

        self.assertGreater(
            high_entry.importance,
            low_entry.importance,
        )


if __name__ == "__main__":
    unittest.main()
