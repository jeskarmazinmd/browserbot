from abc import ABC, abstractmethod

class QuoteSource(ABC):
    @abstractmethod
    def read_data(self):
        """Return the same DataFrame currently returned by live_strategy_runner.read_data()."""
        raise NotImplementedError


class LiveQuoteSource(QuoteSource):
    def __init__(self, reader):
        self._reader = reader

    def read_data(self):
        return self._reader()
