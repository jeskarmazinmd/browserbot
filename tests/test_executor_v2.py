from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
import json
import os
from pathlib import Path
import tempfile
import unittest

from executor_service import Config, validate_intent
from plugin_loader import file_hash, load_plugin
from strategy_api import TradeIntent


class ExecutorV2Tests(unittest.TestCase):
    def setUp(self):
        self.old = dict(os.environ)
        os.environ.update({
            "EXECUTOR_MANUAL_LIVE_ENABLED": "false",
            "EXECUTOR_ALLOWED_SYMBOLS": "TEST",
            "EXECUTOR_MAX_NOTIONAL": "25",
            "EXECUTOR_PLUGIN_STRATEGY_ID": "MANUAL_TEST1",
            "EXECUTOR_PLUGIN_SHA256": "",
        })

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self.old)

    def intent(self, **changes):
        now = datetime.now(timezone.utc)
        value = {
            "intent_id": "one",
            "strategy_id": "MANUAL_TEST1",
            "symbol": "TEST",
            "side": "BUY",
            "quantity": 1,
            "limit_price": "5.00",
            "created_at": now.isoformat(),
            "expires_at": (now + timedelta(seconds=45)).isoformat(),
        }
        value.update(changes)
        return TradeIntent(**value)

    def test_valid_one_share_intent(self):
        self.assertEqual(validate_intent(self.intent(), Config.load()), [])

    def test_naive_plugin_timestamps_are_rejected(self):
        intent = self.intent(
            created_at="2026-08-10T18:00:00",
            expires_at="2026-08-10T18:00:45",
        )
        self.assertIn(
            "stale_or_invalid_window",
            validate_intent(intent, Config.load()),
        )

    def test_rejects_size_symbol_price_and_staleness(self):
        now = datetime.now(timezone.utc)
        intent = self.intent(
            symbol="NOPE",
            quantity=2,
            limit_price="50",
            created_at=(now - timedelta(minutes=2)).isoformat(),
            expires_at=(now - timedelta(minutes=1)).isoformat(),
        )
        self.assertEqual(set(validate_intent(intent, Config.load(), now)), {
            "symbol_not_allowlisted", "quantity_must_equal_one",
            "notional_out_of_bounds", "stale_or_invalid_window",
        })

    def test_live_mode_requires_hash_and_allowlist(self):
        os.environ["EXECUTOR_MANUAL_LIVE_ENABLED"] = "true"
        with self.assertRaises(RuntimeError):
            Config.load()

    def test_plugin_hash_is_enforced(self):
        root = Path(__file__).parents[1] / "plugins" / "manual_test1"
        digest = file_hash(root / "strategy.py")
        plugin, manifest, actual = load_plugin(root, "MANUAL_TEST1", digest)
        self.assertEqual(plugin.strategy_id, "MANUAL_TEST1")
        self.assertEqual(actual, digest)
        with self.assertRaises(RuntimeError):
            load_plugin(root, "MANUAL_TEST1", "0" * 64)


if __name__ == "__main__":
    unittest.main()
