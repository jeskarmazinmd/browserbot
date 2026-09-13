"""Bounded reader for completed-minute executable bid/ask evidence.

Reads the existing MinuteMarketArchive produced by the production collector.
No network access, broker access, order placement, or collector modification.
"""

from __future__ import annotations

import csv
import gzip
import io
import math
import zlib
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ARCHIVE_FIELDS = [
    "market_minute_utc", "observed_at_utc", "symbol", "legacy_price",
    "last", "mark", "bid", "ask", "last_size_raw", "bid_size_raw",
    "ask_size_raw", "quote_time_ms", "trade_time_ms", "bid_time_ms",
    "ask_time_ms", "regular_last", "regular_trade_time_ms",
    "extended_last", "last_mic", "bid_mic", "ask_mic", "realtime",
]


def _parse_timestamp(value: Any) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    else:
        text = str(value).strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).replace(second=0, microsecond=0)


def _positive(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number) or number <= 0:
        return None
    return number


@dataclass(frozen=True)
class ExecutableQuote:
    symbol: str
    minute: datetime
    bid: float
    ask: float
    observed_at: datetime | None = None
    quote_time_ms: int | None = None

    def entry_price(self, direction: int) -> float:
        if direction == 1:
            return self.ask
        if direction == -1:
            return self.bid
        raise ValueError("direction must be -1 or +1")

    def exit_price(self, direction: int) -> float:
        if direction == 1:
            return self.bid
        if direction == -1:
            return self.ask
        raise ValueError("direction must be -1 or +1")


class ExecutableMinuteQuoteFeed:
    """Bounded exact-minute lookup over the existing compressed rich archive.

    The archive is intentionally small: one final snapshot per symbol/minute,
    gzip-compressed, with collector-side daily retention.  This reader caches
    only requested minutes and never substitutes another minute or last price.
    """

    def __init__(
        self,
        root: str | Path,
        *,
        max_cached_minutes: int = 75,
        max_quote_age_seconds: float = 90.0,
    ) -> None:
        if max_cached_minutes < 1:
            raise ValueError("max_cached_minutes must be >= 1")
        self.root = Path(root)
        self.max_cached_minutes = int(max_cached_minutes)
        if max_quote_age_seconds <= 0:
            raise ValueError("max_quote_age_seconds must be positive")
        self.max_quote_age_seconds = float(max_quote_age_seconds)
        self._cache: dict[
            datetime, dict[str, ExecutableQuote]
        ] = {}
        self._cache_order: list[datetime] = []
        self._compressed_offsets: dict[Path, int] = {}

    def _usable_quote(
        self,
        *,
        minute: datetime,
        observed_at: datetime | None,
        quote_time_ms: int | None,
    ) -> bool:
        """Require timestamped quote evidence close to collector observation.

        Broker quote time is authoritative.  Comparing it with observed_at
        avoids treating an old, unchanged quote as executable merely because
        the collector wrote it into a current minute.
        """
        if observed_at is None or quote_time_ms is None or quote_time_ms <= 0:
            return False
        try:
            quote_time = datetime.fromtimestamp(
                quote_time_ms / 1000.0, tz=timezone.utc
            )
        except (OverflowError, OSError, ValueError):
            return False
        if observed_at.replace(second=0, microsecond=0) != minute:
            return False
        age = (observed_at - quote_time).total_seconds()
        return -5.0 <= age <= self.max_quote_age_seconds

    def _path(self, minute: datetime) -> Path:
        return self.root / (
            "minute_market_quotes_"
            + minute.strftime("%Y%m%d")
            + ".csv.gz"
        )

    @staticmethod
    def _optional_timestamp(value: Any) -> datetime | None:
        if value is None or not str(value).strip():
            return None
        try:
            text = str(value).strip()
            if text.endswith("Z"):
                text = text[:-1] + "+00:00"
            parsed = datetime.fromisoformat(text)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _optional_int(value: Any) -> int | None:
        try:
            if value is None or not str(value).strip():
                return None
            return int(value)
        except (TypeError, ValueError):
            return None

    def _remember(
        self,
        minute: datetime,
        quotes: dict[str, ExecutableQuote],
    ) -> None:
        self._cache[minute] = quotes
        if minute in self._cache_order:
            self._cache_order.remove(minute)
        self._cache_order.append(minute)
        while len(self._cache_order) > self.max_cached_minutes:
            oldest = self._cache_order.pop(0)
            self._cache.pop(oldest, None)

    def _load_minute(
        self,
        minute: datetime,
    ) -> dict[str, ExecutableQuote]:
        path = self._path(minute)
        if not path.exists() or path.stat().st_size <= 0:
            return {}

        quotes: dict[str, ExecutableQuote] = {}
        try:
            with gzip.open(path, "rt", newline="") as handle:
                for row in csv.DictReader(handle):
                    try:
                        row_minute = _parse_timestamp(
                            row.get("market_minute_utc")
                        )
                    except (TypeError, ValueError):
                        continue

                    if row_minute != minute:
                        continue

                    symbol = str(row.get("symbol") or "").strip().upper()
                    if not symbol:
                        continue

                    bid = _positive(row.get("bid"))
                    ask = _positive(row.get("ask"))
                    if bid is None or ask is None or ask < bid:
                        continue

                    observed_at = self._optional_timestamp(row.get("observed_at_utc"))
                    quote_time_ms = self._optional_int(row.get("quote_time_ms"))
                    if not self._usable_quote(
                        minute=minute,
                        observed_at=observed_at,
                        quote_time_ms=quote_time_ms,
                    ):
                        continue
                    quotes[symbol] = ExecutableQuote(
                        symbol=symbol,
                        minute=minute,
                        bid=bid,
                        ask=ask,
                        observed_at=observed_at,
                        quote_time_ms=quote_time_ms,
                    )
        except (EOFError, gzip.BadGzipFile, OSError, zlib.error):
            # Archive may be in the middle of an append. Fail closed for this
            # lookup; a later lookup can retry rather than inventing a fill.
            return {}

        return quotes

    def _refresh_incremental(self, path: Path) -> None:
        """Read only gzip members appended since the previous refresh."""
        offset = self._compressed_offsets.get(path, 0)
        if not path.exists() or path.stat().st_size <= offset:
            return
        grouped: dict[datetime, dict[str, ExecutableQuote]] = {}
        try:
            with path.open("rb") as raw:
                raw.seek(offset)
                with gzip.GzipFile(fileobj=raw, mode="rb") as compressed:
                    with io.TextIOWrapper(compressed, newline="") as text:
                        for row in csv.DictReader(text, fieldnames=ARCHIVE_FIELDS):
                            if row.get("market_minute_utc") == "market_minute_utc":
                                continue
                            try:
                                minute = _parse_timestamp(row.get("market_minute_utc"))
                            except (TypeError, ValueError):
                                continue
                            symbol = str(row.get("symbol") or "").strip().upper()
                            bid, ask = _positive(row.get("bid")), _positive(row.get("ask"))
                            if not symbol or bid is None or ask is None or ask < bid:
                                continue
                            observed_at = self._optional_timestamp(row.get("observed_at_utc"))
                            quote_time_ms = self._optional_int(row.get("quote_time_ms"))
                            if not self._usable_quote(
                                minute=minute,
                                observed_at=observed_at,
                                quote_time_ms=quote_time_ms,
                            ):
                                continue
                            grouped.setdefault(minute, {})[symbol] = ExecutableQuote(
                                symbol=symbol, minute=minute, bid=bid, ask=ask,
                                observed_at=observed_at,
                                quote_time_ms=quote_time_ms,
                            )
                new_offset = raw.tell()
        except (EOFError, gzip.BadGzipFile, OSError, zlib.error):
            return
        for minute in sorted(grouped):
            self._remember(minute, grouped[minute])
        self._compressed_offsets[path] = new_offset

    def quotes_for_minute(
        self,
        timestamp: Any,
    ) -> dict[str, ExecutableQuote]:
        minute = _parse_timestamp(timestamp)
        if minute not in self._cache:
            path = self._path(minute)
            self._refresh_incremental(path)
            if minute not in self._cache:
                # Supports bounded historical/random lookup after eviction.
                quotes = self._load_minute(minute)
                if quotes:
                    self._remember(minute, quotes)
                return dict(quotes)
        return dict(self._cache[minute])

    def quote(
        self,
        *,
        timestamp: Any,
        symbol: str,
    ) -> ExecutableQuote | None:
        minute = _parse_timestamp(timestamp)
        quotes = self.quotes_for_minute(minute)
        return quotes.get(str(symbol).strip().upper())

    def entry_price(
        self,
        *,
        timestamp: Any,
        symbol: str,
        direction: int,
    ) -> float | None:
        quote = self.quote(timestamp=timestamp, symbol=symbol)
        if quote is None:
            return None
        return quote.entry_price(direction)

    def exit_price(
        self,
        *,
        timestamp: Any,
        symbol: str,
        direction: int,
    ) -> float | None:
        quote = self.quote(timestamp=timestamp, symbol=symbol)
        if quote is None:
            return None
        return quote.exit_price(direction)
