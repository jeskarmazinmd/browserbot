import unittest
from pathlib import Path

import options_rv_shadow_worker as worker


class OptionsRVWiringTests(unittest.TestCase):
    def test_closed_market_makes_no_requests(self):
        source=Path("options_rv_shadow_worker.py").read_text()
        self.assertIn('"WAITING_REGULAR_MARKET"',source)
        gate=source.index("if regular_market(now)")
        self.assertIn("run_once(now,strategies,tracker)",source[gate:gate+120])

    def test_worker_has_no_trade_path(self):
        source=Path("options_rv_shadow_worker.py").read_text().lower()
        self.assertNotIn("place_order",source)
        self.assertNotIn("schwab_trade_token",source)
        self.assertEqual(worker.UNDERLYINGS,("SPY","QQQ","IWM"))


if __name__=="__main__":
    unittest.main()
