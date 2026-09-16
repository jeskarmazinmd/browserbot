from datetime import datetime, timedelta, timezone

from bidask_multi_leg_paper_tracker import BidAskMultiLegPaperTracker


NOW = datetime(2026, 9, 9, 15, 0, tzinfo=timezone.utc)


def quote(bid, ask, size=100, when=NOW):
    ms = when.timestamp() * 1000
    return {
        "bid": bid, "ask": ask,
        "bid_size_raw": size, "ask_size_raw": size,
        "bid_time_ms": ms, "ask_time_ms": ms, "realtime": True,
    }


def signal():
    return {
        "group_id": "PAIR1", "strategy_id": "PAIRMR1",
        "timestamp": NOW.isoformat(), "take_profit_pct": 1,
        "stop_loss_pct": 1, "max_hold_minutes": 60,
        "legs": [
            {"symbol": "AAA", "side": "LONG", "entry_price": 10, "weight": 1},
            {"symbol": "BBB", "side": "SHORT", "entry_price": 20, "weight": 1},
        ],
    }


def test_atomic_group_crosses_each_side(tmp_path):
    tracker = BidAskMultiLegPaperTracker(tmp_path)
    assert tracker.register(signal())
    tracker.update_quotes({
        "AAA": quote(9.99, 10.01),
        "BBB": quote(19.99, 20.01),
    }, NOW)
    record = tracker.active["PAIR1"]
    assert record["legs"][0]["entry_price"] == 10.01
    assert record["legs"][1]["entry_price"] == 19.99
    assert tracker.entry_full_groups == 1


def test_partial_leg_rejects_entire_group(tmp_path):
    tracker = BidAskMultiLegPaperTracker(tmp_path)
    tracker.register(signal())
    tracker.update_quotes({
        "AAA": quote(9.99, 10.01, size=1),
        "BBB": quote(19.99, 20.01),
    }, NOW)
    assert not tracker.active
    assert not tracker.pending
    assert tracker.entry_rejected_groups == 1


def test_missing_leg_never_creates_one_sided_trade(tmp_path):
    tracker = BidAskMultiLegPaperTracker(tmp_path)
    tracker.register(signal())
    tracker.update_quotes({"AAA": quote(9.99, 10.01)}, NOW)
    assert not tracker.active
    assert "PAIR1" in tracker.pending


def test_exit_requires_fresh_quotes_for_all_legs(tmp_path):
    tracker = BidAskMultiLegPaperTracker(tmp_path)
    tracker.register(signal())
    tracker.update_quotes({
        "AAA": quote(9.99, 10.01), "BBB": quote(19.99, 20.01),
    }, NOW)
    later = NOW + timedelta(minutes=61)
    assert tracker.update_quotes({
        "AAA": quote(10.20, 10.22, when=later),
    }, later) == []
    assert "PAIR1" in tracker.active


def test_full_fresh_exit_closes_group(tmp_path):
    tracker = BidAskMultiLegPaperTracker(tmp_path)
    tracker.register(signal())
    tracker.update_quotes({
        "AAA": quote(9.99, 10.01), "BBB": quote(19.99, 20.01),
    }, NOW)
    later = NOW + timedelta(minutes=61)
    closed = tracker.update_quotes({
        "AAA": quote(10.20, 10.22, when=later),
        "BBB": quote(19.78, 19.80, when=later),
    }, later)
    assert closed[0]["exit_reason"] in {"GROUP_TARGET", "MAX_HOLD"}
    assert not tracker.active
