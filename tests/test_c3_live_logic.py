import unittest

from c3_live_logic import C3Config, C3Logic, ExecutableQuote


def q(t, *, bid=100.0, ask=100.02, last=100.01, quote_at=None, realtime=True):
    return ExecutableQuote("XYZ", t, bid, ask, last=last, quote_at=t if quote_at is None else quote_at,
                           bid_at=t if quote_at is None else quote_at,
                           ask_at=t if quote_at is None else quote_at, realtime=realtime)


class C3LiveLogicTests(unittest.TestCase):
    def engine(self, **changes):
        return C3Logic(C3Config(**changes))

    def pending(self, engine, t=0.0, target=102.0):
        events = engine.register_signal("XYZ", "setup", target, q(t))
        self.assertEqual(events[0]["event"], "SIGNAL")

    def fill(self, engine, t=0.0):
        self.pending(engine, t)
        engine.on_quote(q(t + 1, bid=99.76, ask=99.78, last=99.77))
        events = engine.on_quote(q(t + 2, bid=100.02, ask=100.04, last=100.03))
        self.assertEqual(events[0]["event"], "ENTRY_DECISION")
        events = engine.on_quote(q(t + 2.3, bid=100.02, ask=100.04, last=100.03))
        self.assertEqual(events[0]["event"], "ENTRY_FILL")
        return engine.positions["XYZ"]

    def test_duplicate_signal_is_idempotent(self):
        e = self.engine(); self.pending(e)
        self.assertEqual(e.register_signal("XYZ", "setup", 102, q(1)), [])

    def test_temporary_bad_quote_does_not_destroy_pending_setup(self):
        e = self.engine(); self.pending(e)
        e.on_quote(q(1, bid=99.7, ask=99.72, last=99.71))
        events = e.on_quote(q(2, bid=100, ask=101, last=100.1))
        self.assertEqual(events[0]["event"], "ENTRY_GATE_BLOCK")
        self.assertIn("XYZ", e.pending)
        events = e.on_quote(q(3, bid=100, ask=100.02, last=100.01))
        self.assertEqual(events[0]["event"], "ENTRY_DECISION")

    def test_stale_quote_blocks_entry_without_rejection(self):
        e = self.engine(); self.pending(e)
        e.on_quote(q(1, bid=99.7, ask=99.72, last=99.71))
        events = e.on_quote(q(10, quote_at=1, bid=100, ask=100.02, last=100.01))
        self.assertEqual(events[0]["reason"], "stale_quote")
        self.assertIn("XYZ", e.pending)

    def test_entry_respects_latency_and_marketable_limit(self):
        e = self.engine(); self.pending(e)
        e.on_quote(q(1, bid=99.7, ask=99.72, last=99.71))
        e.on_quote(q(2, bid=100, ask=100.02, last=100.01))
        self.assertEqual(e.on_quote(q(2.1, bid=100, ask=100.02)), [])
        self.assertEqual(e.on_quote(q(2.3, bid=100, ask=100.20)), [])
        self.assertIn("XYZ", e.orders)

    def test_activation_uses_executable_bid_not_last(self):
        e = self.engine(); p = self.fill(e)
        events = e.on_quote(q(3, bid=p.entry_fill * 1.002, ask=p.entry_fill * 1.004, last=p.entry_fill * 1.004))
        self.assertEqual(events, [])
        self.assertFalse(p.activated)
        events = e.on_quote(q(4, bid=p.entry_fill * 1.0031, ask=p.entry_fill * 1.0033))
        self.assertEqual(events[0]["event"], "ACTIVATED")

    def test_stop_uses_bid_and_records_gap_fill(self):
        e = self.engine(); p = self.fill(e)
        fill_bid = p.stop - 0.20
        events = e.on_quote(q(3, bid=fill_bid, ask=fill_bid + 0.02, last=p.stop + 0.10))
        self.assertEqual(events[0]["reason"], "STOP")
        self.assertEqual(events[0]["exit_fill"], fill_bid)
        self.assertNotIn("XYZ", e.positions)

    def test_small_fall_after_activation_does_not_exit_early(self):
        e = self.engine(); p = self.fill(e)
        activation_bid = p.entry_fill * 1.0031
        e.on_quote(q(4, bid=activation_bid, ask=activation_bid + .02))
        self.assertEqual(e.on_quote(q(20, bid=activation_bid - .05, ask=activation_bid - .03)), [])
        self.assertIn("XYZ", e.positions)

    def test_new_high_resets_thirty_second_clock(self):
        e = self.engine(); p = self.fill(e)
        a = p.entry_fill * 1.0031
        e.on_quote(q(4, bid=a, ask=a + .02))
        e.on_quote(q(25, bid=a + .05, ask=a + .07))
        self.assertEqual(e.on_quote(q(45, bid=a, ask=a + .02)), [])
        events = e.on_quote(q(56, bid=a, ask=a + .02))
        self.assertEqual(events[0]["event"], "EXIT_DECISION")

    def test_exit_decision_due_time_is_immutable(self):
        e = self.engine(); p = self.fill(e)
        a = p.entry_fill * 1.0031
        e.on_quote(q(4, bid=a, ask=a + .02))
        events = e.on_quote(q(35, bid=a - .01, ask=a + .01))
        self.assertEqual(events[0]["event"], "EXIT_DECISION")
        due = p.exit_due_at
        self.assertEqual(e.on_quote(q(35.1, bid=a - .02, ask=a)), [])
        self.assertEqual(p.exit_due_at, due)
        events = e.on_quote(q(due + .01, bid=a - .03, ask=a - .01))
        self.assertEqual(events[0]["event"], "EXIT_FILL")

    def test_stop_outranks_pending_dynamic_exit(self):
        e = self.engine(); p = self.fill(e)
        a = p.entry_fill * 1.0031
        e.on_quote(q(4, bid=a, ask=a + .02))
        e.on_quote(q(35, bid=a - .01, ask=a + .01))
        events = e.on_quote(q(35.1, bid=p.stop - .1, ask=p.stop - .08))
        self.assertEqual(events[0]["reason"], "STOP")

    def test_restart_round_trip_preserves_exact_state(self):
        e = self.engine(); self.fill(e)
        restored = C3Logic.from_dict(e.to_dict(), e.config)
        self.assertEqual(restored.to_dict(), e.to_dict())

    def test_unknown_state_version_is_rejected(self):
        e = self.engine(); payload = e.to_dict(); payload["version"] = 999
        with self.assertRaises(ValueError):
            C3Logic.from_dict(payload)

    def test_eod_uses_current_bid(self):
        e = self.engine(); self.fill(e)
        events = e.on_quote(q(3, bid=99.5, ask=99.52), eod=True)
        self.assertEqual(events[0]["reason"], "EOD")
        self.assertEqual(events[0]["exit_fill"], 99.5)

    def test_invalid_configuration_fails_closed(self):
        with self.assertRaises(ValueError):
            C3Config(order_latency_seconds=3, order_ttl_seconds=2)

    def test_nan_quote_is_blocked(self):
        e = self.engine()
        self.assertEqual(
            e._quote_gate(q(0, bid=float("nan"), ask=100), "bid"),
            "missing_or_crossed_quote",
        )

    def test_regressed_observation_time_is_ignored(self):
        e = self.engine(); self.fill(e)
        e.on_quote(q(5, bid=100.10, ask=100.11))
        events = e.on_quote(q(4, bid=90, ask=90.01))
        self.assertEqual(events[0]["event"], "QUOTE_IGNORED")
        self.assertIn("XYZ", e.positions)

    def test_repeated_bad_position_quote_emits_once(self):
        e = self.engine(); self.fill(e)
        first = e.on_quote(q(10, bid=100, ask=100.02, quote_at=1))
        second = e.on_quote(q(11, bid=100, ask=100.02, quote_at=1))
        self.assertEqual(first[0]["event"], "POSITION_QUOTE_BLOCK")
        self.assertEqual(second, [])

    def test_corrupt_overlapping_restart_state_is_rejected(self):
        e = self.engine(); self.fill(e)
        payload = e.to_dict()
        payload["pending"]["XYZ"] = {
            "setup_id": "other", "created_at": 0, "lowest_signal": 1,
            "target": 2, "last_gate_reason": None,
        }
        with self.assertRaises(ValueError):
            C3Logic.from_dict(payload)

    def test_wide_spread_blocks_entry_but_not_stop_exit(self):
        e = self.engine()
        e.register_signal("XYZ", "x", 101, q(0))
        e.on_quote(q(.5, bid=99.7, ask=99.72, last=99.71))
        blocked = e.on_quote(q(1, bid=100, ask=101, last=100.1))
        self.assertEqual(blocked[0]["event"], "ENTRY_GATE_BLOCK")

        e = self.engine(); p = self.fill(e)
        events = e.on_quote(q(3, bid=p.stop - .1, ask=p.stop + 1))
        self.assertEqual(events[0]["reason"], "STOP")

    def test_nonfinite_target_is_rejected_without_state(self):
        e = self.engine()
        self.assertEqual(e.register_signal("XYZ", "x", float("nan"), q(0)), [])
        self.assertEqual(e.pending, {})


if __name__ == "__main__":
    unittest.main()
