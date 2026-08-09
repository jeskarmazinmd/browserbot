import unittest
from pathlib import Path


class SwingWiringTests(unittest.TestCase):
    def test_worker_is_read_only_and_market_gated(self):
        source = Path("swing_shadow_worker.py").read_text()
        self.assertNotIn("schwab_trade_token", source)
        self.assertNotIn("place_order", source)
        self.assertNotIn("get_schwab_client", source)
        gate = source.index("if not regular_market(now)")
        self.assertLess(gate, source.index("load_history(now)", gate))
        self.assertLess(gate, source.index("fetch_quotes()", gate))

    def test_supervisor_and_docker_are_optional_worker_wired(self):
        supervisor = Path("supervisor.py").read_text()
        dockerfile = Path("Dockerfile").read_text()
        self.assertIn('"swing_shadow": [sys.executable, "-u", "swing_shadow_worker.py"]', supervisor)
        self.assertIn("COPY swing_shadow_worker.py .", dockerfile)
        self.assertIn("COPY swing_paper_tracker.py .", dockerfile)
        self.assertIn("COPY swing_strategies /app/swing_strategies", dockerfile)


if __name__ == "__main__":
    unittest.main()
