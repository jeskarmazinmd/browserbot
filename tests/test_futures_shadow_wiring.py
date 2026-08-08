import unittest
from pathlib import Path


class FuturesShadowWiringTests(unittest.TestCase):
    def test_worker_has_no_broker_or_oauth_write_path(self):
        text = Path("futures_shadow_worker.py").read_text()
        for forbidden in ("place_order", "schwab_trade_token", "get_schwab_client", "client_from_token_file", "easy_client"):
            self.assertNotIn(forbidden, text)
        self.assertIn("broker_execution_enabled", text)

    def test_futures_package_is_not_equity_registry_dependency(self):
        # Futures is deliberately its own optional process/domain.
        text = Path("futures_shadow_worker.py").read_text()
        self.assertNotIn("strategies.registry", text)


if __name__ == "__main__":
    unittest.main()
