import unittest
from pathlib import Path


class QuoteSourceWiringTests(unittest.TestCase):
    def test_live_runner_uses_persistent_source_reader(self):
        source = (Path(__file__).resolve().parents[1] / "live_strategy_runner.py").read_text()
        self.assertIn("quote_source = LiveQuoteSource()", source)
        self.assertNotIn("quote_source = LiveQuoteSource(read_data)", source)


if __name__ == "__main__":
    unittest.main()
