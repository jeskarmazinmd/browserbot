from engine.events import MarketSnapshot, SignalEvent


class EventDispatcher:

    def __init__(self):
        self.strategies = []

    def register(self, strategy) -> None:
        self.strategies.append(strategy)

    def dispatch_snapshot(
        self,
        snapshot: MarketSnapshot,
    ) -> list[SignalEvent]:
        signals: list[SignalEvent] = []

        for strategy in self.strategies:
            result = strategy.on_snapshot(snapshot)

            if result:
                signals.extend(result)

        return signals
