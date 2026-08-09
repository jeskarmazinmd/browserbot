import unittest
from pathlib import Path


class ShortShadowWiringTests(unittest.TestCase):
    def test_worker_has_no_broker_or_shared_strategy_path(self):
        text = Path("short_shadow_worker.py").read_text()
        for forbidden in ("place_order", "schwab_trade_token", "get_schwab_client", "client_from_token_file", "PaperOutcomeTracker", "strategies.registry"):
            self.assertNotIn(forbidden, text)
        self.assertNotIn("TOKEN_PATH.write", text)
        self.assertIn("broker_execution_enabled", text)

    def test_tracker_marks_unmodeled_real_shorting_costs(self):
        text = Path("short_paper_tracker.py").read_text()
        self.assertIn('"borrow_fees_included": False', text)
        self.assertIn('"short_locate_verified": False', text)
        self.assertIn('"reg_sho_rule_201_modeled": False', text)


if __name__ == "__main__": unittest.main()
