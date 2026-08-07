import sys
import types
import unittest
from unittest.mock import patch

requests_stub = types.ModuleType("requests")
requests_stub.post = lambda *args, **kwargs: None
requests_stub.get = lambda *args, **kwargs: None
requests_stub.delete = lambda *args, **kwargs: None
sys.modules.setdefault("requests", requests_stub)

from schwab_clients import SchwabTradeClient


class SchwabTradeSafetyTests(unittest.TestCase):
    def test_order_post_is_blocked_by_default(self):
        trader = SchwabTradeClient("token", "account")

        with patch("schwab_clients.requests.post") as post:
            result = trader.place_entry_trigger_oco_order(
                "XYZ",
                qty=1,
                buy_limit_price=10.00,
                target_price=10.10,
                stop_price=9.90,
            )

        self.assertFalse(result["ok"])
        self.assertEqual(result["status"], "SAFE_MODE_BLOCKED")
        post.assert_not_called()

    def test_explicitly_armed_client_can_reach_order_transport(self):
        trader = SchwabTradeClient("token", "account")
        trader.enabled = True

        response = unittest.mock.Mock()
        response.status_code = 201
        response.headers = {}
        response.text = ""
        response.json.side_effect = ValueError()

        with patch("schwab_clients.requests.post", return_value=response) as post:
            result = trader.place_entry_trigger_oco_order(
                "XYZ",
                qty=1,
                buy_limit_price=10.00,
                target_price=10.10,
                stop_price=9.90,
            )

        self.assertTrue(result["ok"])
        self.assertEqual(result["status_code"], 201)
        post.assert_called_once()


if __name__ == "__main__":
    unittest.main()
