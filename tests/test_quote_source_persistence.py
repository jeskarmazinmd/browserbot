import tempfile
import unittest
from pathlib import Path

import pandas as pd

import quote_source


class QuoteSourcePersistenceTests(unittest.TestCase):
    def test_compact_minute_cache_survives_restart(self):
        with tempfile.TemporaryDirectory() as root:
            tape_dir = Path(root) / "tapes"
            tape_dir.mkdir()
            tape = tape_dir / "quotes_test.csv"
            tape.write_text("")
            now = pd.Timestamp.now(tz="UTC").floor("min")
            cache = pd.DataFrame({
                "timestamp": [now - pd.Timedelta(minutes=30), now],
                "symbol": ["ABC", "ABC"],
                "price": [10.0, 11.0],
            })
            self.assertTrue(quote_source._save_persistent_minute_cache(tape, cache, force=True))
            restored = quote_source._load_persistent_minute_cache(tape)
            self.assertEqual(len(restored), 2)
            self.assertEqual(restored.iloc[-1]["price"], 11.0)


if __name__ == "__main__":
    unittest.main()
