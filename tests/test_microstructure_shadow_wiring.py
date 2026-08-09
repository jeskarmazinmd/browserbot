import pathlib
import unittest


class MicrostructureShadowWiringTests(unittest.TestCase):
    def test_worker_has_no_trade_client_or_order_path(self):
        src = pathlib.Path("microstructure_shadow_worker.py").read_text()
        for forbidden in ("schwab_trade_token", "SchwabTradeClient", "place_order", "get_schwab_client", "client_from_token_file"):
            self.assertNotIn(forbidden, src)
        self.assertIn("/marketdata/v1/quotes", src)
        self.assertIn('"broker_execution_enabled": False', src)

    def test_worker_is_optional(self):
        src = pathlib.Path("supervisor.py").read_text()
        self.assertIn('"microstructure_shadow": [sys.executable, "-u", "microstructure_shadow_worker.py"]', src)

    def test_docker_copies_family(self):
        src = pathlib.Path("Dockerfile").read_text()
        self.assertIn("COPY microstructure_shadow_worker.py .", src)
        self.assertIn("COPY microstructure_paper_tracker.py .", src)
        self.assertIn("COPY microstructure_strategies /app/microstructure_strategies", src)


if __name__ == "__main__":
    unittest.main()
