"""Bounded, cached execution for EMA crossover volume confirmations."""

from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor, wait
from datetime import datetime, timezone
import threading
import time


class BoundedVolumeConfirmation:
    """Deduplicate volume requests and keep broker latency off the shard clock."""

    def __init__(self, max_workers=4, max_symbols=24, timeout_seconds=18.0):
        self.max_workers = max(1, int(max_workers))
        self.max_symbols = max(1, int(max_symbols))
        self.timeout_seconds = max(0.0, float(timeout_seconds))
        self._executor = ThreadPoolExecutor(
            max_workers=self.max_workers,
            thread_name_prefix="ema-volume",
        )
        self._lock = threading.Lock()
        self._bucket = None
        self._cache: dict[str, float | None] = {}
        self._inflight: dict[str, Future] = {}
        self._submitted = 0
        self._deadline = 0.0

    @staticmethod
    def _minute_bucket(timestamp):
        if timestamp is None:
            value = datetime.now(timezone.utc)
        elif isinstance(timestamp, datetime):
            value = timestamp
        else:
            value = datetime.fromisoformat(str(timestamp).replace("Z", "+00:00"))
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).replace(second=0, microsecond=0).isoformat()

    def confirm(self, symbols, timestamp, fetch_one):
        requested = list(dict.fromkeys(str(symbol) for symbol in symbols if symbol))
        bucket = self._minute_bucket(timestamp)
        started = time.perf_counter()

        with self._lock:
            if bucket != self._bucket:
                self._bucket = bucket
                self._cache = {}
                # Old requests may finish in their threads, but their data must
                # never be mistaken for confirmation of the new market minute.
                self._inflight = {}
                self._submitted = 0
                self._deadline = time.monotonic() + self.timeout_seconds

            cached_before = sum(symbol in self._cache for symbol in requested)
            submitted_now = 0
            skipped_budget = 0
            for symbol in requested:
                if symbol in self._cache or symbol in self._inflight:
                    continue
                if self._submitted >= self.max_symbols:
                    skipped_budget += 1
                    continue
                self._inflight[symbol] = self._executor.submit(fetch_one, symbol)
                self._submitted += 1
                submitted_now += 1
            futures = {
                symbol: self._inflight[symbol]
                for symbol in requested
                if symbol in self._inflight
            }

            remaining = max(0.0, self._deadline - time.monotonic())

        if futures and remaining > 0:
            # EMA1RR follows EMA1 in the same shard.  Both share this one
            # per-minute deadline; the second strategy cannot wait another
            # complete timeout for the same broker calls.
            wait(list(futures.values()), timeout=remaining)

        completed_now = 0
        with self._lock:
            for symbol, future in list(futures.items()):
                if not future.done():
                    continue
                try:
                    value = future.result()
                    self._cache[symbol] = None if value is None else float(value)
                except Exception:
                    self._cache[symbol] = None
                self._inflight.pop(symbol, None)
                completed_now += 1
            result = {symbol: self._cache.get(symbol) for symbol in requested}
            timed_out = sum(
                symbol in self._inflight and not self._inflight[symbol].done()
                for symbol in requested
            )

        print(
            "EMA_VOLUME_CONFIRMATION_BATCH "
            f"timestamp={bucket} requested={len(requested)} "
            f"cached={cached_before} submitted={submitted_now} "
            f"completed={completed_now} timed_out={timed_out} "
            f"skipped_budget={skipped_budget} "
            f"seconds={time.perf_counter() - started:.3f}",
            flush=True,
        )
        return result

    def close(self):
        self._executor.shutdown(wait=False, cancel_futures=True)
