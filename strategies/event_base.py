from abc import ABC, abstractmethod


class EventStrategy(ABC):

    name = "unnamed"

    @abstractmethod
    def on_quote(self, event):
        pass

    def on_candle(self, event):
        pass
