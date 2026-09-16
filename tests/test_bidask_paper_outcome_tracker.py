from datetime import datetime, timezone

from bidask_paper_outcome_tracker import BidAskPaperOutcomeTracker


NOW = datetime(2026, 9, 9, 15, 0, tzinfo=timezone.utc)  # 11:00 ET


def quote(bid=9.99, ask=10.01, bid_size=100, ask_size=100):
    ms = NOW.timestamp() * 1000
    return {
        "bid": bid,
        "ask": ask,
        "bid_size_raw": bid_size,
        "ask_size_raw": ask_size,
        "bid_time_ms": ms,
        "ask_time_ms": ms,
        "realtime": True,
    }


def signal(setup="S1"):
    return {
        "setup_id": setup,
        "strategy_id": "C3N25S10",
        "symbol": "XYZ",
        "timestamp": NOW.isoformat(),
        "entry_price": 10.00,
        "target_price": 10.50,
        "stop_price": 9.50,
    }


def test_parallel_tracker_uses_versioned_files(tmp_path):
    tracker = BidAskPaperOutcomeTracker(tmp_path)
    assert tracker.ledger_path.name == "paper_signal_v2_bidask_outcomes.jsonl"
    assert tracker.status_path.name == "paper_signal_v2_bidask_status.json"


def test_entry_crosses_ask_and_exit_marks_bid(tmp_path):
    tracker = BidAskPaperOutcomeTracker(tmp_path)
    assert tracker.register(signal())
    tracker.update_quotes({"XYZ": quote()}, NOW)
    row = tracker.active["S1"]
    assert row["entry_price"] == 10.01
    assert row["entry_fill_outcome"] == "FULL"

    later = datetime(2026, 9, 9, 15, 1, tzinfo=timezone.utc)
    closed = tracker.update_quotes(
        {"XYZ": {**quote(bid=10.60, ask=10.62), "bid_time_ms": later.timestamp()*1000,
                 "ask_time_ms": later.timestamp()*1000}},
        later,
    )
    assert closed[0]["exit_reason"] == "TARGET"
    assert closed[0]["exit_price"] == 10.60


def test_partial_entry_scales_notional(tmp_path):
    tracker = BidAskPaperOutcomeTracker(tmp_path, notional=1000)
    tracker.register(signal())
    tracker.update_quotes({"XYZ": quote(ask_size=7)}, NOW)
    row = tracker.active["S1"]
    assert row["entry_fill_outcome"] == "PARTIAL"
    assert row["filled_qty"] == 7
    assert row["notional"] == 7 * 10.01


def test_symbol_requests_are_hard_capped_and_pending_first(tmp_path):
    tracker = BidAskPaperOutcomeTracker(tmp_path)
    for index in range(5):
        item = signal(f"S{index}")
        item["symbol"] = f"P{index}"
        tracker.register(item)
    assert tracker.symbols(limit=3) == {"P0", "P1", "P2"}


def test_eod_does_not_close_without_fresh_executable_bid(tmp_path):
    tracker = BidAskPaperOutcomeTracker(tmp_path)
    tracker.register(signal())
    tracker.update_quotes({"XYZ": quote()}, NOW)
    eod = datetime(2026, 9, 9, 20, 0, tzinfo=timezone.utc)
    assert tracker.update_quotes({}, eod) == []
    assert "S1" in tracker.active


def test_stale_bid_is_not_used_for_exit(tmp_path):
    tracker = BidAskPaperOutcomeTracker(tmp_path)
    tracker.register(signal())
    tracker.update_quotes({"XYZ": quote()}, NOW)
    later = datetime(2026, 9, 9, 15, 1, tzinfo=timezone.utc)
    stale = quote(bid=10.60, ask=10.62)
    assert tracker.update_quotes({"XYZ": stale}, later) == []
    assert "S1" in tracker.active


def test_cycle_quote_provider_targeted_fetch_after_bulk_miss():
    from bidask_paper_outcome_tracker import CycleQuoteProvider

    calls = []

    def provider(symbols):
        calls.append(list(symbols))
        return {"XYZ": quote()} if "XYZ" in symbols else {}

    cycle = CycleQuoteProvider(provider)

    # Simulate the runner's bulk cycle snapshot: ABC succeeded, while XYZ
    # was requested upstream but produced no usable quote. Only successful
    # quotes should seed the cycle cache.
    cycle.reset({"ABC": quote(bid=19.99, ask=20.01)})

    first = cycle(["XYZ"])
    second = cycle(["XYZ"])

    assert first["XYZ"]["ask"] == 10.01
    assert second["XYZ"]["ask"] == 10.01
    assert calls == [["XYZ"]]
