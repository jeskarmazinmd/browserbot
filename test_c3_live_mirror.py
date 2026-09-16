from c3_live_logic import C3Config, C3Logic, ExecutableQuote


def q(t, *, last=100.0, bid=99.99, ask=100.01):
    return ExecutableQuote(
        symbol="XYZ", observed_at=t, bid=bid, ask=ask, last=last,
        quote_at=t, realtime=True,
    )


def test_confirming_observation_fills_immediately_at_ask():
    engine = C3Logic(C3Config(max_spread_pct=1.0, max_quote_age_seconds=15.0))
    engine.register_signal("XYZ", "C3N25S10|XYZ|minute", 102.0, q(0, last=100.0))
    engine.on_quote(q(1, last=99.0, bid=98.99, ask=99.01))
    events = engine.on_quote(q(2, last=99.30, bid=99.29, ask=99.31))
    assert [event["event"] for event in events] == ["ENTRY_DECISION", "ENTRY_FILL"]
    assert engine.positions["XYZ"].entry_fill == 99.31
    assert not engine.orders


def test_c2_exit_fills_on_first_qualifying_bid_observation():
    engine = C3Logic(C3Config(max_spread_pct=1.0, max_quote_age_seconds=15.0))
    engine.register_signal("XYZ", "C3N25S10|XYZ|minute", 102.0, q(0, last=100.0))
    engine.on_quote(q(1, last=99.0, bid=98.99, ask=99.01))
    engine.on_quote(q(2, last=99.30, bid=99.29, ask=99.31))
    engine.on_quote(q(3, last=99.70, bid=99.69, ask=99.71))
    events = engine.on_quote(q(34, last=99.65, bid=99.64, ask=99.66))
    assert events[-1]["event"] == "EXIT_FILL"
    assert events[-1]["reason"] == "NO_NEW_HIGH"
    assert not engine.positions


def test_stale_quote_still_blocks_entry():
    engine = C3Logic(C3Config(max_spread_pct=1.0, max_quote_age_seconds=15.0))
    engine.register_signal("XYZ", "C3N25S10|XYZ|minute", 102.0, q(0, last=100.0))
    engine.on_quote(q(1, last=99.0, bid=98.99, ask=99.01))
    stale = ExecutableQuote("XYZ", 20, 99.29, 99.31, last=99.30,
                            quote_at=1, realtime=True)
    events = engine.on_quote(stale)
    assert events[-1]["event"] == "ENTRY_GATE_BLOCK"
    assert events[-1]["reason"] == "stale_quote"
    assert not engine.positions
