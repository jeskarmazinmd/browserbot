"""
Bounded live minute feed for Module Factory.

Reads the existing collector CSV tape without modifying it and reproduces the
production minute-completion rule:

* final observed price wins for each symbol within a UTC clock minute;
* the newest clock minute is never emitted;
* a minute becomes complete only after a newer minute is observed;
* only bounded minute history is retained in memory.

This module performs no discovery, validation, shadow trading, or order
placement.
"""

from __future__ import annotations

import csv
import io
import os
from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import BinaryIO


@dataclass(frozen=True)
class CompletedMinute:
    minute: datetime
    prices: dict[str, float]


def _parse_timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _clock_minute(value: datetime) -> datetime:
    return value.astimezone(timezone.utc).replace(
        second=0,
        microsecond=0,
    )


class LiveMinuteTapeFeed:
    """
    Incrementally tail one collector tape.

    The feed starts at the current end of the tape by default.  This makes
    runtime startup cheap and prevents accidental replay of a multi-hundred-MB
    trading-day file.  Historical warmup can be supplied separately later.
    """

    def __init__(
        self,
        tape_path: str | Path,
        *,
        history_minutes: int = 75,
        start_at_end: bool = True,
    ) -> None:
        if history_minutes < 1:
            raise ValueError("history_minutes must be >= 1")

        self.tape_path = Path(tape_path)
        self.history_minutes = int(history_minutes)
        self.start_at_end = bool(start_at_end)

        self._handle: BinaryIO | None = None
        self._inode: int | None = None
        self._offset = 0
        self._partial = b""

        self._open_minute: datetime | None = None
        self._open_prices: dict[str, float] = {}
        self._history: OrderedDict[datetime, dict[str, float]] = OrderedDict()

    @property
    def history(self) -> tuple[CompletedMinute, ...]:
        return tuple(
            CompletedMinute(minute=minute, prices=dict(prices))
            for minute, prices in self._history.items()
        )

    @property
    def open_minute(self) -> datetime | None:
        return self._open_minute

    @property
    def offset(self) -> int:
        return self._offset

    def close(self) -> None:
        if self._handle is not None:
            self._handle.close()
        self._handle = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        self.close()
        return False

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass

    def _open(self) -> None:
        stat = self.tape_path.stat()
        self.close()

        self._handle = self.tape_path.open("rb")
        self._inode = stat.st_ino
        self._partial = b""

        if self.start_at_end and self._offset == 0:
            self._offset = stat.st_size

        self._handle.seek(self._offset)

    def _ensure_open(self) -> bool:
        if not self.tape_path.exists():
            return False

        stat = self.tape_path.stat()

        replaced_or_trimmed = (
            self._handle is not None
            and (
                self._inode != stat.st_ino
                or stat.st_size < self._offset
            )
        )

        if replaced_or_trimmed:
            self.close()
            self._inode = None
            self._offset = 0
            self._partial = b""
            self._open_minute = None
            self._open_prices = {}
            self._history.clear()

        if self._handle is None:
            self._open()

        return True

    @staticmethod
    def _rows(payload: bytes):
        text = payload.decode("utf-8")
        reader = csv.reader(io.StringIO(text))

        for row in reader:
            if len(row) < 3:
                continue

            timestamp_raw, symbol_raw, price_raw = row[:3]

            if timestamp_raw == "timestamp_utc":
                continue

            symbol = symbol_raw.strip().upper()
            if not symbol:
                continue

            try:
                timestamp = _parse_timestamp(timestamp_raw.strip())
                price = float(price_raw)
            except (ValueError, TypeError):
                continue

            if price <= 0:
                continue

            yield timestamp, symbol, price

    def _remember(
        self,
        minute: datetime,
        prices: dict[str, float],
    ) -> CompletedMinute:
        frozen_prices = dict(prices)
        self._history[minute] = frozen_prices
        self._history.move_to_end(minute)

        while len(self._history) > self.history_minutes:
            self._history.popitem(last=False)

        return CompletedMinute(
            minute=minute,
            prices=dict(frozen_prices),
        )

    def _consume_row(
        self,
        timestamp: datetime,
        symbol: str,
        price: float,
    ) -> list[CompletedMinute]:
        minute = _clock_minute(timestamp)

        if self._open_minute is None:
            self._open_minute = minute
            self._open_prices = {symbol: price}
            return []

        if minute == self._open_minute:
            self._open_prices[symbol] = price
            return []

        if minute < self._open_minute:
            # Ignore late/out-of-order rows rather than mutate a minute that
            # has already been declared complete.
            return []

        completed = self._remember(
            self._open_minute,
            self._open_prices,
        )

        self._open_minute = minute
        self._open_prices = {symbol: price}

        return [completed]

    def poll(self) -> list[CompletedMinute]:
        if not self._ensure_open():
            return []

        assert self._handle is not None

        self._handle.seek(self._offset)
        new_bytes = self._handle.read()
        self._offset = self._handle.tell()

        if not new_bytes:
            return []

        payload = self._partial + new_bytes

        if payload.endswith(b"\n"):
            complete = payload
            self._partial = b""
        else:
            split = payload.rfind(b"\n")
            if split < 0:
                self._partial = payload
                return []
            complete = payload[: split + 1]
            self._partial = payload[split + 1 :]

        emitted: list[CompletedMinute] = []

        for timestamp, symbol, price in self._rows(complete):
            emitted.extend(
                self._consume_row(timestamp, symbol, price)
            )

        return emitted


def today_tape(
    data_root: str | Path = "/data",
    *,
    now: datetime | None = None,
) -> Path:
    current = now or datetime.now(timezone.utc)
    day = current.astimezone(timezone.utc).strftime("%Y%m%d")
    return Path(data_root) / "tapes" / f"quotes_{day}.csv"
