from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class MarketSnapshot:
    """One complete market-data observation from a single fetch cycle."""

    timestamp: datetime
    prices: dict[str, float]
    expected_symbol_count: int
    returned_symbol_count: int
    fetch_duration_seconds: float
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SignalEvent:
    timestamp: datetime
    strategy_id: str
    symbol: str
    signal_type: str
    data: dict[str, Any] = field(default_factory=dict)
