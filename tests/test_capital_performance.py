from datetime import datetime, timedelta, timezone
import unittest

from reporting.capital_performance import simulate_day


class CapitalPerformanceTests(unittest.TestCase):
    def trade(self, n, entry_time, exit_price=10.10):
        return {
            "setup_id": f"C3|TEST{n}",
            "entry_sequence": n,
            "signal_timestamp": entry_time.isoformat(),
            "exit_timestamp": (entry_time + timedelta(minutes=5)).isoformat(),
            "entry_price": 10.0,
            "exit_price": exit_price,
            "stop_price": 9.8,
        }

    def test_capital_constraint_skips_sixth_simultaneous_trade(self):
        t = datetime(2026, 8, 7, 14, 0, tzinfo=timezone.utc)
        rows = [self.trade(n, t) for n in range(6)]
        result = simulate_day(rows)

        self.assertEqual(result["signals"], 6)
        self.assertEqual(result["taken"], 5)
        self.assertEqual(result["skipped"], 1)
        self.assertEqual(result["max_positions"], 5)
        self.assertAlmostEqual(result["peak_deployed"], 5000.0)

    def test_released_capital_can_be_reused(self):
        t = datetime(2026, 8, 7, 14, 0, tzinfo=timezone.utc)
        rows = [self.trade(n, t) for n in range(5)]
        rows.append(self.trade(5, t + timedelta(minutes=6)))

        result = simulate_day(rows)

        self.assertEqual(result["signals"], 6)
        self.assertEqual(result["taken"], 6)
        self.assertEqual(result["skipped"], 0)



    def test_effective_entry_timestamp_controls_hold_time(self):
        t = datetime(2026, 8, 7, 14, 0, tzinfo=timezone.utc)
        row = self.trade(1, t)
        row["entry_timestamp"] = (t + timedelta(minutes=10)).isoformat()
        row["exit_timestamp"] = (t + timedelta(minutes=15)).isoformat()

        result = simulate_day([row])

        self.assertEqual(result["signals"], 1)
        self.assertEqual(result["median_hold_seconds"], 300)

    def test_never_entered_delayed_setup_uses_no_capital(self):
        t = datetime(2026, 8, 7, 14, 0, tzinfo=timezone.utc)
        row = self.trade(1, t)
        row.update({
            "entry_timestamp": None,
            "exit_model": "second_leg",
            "entered": False,
        })

        result = simulate_day([row])

        self.assertEqual(result["signals"], 0)
        self.assertEqual(result["taken"], 0)

if __name__ == "__main__":
    unittest.main()
