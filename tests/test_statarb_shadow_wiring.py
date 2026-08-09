import pathlib,unittest
class StatArbShadowWiringTests(unittest.TestCase):
 def test_worker_has_no_trade_or_oauth_client(self):
  src=pathlib.Path("statarb_shadow_worker.py").read_text()
  for forbidden in ("schwab_trade_token","SchwabTradeClient","place_order","get_schwab_client","client_from_token_file"):self.assertNotIn(forbidden,src)
  self.assertIn("/marketdata/v1/quotes",src);self.assertIn('"broker_execution_enabled":False',src)
 def test_closed_market_gate_precedes_fetch(self):
  src=pathlib.Path("statarb_shadow_worker.py").read_text();loop=src.index("while True:");self.assertLess(src.index("if not regular_market(now):",loop),src.index("raw=fetch_quotes()",loop))
 def test_worker_is_optional(self):
  src=pathlib.Path("supervisor.py").read_text();self.assertIn('"statarb_shadow": [sys.executable, "-u", "statarb_shadow_worker.py"]',src)
 def test_docker_copies_family(self):
  src=pathlib.Path("Dockerfile").read_text();self.assertIn("COPY statarb_shadow_worker.py .",src);self.assertIn("COPY statarb_paper_tracker.py .",src);self.assertIn("COPY statarb_strategies /app/statarb_strategies",src)
if __name__=="__main__":unittest.main()
