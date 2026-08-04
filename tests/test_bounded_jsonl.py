import gzip
import json
from pathlib import Path
import tempfile
import unittest

from bounded_jsonl import append_jsonl, compress_pending


class BoundedJsonlTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.path = self.root / "bot_events.jsonl"
        self.archive = self.root / "archive" / "intraday"

    def tearDown(self):
        self.temp.cleanup()

    def test_rotation_preserves_every_record(self):
        expected = [{"number": number, "text": "x" * 30} for number in range(20)]
        for row in expected:
            append_jsonl(self.path, row, max_bytes=180, archive_root=self.archive)
        actual = []
        for archive in sorted(self.archive.glob("*/*.jsonl.gz")):
            with gzip.open(archive, "rt") as handle:
                actual.extend(json.loads(line) for line in handle)
        actual.extend(json.loads(line) for line in self.path.read_text().splitlines())
        self.assertEqual(actual, expected)
        self.assertLessEqual(self.path.stat().st_size, 180)

    def test_pending_raw_segment_is_recovered(self):
        pending = self.archive / "2026-08-04" / "bot_events.pending.jsonl"
        pending.parent.mkdir(parents=True)
        pending.write_text('{"ok":true}\n')
        recovered = compress_pending(self.archive)
        self.assertEqual(len(recovered), 1)
        self.assertFalse(pending.exists())
        with gzip.open(recovered[0], "rt") as handle:
            self.assertEqual(handle.read(), '{"ok":true}\n')


if __name__ == "__main__":
    unittest.main()
