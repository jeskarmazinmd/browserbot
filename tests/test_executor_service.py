import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path


class ExecutorValidationTests(unittest.TestCase):
    def setUp(self):
        self.old = dict(os.environ)
        os.environ.update({
            "EXECUTOR_MODE": "DRY_RUN",
            "LIVE_EXECUTION_ENABLED": "false",
            "EXECUTOR_ALLOWED_SYMBOLS": "SPY",
            "EXECUTOR_ALLOWED_STRATEGIES": "GT1",
            "EXECUTOR_MAX_QUANTITY": "1",
            "EXECUTOR_MAX_SIGNAL_AGE_SECONDS": "30",
        })

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self.old)

    def test_defaults_fail_closed(self):
        from executor_service import Config

        os.environ.pop("EXECUTOR_ALLOWED_SYMBOLS", None)
        os.environ.pop("EXECUTOR_ALLOWED_STRATEGIES", None)
        config = Config.load()
        self.assertFalse(config.live_enabled)
        self.assertEqual(config.allowed_symbols, frozenset())
        self.assertEqual(config.allowed_strategies, frozenset())

    def test_live_mode_is_impossible_in_phase_one(self):
        from executor_service import Config

        os.environ["LIVE_EXECUTION_ENABLED"] = "true"
        with self.assertRaises(RuntimeError):
            Config.load()

    def test_valid_one_share_allowlisted_signal(self):
        from executor_service import Config, validate_signal

        now = datetime.now(timezone.utc)
        signal = {
            "signal_id": "one",
            "strategy_id": "GT1",
            "symbol": "SPY",
            "side": "BUY",
            "quantity": 1,
            "timestamp": now.isoformat(),
        }
        self.assertEqual(validate_signal(signal, Config.load(), now), [])

    def test_rejects_stale_oversized_unapproved_signal(self):
        from executor_service import Config, validate_signal

        now = datetime.now(timezone.utc)
        signal = {
            "signal_id": "bad",
            "strategy_id": "C2",
            "symbol": "PLTR",
            "side": "BUY",
            "quantity": 2,
            "timestamp": (now - timedelta(minutes=2)).isoformat(),
        }
        errors = validate_signal(signal, Config.load(), now)
        self.assertEqual(set(errors), {
            "strategy_not_allowlisted",
            "symbol_not_allowlisted",
            "quantity_out_of_bounds",
            "stale_signal",
        })


if __name__ == "__main__":
    unittest.main()
