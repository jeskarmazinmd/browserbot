import time
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Callable, Mapping

from engine.events import MarketSnapshot


class SnapshotFeed(ABC):

    @abstractmethod
    def fetch(self) -> MarketSnapshot:
        raise NotImplementedError


class MappingSnapshotFeed(SnapshotFeed):
    """Convert one {symbol: price} fetch into one MarketSnapshot."""

    def __init__(
        self,
        fetch_prices: Callable[[], Mapping[str, float]],
        expected_symbol_count: int | None = None,
    ):
        self._fetch_prices = fetch_prices
        self._expected_symbol_count = expected_symbol_count

    def fetch(self) -> MarketSnapshot:
        started = time.perf_counter()
        raw_prices = self._fetch_prices()
        elapsed = time.perf_counter() - started

        prices: dict[str, float] = {}

        for symbol, price in raw_prices.items():
            try:
                value = float(price)
            except (TypeError, ValueError):
                continue

            if value <= 0:
                continue

            prices[str(symbol).upper()] = value

        expected = (
            int(self._expected_symbol_count)
            if self._expected_symbol_count is not None
            else len(raw_prices)
        )

        return MarketSnapshot(
            timestamp=datetime.now(timezone.utc),
            prices=prices,
            expected_symbol_count=expected,
            returned_symbol_count=len(prices),
            fetch_duration_seconds=elapsed,
        )
