import tempfile
import unittest
from pathlib import Path

from research_tools.module_factory.idea_library import (
    IdeaLibrary,
    IdeaSource,
    ResearchIdea,
    seed_core_ideas,
)


class IdeaLibraryTests(unittest.TestCase):
    def _idea(self, source=None):
        return ResearchIdea(
            concept="lead_lag",
            mechanism=(
                "Information may propagate "
                "with delay."
            ),
            observables=(
                "return",
                "relative_return",
            ),
            transformations=(
                "lag",
                "difference",
            ),
            scientist_types=(
                "time_series",
                "cross_sectional",
            ),
            source=(
                source
                or IdeaSource(
                    source_type="academic",
                    title="Example paper",
                )
            ),
        )

    def test_id_is_deterministic(self):
        self.assertEqual(
            self._idea().idea_id,
            self._idea().idea_id,
        )

    def test_source_does_not_change_concept_id(self):
        a = self._idea(
            IdeaSource(
                source_type="academic",
                title="Paper A",
            )
        )

        b = self._idea(
            IdeaSource(
                source_type="practitioner",
                title="Blog B",
            )
        )

        self.assertEqual(
            a.idea_id,
            b.idea_id,
        )

    def test_multiple_sources_are_retained(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ideas.jsonl"

            library = IdeaLibrary(path)

            library.add(
                self._idea(
                    IdeaSource(
                        source_type="academic",
                        title="Paper A",
                    )
                )
            )

            library.add(
                self._idea(
                    IdeaSource(
                        source_type="practitioner",
                        title="Blog B",
                    )
                )
            )

            self.assertEqual(
                len(library),
                1,
            )

            idea_id = (
                library.current()[0].idea_id
            )

            self.assertEqual(
                len(
                    library.sources(
                        idea_id
                    )
                ),
                2,
            )

            reloaded = IdeaLibrary(path)

            self.assertEqual(
                len(reloaded),
                1,
            )

            self.assertEqual(
                len(
                    reloaded.sources(
                        idea_id
                    )
                ),
                2,
            )

    def test_seed_library_is_direction_agnostic(self):
        ideas = seed_core_ideas()

        self.assertGreaterEqual(
            len(ideas),
            8,
        )

        self.assertTrue(
            all(
                idea.assumed_direction
                == "unknown"
                for idea in ideas
            )
        )

    def test_invalid_source_rejected(self):
        with self.assertRaises(ValueError):
            IdeaSource(
                source_type="magic",
            )


if __name__ == "__main__":
    unittest.main()
