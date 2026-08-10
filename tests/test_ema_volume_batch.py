from __future__ import annotations

from datetime import datetime, timedelta, timezone
import time
import unittest

from strategies.ema_volume_batch import BoundedVolumeConfirmation


class BoundedVolumeConfirmationTests(unittest.TestCase):
    def test_deduplicates_and_reuses_results_within_minute(self):
        calls = []
        confirmer = BoundedVolumeConfirmation(2, 10, 1)
        stamp = datetime(2026, 8, 10, 19, 30, tzinfo=timezone.utc)
        try:
            fetch = lambda symbol: calls.append(symbol) or 1.5
            first = confirmer.confirm(["AAPL", "MSFT", "AAPL"], stamp, fetch)
            second = confirmer.confirm(["MSFT", "AAPL"], stamp, fetch)
            self.assertEqual(first, {"AAPL": 1.5, "MSFT": 1.5})
            self.assertEqual(second, {"MSFT": 1.5, "AAPL": 1.5})
            self.assertCountEqual(calls, ["AAPL", "MSFT"])
        finally:
            confirmer.close()

    def test_budget_fails_excess_symbols_closed(self):
        confirmer = BoundedVolumeConfirmation(2, 2, 1)
        stamp = datetime(2026, 8, 10, 19, 30, tzinfo=timezone.utc)
        try:
            result = confirmer.confirm(["A", "B", "C"], stamp, lambda _: 2.0)
            self.assertEqual(sum(value == 2.0 for value in result.values()), 2)
            self.assertIsNone(result["C"])
        finally:
            confirmer.close()

    def test_deadline_returns_unavailable_without_blocking(self):
        confirmer = BoundedVolumeConfirmation(1, 2, 0.02)
        stamp = datetime(2026, 8, 10, 19, 30, tzinfo=timezone.utc)
        try:
            started = time.perf_counter()
            result = confirmer.confirm(["A"], stamp, lambda _: time.sleep(0.15) or 2.0)
            self.assertLess(time.perf_counter() - started, 0.10)
            self.assertIsNone(result["A"])
        finally:
            confirmer.close()

    def test_second_caller_shares_first_callers_deadline(self):
        confirmer = BoundedVolumeConfirmation(1, 2, 0.03)
        stamp = datetime(2026, 8, 10, 19, 30, tzinfo=timezone.utc)
        try:
            fetch = lambda _: time.sleep(0.20) or 2.0
            confirmer.confirm(["A"], stamp, fetch)
            started = time.perf_counter()
            result = confirmer.confirm(["A"], stamp, fetch)
            self.assertLess(time.perf_counter() - started, 0.02)
            self.assertIsNone(result["A"])
        finally:
            confirmer.close()

    def test_new_minute_gets_a_fresh_budget(self):
        confirmer = BoundedVolumeConfirmation(1, 1, 1)
        stamp = datetime(2026, 8, 10, 19, 30, tzinfo=timezone.utc)
        try:
            self.assertEqual(confirmer.confirm(["A"], stamp, lambda _: 1.0)["A"], 1.0)
            later = stamp + timedelta(minutes=1)
            self.assertEqual(confirmer.confirm(["B"], later, lambda _: 2.0)["B"], 2.0)
        finally:
            confirmer.close()


if __name__ == "__main__":
    unittest.main()
