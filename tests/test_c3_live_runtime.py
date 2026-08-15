import json
from pathlib import Path
import tempfile
import unittest

from c3_live_logic import C3Config, ExecutableQuote
from c3_live_runtime import DurableC3


class DurableC3Tests(unittest.TestCase):
    def q(self, at, bid=99.75, ask=99.77, last=99.76):
        return ExecutableQuote("XYZ", at, bid, ask, last, quote_at=at, realtime=True)

    def test_restart_keeps_signal_dedupe_and_pending(self):
        with tempfile.TemporaryDirectory() as root:
            state = Path(root) / "state.json"
            ledger = Path(root) / "ledger.jsonl"
            runtime = DurableC3.load(state, ledger, C3Config())
            runtime.register_signal("XYZ", "one", 101, self.q(0))
            restarted = DurableC3.load(state, ledger, C3Config())
            self.assertIn("XYZ", restarted.engine.pending)
            self.assertEqual(restarted.register_signal("XYZ", "one", 101, self.q(1)), [])

    def test_ledger_sequences_are_monotonic_and_state_is_valid_json(self):
        with tempfile.TemporaryDirectory() as root:
            state = Path(root) / "state.json"
            ledger = Path(root) / "ledger.jsonl"
            runtime = DurableC3.load(state, ledger, C3Config(order_latency_seconds=.25))
            runtime.register_signal("XYZ", "one", 101, self.q(0))
            runtime.on_quote(self.q(1, bid=100.02, ask=100.04, last=100.03))
            runtime.on_quote(self.q(1.3, bid=100.02, ask=100.04, last=100.03))
            rows = [json.loads(line) for line in ledger.read_text().splitlines()]
            self.assertEqual([r["sequence"] for r in rows], list(range(1, len(rows) + 1)))
            self.assertEqual(json.loads(state.read_text())["sequence"], rows[-1]["sequence"])

    def test_corrupt_state_fails_closed_instead_of_starting_empty(self):
        with tempfile.TemporaryDirectory() as root:
            state = Path(root) / "state.json"
            state.write_text("not-json")
            with self.assertRaises(json.JSONDecodeError):
                DurableC3.load(state, Path(root) / "ledger.jsonl")


if __name__ == "__main__":
    unittest.main()
