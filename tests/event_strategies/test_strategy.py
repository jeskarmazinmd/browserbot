from engine.events import SignalEvent


class TestStrategy:

    name = "TEST"

    def __init__(self):
        self.count = 0

    def on_quote(self, event):
        self.count += 1

        if self.count == 3:
            return [
                SignalEvent(
                    timestamp=event.timestamp,
                    strategy_id=self.name,
                    symbol=event.symbol,
                    signal_type="TEST_SIGNAL",
                    data={
                        "price": event.price,
                        "quotes_seen": self.count,
                    },
                )
            ]

        return []

    def on_candle(self, event):
        return []
