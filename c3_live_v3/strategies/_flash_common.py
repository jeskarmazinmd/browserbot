from collections import defaultdict, deque
from engine.events import SignalEvent
from strategies.event_base import EventStrategy

class FlashReboundState(EventStrategy):
    def __init__(self):
        self.history = defaultdict(lambda: deque(maxlen=20))
        self.low = {}
        self.started = {}

    def _update(self, snapshot):
        for symbol, quote in snapshot.quotes.items():
            price = float(quote.price)
            self.history[symbol].append(price)
            if symbol not in self.low or price < self.low[symbol]:
                self.low[symbol] = price

    def _reset_if_recovered(self, symbol, price):
        if symbol in self.low and price > self.low[symbol] * 1.01:
            self.low.pop(symbol, None)
