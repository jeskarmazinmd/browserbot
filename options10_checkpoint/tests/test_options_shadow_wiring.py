import pathlib,unittest

class OptionsShadowWiringTests(unittest.TestCase):
    def test_worker_has_no_trade_client_or_order_path(self):
        src=pathlib.Path("options_shadow_worker.py").read_text()
        self.assertNotIn("SchwabTradeClient",src);self.assertNotIn("schwab_trade_token",src);self.assertNotIn("place_order",src)
        self.assertNotIn("client_from_token_file",src);self.assertNotIn("get_schwab_client",src)
        self.assertIn("/marketdata/v1/chains",src);self.assertIn('"broker_execution_enabled":False',src)
    def test_supervisor_keeps_options_worker_optional(self):
        src=pathlib.Path("supervisor.py").read_text();self.assertIn('"options_shadow": [sys.executable, "-u", "options_shadow_worker.py"]',src)

if __name__=="__main__":unittest.main()
