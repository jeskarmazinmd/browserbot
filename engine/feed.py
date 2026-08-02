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
    def __init__(self, fetch_prices: Callable[[], Mapping[str, float]], expected_symbol_count: int):
        self.fetch_prices = fetch_prices
        self.expected_symbol_count = expected_symbol_count

    def fetch(self) -> MarketSnapshot:
        started = perf_counter()
        prices = self.fetch_prices()
        quotes = {str(symbol).upper(): Quote(price=float(price)) for symbol, price in prices.items() if float(price) > 0}
        return MarketSnapshot(
            timestamp=datetime.now(timezone.utc),
            quotes=quotes,
            expected_symbol_count=self.expected_symbol_count,
            returned_symbol_count=len(quotes),
            fetch_duration_seconds=perf_counter() - started,
        )
