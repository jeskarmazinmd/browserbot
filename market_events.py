from dataclasses import dataclass
from datetime import datetime
from typing import Optional


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
