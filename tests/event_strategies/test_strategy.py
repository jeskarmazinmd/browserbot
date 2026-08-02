from engine.events import MarketSnapshot, SignalEvent
from strategies.event_base import EventStrategy


class TestStrategy(EventStrategy):

    name = "TEST"

    def __init__(self):
        self.snapshot_count = 0

    def on_snapshot(
        self,
        snapshot: MarketSnapshot,
    ) -> list[SignalEvent]:
        self.snapshot_count += 1

        if self.snapshot_count != 3:
            return []

        price = snapshot.prices.get("TEST")
        if price is None:
            return []

        return [
            SignalEvent(
                timestamp=snapshot.timestamp,
                strategy_id=self.name,
                symbol="TEST",
                signal_type="TEST_SIGNAL",
                data={
                    "price": price,
                    "snapshots_seen": self.snapshot_count,
                    "returned_symbol_count": snapshot.returned_symbol_count,
                },
            )
        ]
