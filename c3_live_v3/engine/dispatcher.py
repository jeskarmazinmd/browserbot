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
            try:
                result = strategy.on_snapshot(snapshot)

                if result:
                    signals.extend(result)

            except Exception as exc:
                strategy_name = getattr(
                    strategy,
                    "STRATEGY_ID",
                    strategy.__class__.__name__,
                )

                print(
                    f"STRATEGY_ERROR {strategy_name}: "
                    f"{type(exc).__name__}: {exc}",
                    flush=True,
                )

        return signals
