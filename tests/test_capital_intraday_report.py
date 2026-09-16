import csv
from datetime import datetime, timezone
import gzip
import json

from reporting.capital_intraday_report import (
    build_report, load_bidask_rows, load_current_bids, load_snapshot_rows,
    render_history, save_finalized_day, summarize_paired,
)


NOW = datetime(2026, 9, 15, 18, 0, tzinfo=timezone.utc)


def write_jsonl(path, rows):
    path.write_text("".join(json.dumps(row) + "\n" for row in rows))


def entry(setup, strategy, symbol, price, stop, minute):
    return {
        "event_type": "PAPER_ENTRY", "setup_id": setup,
        "strategy_id": strategy, "symbol": symbol,
        "signal_timestamp": f"2026-09-15T17:{minute}:00+00:00",
        "entry_price": price, "stop_price": stop,
    }


def test_snapshot_combines_completed_and_marks_open(tmp_path):
    first = entry("a", "C4", "AAA", 100, 95, "00")
    second = entry("b", "C4", "BBB", 50, 45, "01")
    exited = dict(first, event_type="PAPER_EXIT", exit_timestamp="2026-09-15T17:30:00+00:00", exit_price=110)
    ledger = tmp_path / "paper_signal_outcomes.jsonl"
    write_jsonl(ledger, [first, second, exited])

    rows, unpriced, sequences = load_snapshot_rows(ledger, {"main_last": {"BBB": 55}}, "2026-09-15", NOW)

    assert unpriced == 0
    assert len(rows) == 2
    assert {row["exit_price"] for row in rows} == {110, 55}
    assert sorted(row["entry_sequence"] for row in rows) == [0, 1]
    assert sequences == {"a": 0, "b": 1}


def test_bidask_snapshot_uses_ask_entry_and_current_bid_exit(tmp_path):
    ledger = tmp_path / "ba.jsonl"
    write_jsonl(ledger, [{
        **entry("a", "C4", "AAA", 100.2, 95, "00"),
        "event_type": "BA_REPRICE_ENTRY", "entry_ask": 100.2,
        "parent_setup_id": "a",
    }])
    rows, unpriced = load_bidask_rows(
        ledger, {"AAA": 109.8}, "2026-09-15", NOW, {"a": 0}
    )
    assert unpriced == 0
    assert rows[0]["entry_price"] == 100.2
    assert rows[0]["exit_price"] == 109.8


def test_damaged_gzip_tail_keeps_complete_bid_rows(tmp_path):
    rich = tmp_path / "research_market"
    rich.mkdir()
    path = rich / "minute_market_quotes_20260915.csv.gz"
    with gzip.open(path, "wt", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["observed_at_utc", "symbol", "bid"])
        writer.writeheader()
        writer.writerow({"observed_at_utc": NOW.isoformat(), "symbol": "AAA", "bid": "109.8"})
    with path.open("ab") as handle:
        handle.write(b"not-a-valid-gzip-tail")
    assert load_current_bids(tmp_path, "2026-09-15", NOW) == {"AAA": 109.8}


def test_report_is_terminal_friendly_and_read_only(tmp_path):
    tape = tmp_path / "tapes"
    tape.mkdir()
    with (tape / "quotes_20260915.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["timestamp_utc", "symbol", "last_price"])
        writer.writeheader()
        writer.writerow({"timestamp_utc": NOW.isoformat(), "symbol": "AAA", "last_price": "110"})
    ledger = tmp_path / "paper_signal_outcomes.jsonl"
    write_jsonl(ledger, [entry("a", "C4", "AAA", 100, 95, "00")])
    rich = tmp_path / "research_market"
    rich.mkdir()
    with gzip.open(rich / "minute_market_quotes_20260915.csv.gz", "wt", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["observed_at_utc", "symbol", "bid"])
        writer.writeheader()
        writer.writerow({"observed_at_utc": NOW.isoformat(), "symbol": "AAA", "bid": "109.8"})
    write_jsonl(tmp_path / "paper_signal_v3_bidask_repricing_outcomes.jsonl", [{
        **entry("a", "C4", "AAA", 100.2, 95, "00"),
        "event_type": "BA_REPRICE_ENTRY", "parent_setup_id": "a",
    }])
    before = ledger.read_bytes()

    report = build_report(tmp_path, "2026-09-15", NOW, detail=True)

    assert "LAST vs REALISTIC BID/ASK" in report
    assert "C4" in report
    assert "+2.00%" in report
    assert "+1.73%" in report
    assert "100.0%" in report
    assert ledger.read_bytes() == before


def test_current_day_does_not_scan_archives(tmp_path, monkeypatch):
    (tmp_path / "tapes").mkdir()
    (tmp_path / "archive").mkdir()
    (tmp_path / "paper_signal_outcomes.jsonl").write_text("")
    monkeypatch.setattr(
        "reporting.capital_intraday_report.load_archive",
        lambda path: (_ for _ in ()).throw(AssertionError("archive scanned")),
    )
    build_report(tmp_path, "2026-09-15", NOW, detail=True)


def test_summary_compares_only_identical_setups():
    parent_a = {
        **entry("a", "C4", "AAA", 100, 95, "00"),
        "exit_timestamp": NOW.isoformat(), "exit_price": 110,
    }
    parent_b = {
        **entry("b", "C4", "BBB", 50, 45, "01"),
        "exit_timestamp": NOW.isoformat(), "exit_price": 40,
    }
    ba_a = dict(parent_a, entry_price=101, exit_price=109)
    summary = summarize_paired([parent_a, parent_b], [ba_a])["C4"]
    assert summary["full_last"]["signals"] == 2
    assert summary["paired_last"]["signals"] == 1
    assert summary["paired_ba"]["signals"] == 1
    assert summary["coverage_pct"] == 50.0
    assert summary["paired_ba"]["return_pct"] < summary["paired_last"]["return_pct"]


def test_daily_history_is_immutable_and_renders_days_as_columns(tmp_path):
    row = {
        "full_last": {"return_pct": 2.0},
        "paired_last": {"return_pct": 1.5},
        "paired_ba": {"return_pct": 1.0, "signals": 1},
        "realized_ba": {"return_pct": 1.0},
        "coverage_pct": 100.0,
        "open_pairs": 0,
    }
    assert save_finalized_day(tmp_path, "2026-09-14", {"C4": row}, NOW)
    assert not save_finalized_day(tmp_path, "2026-09-14", {"C4": {}}, NOW)
    output = render_history(
        json.loads((tmp_path / "capital_bidask_daily_history.json").read_text()),
        "2026-09-15", {"C4": row}, "all", "overall",
    )
    assert "09-14" in output and "09-15" in output
    assert output.count("+1.00%/-0.50%") == 2
    assert "+2.00%" in output
