from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from research_tools.module_factory.live_minute_feed import (
    LiveMinuteTapeFeed,
    today_tape,
)


class LiveMinuteTapeFeedTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "quotes.csv"
        self.path.write_text(
            "timestamp_utc,symbol,last_price\n",
            encoding="utf-8",
        )

    def tearDown(self):
        self.tmp.cleanup()

    def append(self, text: str):
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(text)

    def test_withholds_newest_minute_and_uses_last_price(self):
        feed = LiveMinuteTapeFeed(
            self.path,
            start_at_end=False,
        )

        self.append(
            "2026-09-03T17:54:01+00:00,AAA,10\n"
            "2026-09-03T17:54:20+00:00,AAA,11\n"
            "2026-09-03T17:54:30+00:00,BBB,20\n"
        )

        self.assertEqual(feed.poll(), [])

        self.append(
            "2026-09-03T17:55:01+00:00,AAA,12\n"
        )

        emitted = feed.poll()
        self.assertEqual(len(emitted), 1)
        self.assertEqual(
            emitted[0].minute,
            datetime(2026, 9, 3, 17, 54, tzinfo=timezone.utc),
        )
        self.assertEqual(
            emitted[0].prices,
            {"AAA": 11.0, "BBB": 20.0},
        )

        self.assertEqual(feed.poll(), [])

    def test_multiple_completed_minutes_can_emit_in_one_poll(self):
        feed = LiveMinuteTapeFeed(
            self.path,
            start_at_end=False,
        )

        self.append(
            "2026-09-03T17:54:01+00:00,AAA,10\n"
            "2026-09-03T17:55:01+00:00,AAA,11\n"
            "2026-09-03T17:56:01+00:00,AAA,12\n"
        )

        emitted = feed.poll()

        self.assertEqual(
            [x.minute.minute for x in emitted],
            [54, 55],
        )
        self.assertEqual(feed.open_minute.minute, 56)

    def test_partial_line_waits_for_completion(self):
        feed = LiveMinuteTapeFeed(
            self.path,
            start_at_end=False,
        )

        self.append(
            "2026-09-03T17:54:01+00:00,AAA,10\n"
            "2026-09-03T17:55:01+00:00,AAA"
        )

        self.assertEqual(feed.poll(), [])

        self.append(",11\n")

        emitted = feed.poll()
        self.assertEqual(len(emitted), 1)
        self.assertEqual(emitted[0].prices["AAA"], 10.0)

    def test_history_is_bounded(self):
        feed = LiveMinuteTapeFeed(
            self.path,
            history_minutes=2,
            start_at_end=False,
        )

        self.append(
            "2026-09-03T17:54:01+00:00,AAA,10\n"
            "2026-09-03T17:55:01+00:00,AAA,11\n"
            "2026-09-03T17:56:01+00:00,AAA,12\n"
            "2026-09-03T17:57:01+00:00,AAA,13\n"
        )

        feed.poll()

        self.assertEqual(
            [x.minute.minute for x in feed.history],
            [55, 56],
        )

    def test_start_at_end_does_not_replay_existing_tape(self):
        self.append(
            "2026-09-03T17:54:01+00:00,AAA,10\n"
        )

        feed = LiveMinuteTapeFeed(
            self.path,
            start_at_end=True,
        )

        self.assertEqual(feed.poll(), [])

        self.append(
            "2026-09-03T17:55:01+00:00,AAA,11\n"
        )

        # First observed minute after startup is still withheld.
        self.assertEqual(feed.poll(), [])

        self.append(
            "2026-09-03T17:56:01+00:00,AAA,12\n"
        )

        emitted = feed.poll()
        self.assertEqual(len(emitted), 1)
        self.assertEqual(emitted[0].minute.minute, 55)

    def test_today_tape(self):
        path = today_tape(
            "/data",
            now=datetime(
                2026, 9, 3, 18, 0,
                tzinfo=timezone.utc,
            ),
        )
        self.assertEqual(
            path,
            Path("/data/tapes/quotes_20260903.csv"),
        )


if __name__ == "__main__":
    unittest.main()
