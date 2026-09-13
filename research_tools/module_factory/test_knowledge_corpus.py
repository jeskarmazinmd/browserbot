import tempfile
import unittest
from pathlib import Path

from research_tools.module_factory.knowledge_corpus import (
    KnowledgeCorpus,
    seed_research_documents,
)
from research_tools.module_factory.knowledge_ingestion import (
    KnowledgeDocument,
)


class KnowledgeCorpusTests(unittest.TestCase):
    def test_add_and_reload(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "corpus.jsonl"
            corpus = KnowledgeCorpus(path)

            document = KnowledgeDocument(
                source_type="academic",
                title="Example",
                text="Momentum and volatility.",
                locator="example:test",
            )

            self.assertTrue(
                corpus.add(document)
            )

            reloaded = KnowledgeCorpus(path)

            self.assertEqual(
                len(reloaded),
                1,
            )

            self.assertEqual(
                reloaded.current()[0].title,
                "Example",
            )

    def test_exact_duplicate_not_reappended(self):
        with tempfile.TemporaryDirectory() as tmp:
            corpus = KnowledgeCorpus(
                Path(tmp) / "corpus.jsonl"
            )

            document = KnowledgeDocument(
                source_type="academic",
                title="Example",
                text="Same content.",
                locator="example:test",
            )

            self.assertTrue(
                corpus.add(document)
            )

            self.assertFalse(
                corpus.add(document)
            )

            self.assertEqual(
                len(corpus),
                1,
            )

    def test_updated_content_replaces_current(self):
        with tempfile.TemporaryDirectory() as tmp:
            corpus = KnowledgeCorpus(
                Path(tmp) / "corpus.jsonl"
            )

            first = KnowledgeDocument(
                source_type="academic",
                title="Example",
                text="First version.",
                locator="example:test",
            )

            second = KnowledgeDocument(
                source_type="academic",
                title="Example",
                text="Second version.",
                locator="example:test",
            )

            self.assertEqual(
                first.document_id,
                second.document_id,
            )

            corpus.add(first)
            corpus.add(second)

            self.assertEqual(
                len(corpus),
                1,
            )

            self.assertEqual(
                corpus.current()[0].text,
                "Second version.",
            )

    def test_tag_lookup(self):
        with tempfile.TemporaryDirectory() as tmp:
            corpus = KnowledgeCorpus(
                Path(tmp) / "corpus.jsonl"
            )

            corpus.add(
                KnowledgeDocument(
                    source_type="academic",
                    title="Microstructure",
                    text="Order flow.",
                    tags=(
                        "microstructure",
                        "intraday",
                    ),
                )
            )

            self.assertEqual(
                len(
                    corpus.by_tag(
                        "microstructure"
                    )
                ),
                1,
            )

    def test_seed_documents_are_real_sources(self):
        documents = seed_research_documents()

        self.assertGreaterEqual(
            len(documents),
            10,
        )

        self.assertTrue(
            all(
                document.locator.startswith(
                    "https://"
                )
                for document in documents
            )
        )

        self.assertTrue(
            all(
                document.source_type
                == "academic"
                for document in documents
            )
        )

    def test_unseen_filter(self):
        with tempfile.TemporaryDirectory() as tmp:
            corpus = KnowledgeCorpus(
                Path(tmp) / "corpus.jsonl"
            )

            documents = (
                seed_research_documents()[:2]
            )

            corpus.add_many(documents)

            unseen = corpus.unseen_for_library(
                {
                    documents[0].document_id,
                }
            )

            self.assertEqual(
                len(unseen),
                1,
            )

            self.assertEqual(
                unseen[0].document_id,
                documents[1].document_id,
            )


if __name__ == "__main__":
    unittest.main()
