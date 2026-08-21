from abc import ABC, abstractmethod

from engine.events import MarketSnapshot, SignalEvent


class EventStrategy(ABC):

    name = "unnamed"

    @abstractmethod
    def on_snapshot(
        self,
        snapshot: MarketSnapshot,
    ) -> list[SignalEvent]:
        raise NotImplementedError
