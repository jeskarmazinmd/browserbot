"""Local G2 scan and durable-fill benchmark; does not call Schwab or Fly."""
from datetime import datetime, timezone
import json
from pathlib import Path
import statistics
import sys
import tempfile
import time
import tracemalloc

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from strategies import generation_two as g2, registry
from generation_two_paper_tracker import GenerationTwoBidAskTracker


def main():
    now = datetime(2026, 10, 5, 15, 0, tzinfo=timezone.utc)
    event = {"timestamp": now.isoformat(), "symbol": "XYZ", "flash_drop_pct": 1.4,
             "pre30_return_std_pct": .2, "pre_return_pct": 1., "pre_r2": .7,
             "target_price": 10.5, "flash_start_price": 10.5}
    timings = []
    for _ in range(7):
        start = time.perf_counter()
        for _symbol in range(1000):
            for module in g2.MODULES.values():
                module.accepts_flash(event, 12.)
        timings.append(time.perf_counter() - start)
    book = {"bid": 9.999, "ask": 10., "bid_size_raw": 1000, "ask_size_raw": 1000,
            "bid_time_ms": now.timestamp() * 1000, "ask_time_ms": now.timestamp() * 1000,
            "realtime": True}
    tracemalloc.start()
    with tempfile.TemporaryDirectory() as temp:
        tracker = GenerationTwoBidAskTracker(temp, now_provider=lambda: now)
        start = time.perf_counter()
        accepted = 0
        for sid, module in sorted(g2.MODULES.items()):
            for slot in range(5):
                row = module.refresh_event_for_entry({**event, "symbol": "SYM" + str(slot)}, 10.)
                accepted += tracker.register_signal(row, book, now)
        admission_seconds = time.perf_counter() - start
        current_bytes, peak_bytes = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        updates = []
        quotes = {"SYM" + str(slot): book for slot in range(5)}
        for _ in range(7):
            start = time.perf_counter()
            tracker.update_quotes(quotes, now)
            updates.append(time.perf_counter() - start)
        files = sum(path.stat().st_size for path in Path(temp).iterdir())
        untraced = GenerationTwoBidAskTracker(Path(temp) / "untraced", now_provider=lambda: now)
        start = time.perf_counter()
        untraced_accepted = 0
        for sid, module in sorted(g2.MODULES.items()):
            for slot in range(5):
                row = module.refresh_event_for_entry({**event, "symbol": "SYM" + str(slot)}, 10.)
                untraced_accepted += untraced.register_signal(row, book, now)
        untraced_admission_seconds = time.perf_counter() - start
        assert untraced_accepted == accepted
    result = {
        "g2_modules": len(g2.IDS), "existing_flash_modules": len(registry.FLASH_STRATEGY_MODULES) - len(g2.IDS),
        "synthetic_symbols": 1000, "raw_admission_median_seconds": statistics.median(timings),
        "raw_admission_max_seconds": max(timings),
        "durable_fill_batch_attempts": 320, "durable_fill_batch_accepted": accepted,
        "durable_fill_batch_seconds_with_tracemalloc": admission_seconds,
        "durable_fill_batch_seconds_without_tracemalloc": untraced_admission_seconds,
        "tracker_current_bytes": current_bytes, "tracker_peak_bytes": peak_bytes,
        "active_quote_update_median_seconds": statistics.median(updates),
        "sample_ledger_and_checkpoint_bytes": files,
        "additional_candle_requests_per_g2_confirmation": 0,
        "limitations": "Local synthetic benchmark; not live Fly utilization, full runner latency, or long-run disk growth.",
    }
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
