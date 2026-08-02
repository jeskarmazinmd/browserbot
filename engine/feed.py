from abc import ABC, abstractmethod
from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from time import perf_counter

from engine.events import MarketSnapshot, Quote


class SnapshotFeed(ABC):

    @abstractmethod
    def fetch(self) -> MarketSnapshot:
        raise NotImplementedError


class MappingSnapshotFeed(SnapshotFeed):

    def __init__(
        self,
        fetch_prices: Callable[[], Mapping[str, float | Quote]],
        expected_symbol_count: int,
        timestamp_provider: Callable[[], datetime] | None = None,
    ):
        self.fetch_prices = fetch_prices
        self.expected_symbol_count = expected_symbol_count
        self.timestamp_provider = (
            timestamp_provider
            if timestamp_provider is not None
            else lambda: datetime.now(timezone.utc)
        )

    def fetch(self) -> MarketSnapshot:

        started = perf_counter()

        raw_quotes = self.fetch_prices()

        quotes = {}

        for symbol, value in raw_quotes.items():
            if isinstance(value, Quote):
                quotes[symbol] = value
            else:
                quotes[symbol] = Quote(
                    price=float(value),
                )

        return MarketSnapshot(
            timestamp=self.timestamp_provider(),
            quotes=quotes,
            expected_symbol_count=self.expected_symbol_count,
            returned_symbol_count=len(quotes),
            fetch_duration_seconds=perf_counter() - started,
        )
