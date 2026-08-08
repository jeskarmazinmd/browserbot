import unittest
from pathlib import Path


class ForexShadowWiringTests(unittest.TestCase):
    def test_worker_has_no_broker_or_oauth_write_path(self):
        text = Path("forex_shadow_worker.py").read_text()
        for forbidden in ("place_order", "schwab_trade_token", "get_schwab_client", "client_from_token_file", "easy_client"):
            self.assertNotIn(forbidden, text)
        self.assertNotIn("TOKEN_PATH.write", text)
        self.assertIn("broker_execution_enabled", text)

    def test_forex_is_not_equity_registry_dependency(self):
        self.assertNotIn("strategies.registry", Path("forex_shadow_worker.py").read_text())


if __name__ == "__main__":
    unittest.main()
