from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class Quote:
    """Usable fields extracted from one Schwab symbol quote."""

    price: float
    total_volume: float | None = None
    bid: float | None = None
    ask: float | None = None


@dataclass(frozen=True)
class MarketSnapshot:
    """One complete market-data observation from a single Schwab fetch cycle."""

    timestamp: datetime
    quotes: dict[str, Quote]
    expected_symbol_count: int
    returned_symbol_count: int
    fetch_duration_seconds: float
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def prices(self) -> dict[str, float]:
        """Temporary compatibility view for existing snapshot strategies."""
        return {
            symbol: quote.price
            for symbol, quote in self.quotes.items()
        }


@dataclass(frozen=True)
class SignalEvent:
    timestamp: datetime
    strategy_id: str
    symbol: str
    signal_type: str
    data: dict[str, Any] = field(default_factory=dict)
