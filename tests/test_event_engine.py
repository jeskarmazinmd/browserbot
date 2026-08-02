from engine.dispatcher import EventDispatcher
from engine.feed import MappingSnapshotFeed
from tests.event_strategies.test_strategy import TestStrategy


price_cycles = iter([
    {"TEST": 100.0, "AAPL": 200.0},
    {"TEST": 101.0, "AAPL": 201.0},
    {"TEST": 102.0, "AAPL": 202.0},
])


def fetch_prices():
    return next(price_cycles)


feed = MappingSnapshotFeed(
    fetch_prices=fetch_prices,
    expected_symbol_count=2,
)

dispatcher = EventDispatcher()
dispatcher.register(TestStrategy())

for _ in range(3):
    snapshot = feed.fetch()
    signals = dispatcher.dispatch_snapshot(snapshot)

    if signals:
        print(signals)
