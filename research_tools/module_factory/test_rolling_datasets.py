import csv
import gzip
from pathlib import Path
import tempfile
import unittest

from research_tools.module_factory.rolling_datasets import LateHistoricalArchiveError, RollingDatasetLedger, compact_rich_archive


class RollingDatasetTests(unittest.TestCase):
    def test_roles_are_immutable_and_every_fifth_day_is_validation(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            ledger = RollingDatasetLedger(root / "ledger.json")
            values = [ledger.assign(f"2026-08-{day:02d}", source_path=root/f"s{day}", compact_path=root/f"c{day}") for day in range(1, 6)]
            self.assertEqual([item.role for item in values], ["DISCOVERY"] * 4 + ["VALIDATION"])
            restarted = RollingDatasetLedger(root / "ledger.json")
            self.assertEqual(restarted.assign("2026-08-05", source_path=root/"s5", compact_path=root/"c5").role, "VALIDATION")
            with self.assertRaises(RuntimeError):
                restarted.assign("2026-08-05", source_path=root/"changed", compact_path=root/"c5")


    def test_late_historical_day_cannot_rewrite_immutable_cadence(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            ledger = RollingDatasetLedger(root / "ledger.json")
            for day in (1, 2, 3, 4, 7, 8, 10, 11, 14):
                ledger.assign(
                    f"2026-09-{day:02d}",
                    source_path=root / f"s{day}",
                    compact_path=root / f"c{day}",
                )

            self.assertTrue(ledger.is_late_unassigned("2026-09-09"))
            with self.assertRaises(LateHistoricalArchiveError):
                ledger.assign(
                    "2026-09-09",
                    source_path=root / "s9",
                    compact_path=root / "c9",
                )

            # The next chronological archive remains ordinal 10 and therefore
            # validation; the late day cannot steal that immutable role.
            next_item = ledger.assign(
                "2026-09-15",
                source_path=root / "s15",
                compact_path=root / "c15",
            )
            self.assertEqual(next_item.role, "VALIDATION")
            self.assertNotIn("2026-09-09", {item.day for item in ledger.datasets()})

    def test_compaction_preserves_bid_ask_but_drops_unused_fields(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); source = root/"source.csv.gz"; target = root/"compact.csv.gz"
            with gzip.open(source, "wt", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=["market_minute_utc","symbol","last","bid","ask","unused"])
                writer.writeheader(); writer.writerow({"market_minute_utc":"2026-08-01T14:00:00+00:00","symbol":"A","last":"10","bid":"9","ask":"11","unused":"large"})
            result = compact_rich_archive(source, target)
            self.assertTrue(result["created"])
            with gzip.open(target, "rt", newline="") as handle:
                row = next(csv.DictReader(handle))
            self.assertEqual((row["bid"], row["ask"]), ("9", "11"))
            self.assertNotIn("unused", row)

    def test_corrupt_source_fails_closed_and_removes_partial_output(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "source.csv.gz"
            target = root / "compact.csv.gz"
            temporary = target.with_suffix(target.suffix + ".tmp")
            source.write_bytes(b"not-a-gzip-member")
            temporary.write_bytes(b"old-partial-output")

            result = compact_rich_archive(source, target)

            self.assertFalse(result["usable"])
            self.assertFalse(target.exists())
            self.assertFalse(temporary.exists())
            self.assertIn("error", result)
