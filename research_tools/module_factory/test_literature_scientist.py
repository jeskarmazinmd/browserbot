from datetime import datetime, timezone
from pathlib import Path
import tempfile
import unittest

from research_tools.module_factory.knowledge_ingestion import KnowledgeDocument
from research_tools.module_factory.literature_scientist import (
    after_market_hours, reconstruct_abstract, run_once,
)
from research_tools.module_factory.resource_governor import (
    ResourceDecision, ResourceSnapshot,
)


class FakeSource:
    def search(self, query, *, limit):
        return [KnowledgeDocument(
            source_type="academic", title="Intraday momentum and liquidity",
            text="Momentum, bid ask spread, liquidity and reversal predictability.",
            locator="https://example.invalid/paper", tags=(query,),
        )]


class AllowGovernor:
    def check(self, *, data_root):
        return ResourceDecision(
            allowed=True,
            reasons=(),
            snapshot=ResourceSnapshot(
                memory_available_mb=2048,
                memory_total_mb=4096,
                load_1m=0.1,
                cpu_count=8,
                data_free_mb=2048,
            ),
        )


class LiteratureScientistTests(unittest.TestCase):
    def test_reconstructs_openalex_abstract(self):
        self.assertEqual(reconstruct_abstract({"world": [1], "hello": [0]}), "hello world")

    def test_after_hours_boundary(self):
        self.assertFalse(after_market_hours(datetime(2026, 9, 9, 15, 0, tzinfo=timezone.utc)))
        self.assertTrue(after_market_hours(datetime(2026, 9, 9, 22, 0, tzinfo=timezone.utc)))

    def test_retrieval_populates_provenance_corpus_and_ideas(self):
        with tempfile.TemporaryDirectory() as folder:
            result = run_once(
                data_root=Path(folder), force=True, source=FakeSource(),
                queries=("microstructure",), results_per_query=2,
                resource_governor=AllowGovernor(),
            )
            self.assertEqual(result["status"], "OK")
            self.assertEqual(result["documents_added"], 1)
            self.assertGreater(result["ideas_added"], 0)
            root = Path(folder) / "module_factory"
            self.assertTrue((root / "knowledge_corpus.jsonl").exists())
            self.assertTrue((root / "idea_library.jsonl").exists())
