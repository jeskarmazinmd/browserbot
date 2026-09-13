import csv
import gzip
import tempfile
import unittest
import zlib
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from research_tools.module_factory.executable_quote_feed import (
    ExecutableMinuteQuoteFeed,
)


FIELDS = [
    "market_minute_utc",
    "observed_at_utc",
    "symbol",
    "bid",
    "ask",
    "quote_time_ms",
]


def write_rows(root, day, rows):
    rows = [dict(row) for row in rows]
    for row in rows:
        if row.get("quote_time_ms") == "123":
            observed = datetime.fromisoformat(row["observed_at_utc"])
            row["quote_time_ms"] = str(int(observed.timestamp() * 1000))
    path = Path(root) / f"minute_market_quotes_{day}.csv.gz"
    with gzip.open(path, "wt", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    return path


class ExecutableMinuteQuoteFeedTests(unittest.TestCase):
    def test_transient_zlib_error_fails_closed_and_can_retry(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "minute_market_quotes_20260810.csv.gz"
            path.write_bytes(b"incomplete-member")
            feed = ExecutableMinuteQuoteFeed(root)

            with patch(
                "research_tools.module_factory.executable_quote_feed.gzip.GzipFile",
                side_effect=zlib.error("invalid distance too far back"),
            ):
                feed._refresh_incremental(path)

            self.assertNotIn(path, feed._compressed_offsets)

    def test_historical_zlib_error_returns_no_quote(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "minute_market_quotes_20260810.csv.gz"
            path.write_bytes(b"incomplete-member")
            feed = ExecutableMinuteQuoteFeed(root)

            with patch(
                "research_tools.module_factory.executable_quote_feed.gzip.open",
                side_effect=zlib.error("invalid distance too far back"),
            ):
                self.assertEqual(
                    feed._load_minute(
                        datetime(2026, 8, 10, 13, 30, tzinfo=timezone.utc)
                    ),
                    {},
                )

    def test_long_uses_ask_entry_bid_exit(self):
        with tempfile.TemporaryDirectory() as root:
            write_rows(root, "20260810", [{
                "market_minute_utc": "2026-08-10T13:30:00+00:00",
                "observed_at_utc": "2026-08-10T13:30:59+00:00",
                "symbol": "XYZ",
                "bid": "99.9",
                "ask": "100.1",
                "quote_time_ms": "123",
            }])
            feed = ExecutableMinuteQuoteFeed(root)
            ts = datetime(2026,8,10,13,30,tzinfo=timezone.utc)
            self.assertEqual(
                feed.entry_price(
                    timestamp=ts, symbol="XYZ", direction=1
                ),
                100.1,
            )
            self.assertEqual(
                feed.exit_price(
                    timestamp=ts, symbol="XYZ", direction=1
                ),
                99.9,
            )

    def test_short_uses_bid_entry_ask_exit(self):
        with tempfile.TemporaryDirectory() as root:
            write_rows(root, "20260810", [{
                "market_minute_utc": "2026-08-10T13:30:00+00:00",
                "observed_at_utc": "2026-08-10T13:30:59+00:00",
                "symbol": "XYZ",
                "bid": "99.9",
                "ask": "100.1",
                "quote_time_ms": "123",
            }])
            feed = ExecutableMinuteQuoteFeed(root)
            ts = "2026-08-10T13:30:00+00:00"
            self.assertEqual(
                feed.entry_price(
                    timestamp=ts, symbol="xyz", direction=-1
                ),
                99.9,
            )
            self.assertEqual(
                feed.exit_price(
                    timestamp=ts, symbol="xyz", direction=-1
                ),
                100.1,
            )

    def test_missing_exact_minute_never_uses_neighbour(self):
        with tempfile.TemporaryDirectory() as root:
            write_rows(root, "20260810", [{
                "market_minute_utc": "2026-08-10T13:31:00+00:00",
                "observed_at_utc": "2026-08-10T13:31:59+00:00",
                "symbol": "XYZ",
                "bid": "100",
                "ask": "101",
                "quote_time_ms": "123",
            }])
            feed = ExecutableMinuteQuoteFeed(root)
            self.assertIsNone(
                feed.entry_price(
                    timestamp="2026-08-10T13:30:00+00:00",
                    symbol="XYZ",
                    direction=1,
                )
            )

    def test_missing_side_rejects_quote(self):
        with tempfile.TemporaryDirectory() as root:
            write_rows(root, "20260810", [{
                "market_minute_utc": "2026-08-10T13:30:00+00:00",
                "observed_at_utc": "2026-08-10T13:30:59+00:00",
                "symbol": "XYZ",
                "bid": "",
                "ask": "101",
                "quote_time_ms": "123",
            }])
            feed = ExecutableMinuteQuoteFeed(root)
            self.assertIsNone(
                feed.entry_price(
                    timestamp="2026-08-10T13:30:00+00:00",
                    symbol="XYZ",
                    direction=1,
                )
            )

    def test_crossed_quote_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            write_rows(root, "20260810", [{
                "market_minute_utc": "2026-08-10T13:30:00+00:00",
                "observed_at_utc": "2026-08-10T13:30:59+00:00",
                "symbol": "XYZ",
                "bid": "101",
                "ask": "100",
                "quote_time_ms": "123",
            }])
            feed = ExecutableMinuteQuoteFeed(root)
            self.assertIsNone(
                feed.entry_price(
                    timestamp="2026-08-10T13:30:00+00:00",
                    symbol="XYZ",
                    direction=1,
                )
            )

    def test_no_last_price_fallback(self):
        with tempfile.TemporaryDirectory() as root:
            # No rich archive at all.
            feed = ExecutableMinuteQuoteFeed(root)
            self.assertIsNone(
                feed.entry_price(
                    timestamp="2026-08-10T13:30:00+00:00",
                    symbol="XYZ",
                    direction=1,
                )
            )

    def test_stale_and_missing_quote_timestamps_are_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            observed = datetime(2026, 8, 10, 13, 30, 59, tzinfo=timezone.utc)
            write_rows(root, "20260810", [
                {"market_minute_utc": "2026-08-10T13:30:00+00:00",
                 "observed_at_utc": observed.isoformat(), "symbol": "OLD",
                 "bid": "99", "ask": "100",
                 "quote_time_ms": str(int(observed.timestamp() * 1000) - 91_000)},
                {"market_minute_utc": "2026-08-10T13:30:00+00:00",
                 "observed_at_utc": observed.isoformat(), "symbol": "MISSING",
                 "bid": "99", "ask": "100", "quote_time_ms": ""},
            ])
            feed = ExecutableMinuteQuoteFeed(root, max_quote_age_seconds=90)
            for symbol in ("OLD", "MISSING"):
                self.assertIsNone(feed.quote(timestamp="2026-08-10T13:30:00+00:00", symbol=symbol))

    def test_invalid_direction_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            write_rows(root, "20260810", [{
                "market_minute_utc": "2026-08-10T13:30:00+00:00",
                "observed_at_utc": "2026-08-10T13:30:59+00:00",
                "symbol": "XYZ",
                "bid": "99",
                "ask": "100",
                "quote_time_ms": "123",
            }])
            feed = ExecutableMinuteQuoteFeed(root)
            with self.assertRaises(ValueError):
                feed.entry_price(
                    timestamp="2026-08-10T13:30:00+00:00",
                    symbol="XYZ",
                    direction=0,
                )

    def test_cache_is_bounded(self):
        with tempfile.TemporaryDirectory() as root:
            rows = []
            for minute in range(3):
                rows.append({
                    "market_minute_utc":
                        f"2026-08-10T13:{30+minute:02d}:00+00:00",
                    "observed_at_utc":
                        f"2026-08-10T13:{30+minute:02d}:59+00:00",
                    "symbol": "XYZ",
                    "bid": str(99 + minute),
                    "ask": str(100 + minute),
                    "quote_time_ms": "123",
                })
            write_rows(root, "20260810", rows)
            feed = ExecutableMinuteQuoteFeed(
                root,
                max_cached_minutes=2,
            )
            for minute in range(3):
                self.assertIsNotNone(
                    feed.quote(
                        timestamp=(
                            f"2026-08-10T13:{30+minute:02d}:00+00:00"
                        ),
                        symbol="XYZ",
                    )
                )
            self.assertEqual(len(feed._cache), 2)


if __name__ == "__main__":
    unittest.main()
