from collections import defaultdict, deque


class SymbolState:

    def __init__(self, maxlen=10000):
        self.history = defaultdict(lambda: deque(maxlen=maxlen))

    def add(self, symbol, event):
        self.history[symbol].append(event)

    def get(self, symbol):
        return list(self.history[symbol])
