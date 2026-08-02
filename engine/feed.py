from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Iterable, Mapping

from engine.events import QuoteEvent


class QuoteFeed(ABC):

    @abstractmethod
    def fetch(self) -> list[QuoteEvent]:
        raise NotImplementedError


class MappingQuoteFeed(QuoteFeed):
    """Adapter for a live snapshot shaped like {symbol: price}."""

    def __init__(self, fetch_prices):
        self._fetch_prices = fetch_prices

    def fetch(self) -> list[QuoteEvent]:
        timestamp = datetime.now(timezone.utc)
        prices: Mapping[str, float] = self._fetch_prices()

        events = []
        for symbol, price in prices.items():
            try:
                value = float(price)
            except (TypeError, ValueError):
                continue

            if value <= 0:
                continue

            events.append(
                QuoteEvent(
                    timestamp=timestamp,
                    symbol=str(symbol).upper(),
                    price=value,
                )
            )

        return events
