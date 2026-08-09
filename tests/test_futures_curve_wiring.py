import unittest
from pathlib import Path
class FuturesCurveWiringTests(unittest.TestCase):
 def test_worker_has_no_broker_or_trade_token_path(self):
  text=Path("futures_curve_shadow_worker.py").read_text()
  for forbidden in ("place_order","schwab_trade_token","get_schwab_client","client_from_token_file","easy_client","futures_shadow_worker"):self.assertNotIn(forbidden,text)
  self.assertIn("broker_execution_enabled",text)
 def test_closed_session_gate_precedes_quote_request(self):
  text=Path("futures_curve_shadow_worker.py").read_text();gate=text.index("if not futures_session(now)");self.assertLess(gate,text.index("fetch_quotes",gate))
 def test_optional_supervisor_and_docker_wiring(self):
  supervisor=Path("supervisor.py").read_text();docker=Path("Dockerfile").read_text();self.assertIn('"futures_curve_shadow": [sys.executable, "-u", "futures_curve_shadow_worker.py"]',supervisor);self.assertIn("COPY futures_curve_shadow_worker.py .",docker);self.assertIn("COPY futures_curve_paper_tracker.py .",docker);self.assertIn("COPY futures_curve_strategies /app/futures_curve_strategies",docker)
if __name__=="__main__":unittest.main()
