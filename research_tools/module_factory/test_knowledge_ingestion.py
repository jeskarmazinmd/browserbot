import tempfile
import unittest
from pathlib import Path

from research_tools.module_factory.idea_library import (
    IdeaLibrary,
)
from research_tools.module_factory.knowledge_ingestion import (
    IdeaProposal,
    KnowledgeDocument,
    ingest_document,
    suggest_proposals,
)


class KnowledgeIngestionTests(unittest.TestCase):
    def test_document_id_is_deterministic(self):
        a = KnowledgeDocument(
            source_type="academic",
            title="Example Paper",
            text="Momentum research.",
            authors=("A", "B"),
            year=2024,
            locator="doi:test",
        )

        b = KnowledgeDocument(
            source_type="academic",
            title="Example Paper",
            text="Different local copy.",
            authors=("A", "B"),
            year=2024,
            locator="doi:test",
        )

        self.assertEqual(
            a.document_id,
            b.document_id,
        )

    def test_lexicon_extracts_multiple_concepts(self):
        document = KnowledgeDocument(
            source_type="academic",
            title=(
                "Momentum and volatility "
                "in market microstructure"
            ),
            text=(
                "We study momentum, volatility "
                "clustering and order flow."
            ),
        )

        concepts = {
            proposal.concept
            for proposal
            in suggest_proposals(document)
        }

        self.assertIn(
            "momentum",
            concepts,
        )

        self.assertIn(
            "volatility",
            concepts,
        )

        self.assertIn(
            "liquidity_microstructure",
            concepts,
        )

    def test_ingestion_preserves_provenance(self):
        with tempfile.TemporaryDirectory() as tmp:
            library = IdeaLibrary(
                Path(tmp) / "ideas.jsonl"
            )

            document = KnowledgeDocument(
                source_type="academic",
                title="Lead Lag Paper",
                text=(
                    "We study information "
                    "diffusion and lead-lag."
                ),
                authors=("Researcher",),
                year=2025,
                locator="doi:example",
                stance="supports",
            )

            records = ingest_document(
                library,
                document,
            )

            self.assertTrue(records)

            idea = library.get(
                records[0].idea_id
            )

            self.assertIsNotNone(idea)

            sources = library.sources(
                idea.idea_id
            )

            self.assertEqual(
                sources[0].title,
                "Lead Lag Paper",
            )

            self.assertIn(
                document.document_id,
                sources[0].notes,
            )

    def test_explicit_proposal_is_supported(self):
        library = IdeaLibrary()

        document = KnowledgeDocument(
            source_type="practitioner",
            title="Unusual Observation",
            text=(
                "A practitioner describes "
                "an unusual market behavior."
            ),
        )

        proposal = IdeaProposal(
            concept="custom_mechanism",
            mechanism=(
                "Investigate a custom "
                "mechanism."
            ),
            observables=(
                "return",
                "volatility",
            ),
            transformations=(
                "ratio",
            ),
            scientist_types=(
                "interaction",
            ),
        )

        records = ingest_document(
            library,
            document,
            proposals=[proposal],
        )

        self.assertEqual(
            len(records),
            1,
        )

        idea = library.get(
            records[0].idea_id
        )

        self.assertEqual(
            idea.concept,
            "custom_mechanism",
        )

        self.assertEqual(
            idea.assumed_direction,
            "unknown",
        )

    def test_same_concept_multiple_sources_dedupes(self):
        library = IdeaLibrary()

        proposal = IdeaProposal(
            concept="shared_concept",
            mechanism=(
                "Investigate shared structure."
            ),
            observables=("return",),
            scientist_types=(
                "time_series",
            ),
        )

        first = KnowledgeDocument(
            source_type="academic",
            title="Paper",
            text="Something.",
        )

        second = KnowledgeDocument(
            source_type="practitioner",
            title="Blog",
            text="Something else.",
        )

        ingest_document(
            library,
            first,
            proposals=[proposal],
        )

        ingest_document(
            library,
            second,
            proposals=[proposal],
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

    def test_source_stance_does_not_set_direction(self):
        library = IdeaLibrary()

        document = KnowledgeDocument(
            source_type="academic",
            title="Reversal Paper",
            text=(
                "Evidence supports "
                "short-term reversal."
            ),
            stance="supports",
        )

        records = ingest_document(
            library,
            document,
        )

        self.assertTrue(records)

        for record in records:
            idea = library.get(
                record.idea_id
            )

            self.assertEqual(
                idea.assumed_direction,
                "unknown",
            )


if __name__ == "__main__":
    unittest.main()
