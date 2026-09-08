from datetime import datetime, timezone
from pathlib import Path

import nh015_execution_family as family


NOW = datetime(2026, 9, 8, 18, 0, tzinfo=timezone.utc)
NOW_MS = int(NOW.timestamp() * 1000)


def signal():
    return {
        "strategy_id": family.SOURCE_STRATEGY_ID,
        "setup_id": "TEST1",
        "symbol": "XYZ",
        "timestamp": NOW.isoformat(),
        "entry_price": 10.00,
        "target_price": 10.20,
        "stop_price": 9.80,
    }


def quote(**changes):
    q = {
        "bid": 9.99,
        "ask": 10.00,
        "bid_time_ms": NOW_MS,
        "ask_time_ms": NOW_MS,
        "realtime": True,
        "bid_size_raw": 500,
        "ask_size_raw": 500,
    }
    q.update(changes)
    return q


def test_family_ioc_records_native_execution(tmp_path):
    tracker = family.NH015ExecutionFamily(tmp_path)

    rows = tracker.register(signal(), quote(), NOW)

    entries = [
        x for x in rows
        if x["event_type"] == "FAMILY_ENTRY"
    ]

    assert entries

    row = entries[0]

    assert row["execution_model"] == "BIDASK_EXEC_V1"
    assert row["entry_price"] == 10.00
    assert row["entry_price_source"] == "ASK"
    assert row["exit_price_source"] == "BID"
    assert row["filled_qty"] > 0


def test_family_partial_fill_owns_only_filled_quantity(tmp_path):
    tracker = family.NH015ExecutionFamily(tmp_path)

    rows = tracker.register(
        signal(),
        quote(ask_size_raw=7),
        NOW,
    )

    entries = [
        x for x in rows
        if x["event_type"] == "FAMILY_ENTRY"
    ]

    assert entries

    row = entries[0]

    assert row["fill_outcome"] == "PARTIAL"
    assert row["filled_qty"] == 7
    assert row["requested_qty"] > 7


def test_family_does_not_fill_stale_quote(tmp_path):
    tracker = family.NH015ExecutionFamily(tmp_path)

    rows = tracker.register(
        signal(),
        quote(ask_time_ms=NOW_MS - 10_000),
        NOW,
    )

    assert not [
        x for x in rows
        if x["event_type"] == "FAMILY_ENTRY"
    ]


def test_family_does_not_fill_without_size(tmp_path):
    tracker = family.NH015ExecutionFamily(tmp_path)

    rows = tracker.register(
        signal(),
        quote(ask_size_raw=None),
        NOW,
    )

    assert not [
        x for x in rows
        if x["event_type"] == "FAMILY_ENTRY"
    ]
