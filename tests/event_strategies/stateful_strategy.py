from collections import defaultdict, deque

from engine.events import MarketSnapshot, SignalEvent
from strategies.event_base import EventStrategy


class StatefulStrategy(EventStrategy):
    name = "STATEFUL_TEST"

    def __init__(self):
        self.prices = defaultdict(lambda: deque(maxlen=3))

    def on_snapshot(
        self,
        snapshot: MarketSnapshot,
    ) -> list[SignalEvent]:
        signals = []

        for symbol, price in snapshot.prices.items():
            history = self.prices[symbol]
            history.append(price)

            if len(history) < 3:
                continue

            first = history[0]
            last = history[-1]

            if last > first:
                signals.append(
                    SignalEvent(
                        timestamp=snapshot.timestamp,
                        strategy_id=self.name,
                        symbol=symbol,
                        signal_type="PRICE_INCREASED",
                        data={
                            "first_price": first,
                            "last_price": last,
                            "observations_stored": len(history),
                        },
                    )
                )

        return signals
