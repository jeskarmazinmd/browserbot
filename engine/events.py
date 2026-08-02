from dataclasses import dataclass
from datetime import datetime


@dataclass
class QuoteEvent:
    timestamp: datetime
    symbol: str
    price: float


@dataclass
class CandleEvent:
    timestamp: datetime
    symbol: str
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass
class SignalEvent:
    timestamp: datetime
    strategy_id: str
    symbol: str
    signal_type: str
    data: dict
