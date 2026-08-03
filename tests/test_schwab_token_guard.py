import json
import os
import tempfile
import unittest
from pathlib import Path

from schwab_token_guard import (
    atomic_write_json,
    clear_auth_failure,
    is_terminal_refresh_error,
    manual_reauth_required,
    mark_manual_reauth_required,
)


class SchwabTokenGuardTests(unittest.TestCase):
    def test_collector_does_not_touch_trading_token(self):
        source = (Path(__file__).resolve().parents[1] / "live_quote_collector.py").read_text()
        self.assertNotIn("touch_both_schwab_tokens", source)
        self.assertNotIn("schwab_trade_token.json", source)

    def test_runner_rechecks_disabled_trader_after_new_manual_token(self):
        source = (Path(__file__).resolve().parents[1] / "live_strategy_runner.py").read_text()
        self.assertIn("TRADING_AUTH_RECOVERED", source)
        self.assertIn("not trader_enabled", source)

    def test_terminal_refresh_error_detection(self):
        self.assertTrue(is_terminal_refresh_error("invalid_grant: refresh token is revoked"))
        self.assertFalse(is_terminal_refresh_error("temporary network timeout"))

    def test_manual_reauth_status_clears_when_token_is_replaced(self):
        with tempfile.TemporaryDirectory() as root:
            token = Path(root) / "token.json"
            status = Path(root) / "status.json"
            token.write_text("{}")
            mark_manual_reauth_required(token, status, RuntimeError("invalid_grant"))
            self.assertTrue(manual_reauth_required(token, status))
            stat = token.stat()
            os.utime(token, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000))
            self.assertFalse(manual_reauth_required(token, status))
            clear_auth_failure(status)
            self.assertFalse(status.exists())

    def test_atomic_json_replacement(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "token.json"
            atomic_write_json(path, {"token": {"access_token": "secret"}})
            self.assertEqual(json.loads(path.read_text())["token"]["access_token"], "secret")


if __name__ == "__main__":
    unittest.main()
