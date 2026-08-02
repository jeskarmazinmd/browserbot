class EventDispatcher:

    def __init__(self):
        self.strategies = []

    def register(self, strategy):
        self.strategies.append(strategy)

    def dispatch_quote(self, event):
        signals = []

        for strategy in self.strategies:
            result = strategy.on_quote(event)
            if result:
                signals.extend(result)

        return signals

    def dispatch_candle(self, event):
        signals = []

        for strategy in self.strategies:
            result = strategy.on_candle(event)
            if result:
                signals.extend(result)

        return signals
