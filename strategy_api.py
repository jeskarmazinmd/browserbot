from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True)
class TradeIntent:
    intent_id: str
    strategy_id: str
    symbol: str
    side: str
    quantity: int
    limit_price: str
    created_at: str
    expires_at: str

    def to_dict(self):
        return asdict(self)


class StrategyPlugin(Protocol):
    strategy_id: str

    def evaluate(self, context: dict) -> list[TradeIntent]: ...
