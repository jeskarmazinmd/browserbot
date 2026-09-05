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
    def test_ioc_entry_is_single_limit_without_attached_exits(self):
        trader = SchwabTradeClient("token", "account")
        trader.enabled = True
        with patch.object(trader, "_post_order") as post:
            post.return_value = {"ok": True, "headers": {}}
            trader.place_ioc_limit_buy_order("XYZ", 7, 10.02)
        payload = post.call_args.args[0]
        self.assertEqual("IMMEDIATE_OR_CANCEL", payload["duration"])
        self.assertEqual("LIMIT", payload["orderType"])
        self.assertEqual("SINGLE", payload["orderStrategyType"])
        self.assertNotIn("childOrderStrategies", payload)
        self.assertEqual(7, payload["orderLegCollection"][0]["quantity"])

    def test_protective_oco_uses_only_confirmed_fill_quantity(self):
        trader = SchwabTradeClient("token", "account")
        trader.enabled = True
        with patch.object(trader, "_post_order") as post:
            post.return_value = {"ok": True, "headers": {}}
            trader.place_oco_exit_order("XYZ", 3, 10.20, 9.90)
        payload = post.call_args.args[0]
        self.assertEqual("OCO", payload["orderStrategyType"])
        quantities = [
            child["orderLegCollection"][0]["quantity"]
            for child in payload["childOrderStrategies"]
        ]
        self.assertEqual([3, 3], quantities)
        self.assertTrue(all(
            child["duration"] == "GOOD_TILL_CANCEL"
            for child in payload["childOrderStrategies"]
        ))

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
