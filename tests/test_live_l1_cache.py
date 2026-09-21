import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from bidask_paper_outcome_tracker import IndependentBidAskPaperTracker
from live_l1_cache import LiveL1SnapshotReader, publish_live_l1_snapshot
from market_quotes import QuoteSnapshot


NOW = datetime(2026, 9, 21, 15, 0, tzinfo=timezone.utc)


def snapshot(**changes):
    values = {
        "symbol": "XYZ", "legacy_price": 10.0, "last": 10.0, "mark": 10.0,
        "bid": 9.99, "ask": 10.01, "last_size_raw": 7,
        "bid_size_raw": 100, "ask_size_raw": 100,
        "quote_time_ms": int(NOW.timestamp() * 1000),
        "trade_time_ms": int(NOW.timestamp() * 1000),
        "bid_time_ms": int(NOW.timestamp() * 1000),
        "ask_time_ms": int(NOW.timestamp() * 1000),
        "regular_last": 10.0,
        "regular_trade_time_ms": int(NOW.timestamp() * 1000),
        "extended_last": None, "last_mic": "XNAS", "bid_mic": "XNAS",
        "ask_mic": "XNAS", "realtime": True,
    }
    values.update(changes)
    return QuoteSnapshot(**values)


def signal(setup_id="one"):
    return {
        "setup_id": setup_id, "strategy_id": "TESTBA", "symbol": "XYZ",
        "timestamp": NOW.isoformat(), "entry_price": 10.01,
        "target_price": 10.5, "stop_price": 9.5,
    }


class LiveL1CacheTests(unittest.TestCase):
    def test_production_image_and_processes_are_wired_to_shared_cache(self):
        root = Path(__file__).resolve().parents[1]
        dockerfile = (root / "Dockerfile").read_text()
        collector = (root / "live_quote_collector.py").read_text()
        runner = (root / "live_strategy_runner.py").read_text()
        self.assertIn("COPY live_l1_cache.py .", dockerfile)
        self.assertIn("publish_live_l1_snapshot(snapshots, observed_at)", collector)
        self.assertIn("independent_l1 = LiveL1SnapshotReader()", runner)
        self.assertNotIn("CycleQuoteProvider", runner)

    def test_atomic_publication_preserves_rich_quote_fields(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "live.json"
            path.write_text('{"old":true}')
            real_replace = os.replace

            def inspect_then_replace(source, target):
                self.assertEqual(json.loads(path.read_text()), {"old": True})
                real_replace(source, target)

            with mock.patch("live_l1_cache.os.replace", side_effect=inspect_then_replace):
                publish_live_l1_snapshot({"XYZ": snapshot()}, NOW, path)

            quote = LiveL1SnapshotReader(path).quotes(["xyz"])["XYZ"]
            self.assertEqual(quote["bid"], 9.99)
            self.assertEqual(quote["ask"], 10.01)
            self.assertEqual(quote["bid_size_raw"], 100)
            self.assertEqual(quote["ask_size_raw"], 100)
            self.assertEqual(quote["bid_time_ms"], int(NOW.timestamp() * 1000))
            self.assertEqual(quote["ask_time_ms"], int(NOW.timestamp() * 1000))
            self.assertIs(quote["realtime"], True)
            self.assertEqual(quote["collector_observed_at"], NOW.isoformat())

    def test_reader_fails_closed_for_partial_or_invalid_snapshot(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "live.json"
            path.write_text('{"schema":"LIVE_L1_V1","quotes":')
            self.assertEqual(LiveL1SnapshotReader(path).quotes(["XYZ"]), {})

    def test_independent_ba_admission_uses_cache_and_classifier(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            path = root / "live.json"
            publish_live_l1_snapshot({"XYZ": snapshot()}, NOW, path)
            quote = LiveL1SnapshotReader(path).quotes(["XYZ"])["XYZ"]
            tracker = IndependentBidAskPaperTracker(root / "ledger")
            self.assertTrue(tracker.register_signal(signal(), quote, NOW))
            self.assertEqual(tracker.active["one"]["entry_price"], 10.01)

    def test_stale_missing_crossed_and_nonrealtime_quotes_are_rejected(self):
        cases = {
            "missing": None,
            "last_only": snapshot(bid=None, ask=None, bid_size_raw=None, ask_size_raw=None),
            "stale": snapshot(ask_time_ms=int((NOW - timedelta(seconds=6)).timestamp() * 1000)),
            "crossed": snapshot(bid=10.02, ask=10.01),
            "delayed": snapshot(realtime=False),
            "no_liquidity": snapshot(ask_size_raw=0),
        }
        with tempfile.TemporaryDirectory() as temp:
            for name, value in cases.items():
                tracker = IndependentBidAskPaperTracker(Path(temp) / name)
                quote = value.as_dict() if value is not None else None
                self.assertFalse(
                    tracker.register_signal(signal(name), quote, NOW), name
                )


if __name__ == "__main__":
    unittest.main()
