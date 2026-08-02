from engine.dispatcher import EventDispatcher
from engine.feed import MappingSnapshotFeed
from tests.event_strategies.stateful_strategy import StatefulStrategy


cycles = iter([
    {"AAA": 100.0, "BBB": 200.0},
    {"AAA": 101.0, "BBB": 199.0},
    {"AAA": 102.0, "BBB": 198.0},
])


def fetch_prices():
    return next(cycles)


feed = MappingSnapshotFeed(
    fetch_prices=fetch_prices,
    expected_symbol_count=2,
)

dispatcher = EventDispatcher()
strategy = StatefulStrategy()
dispatcher.register(strategy)

for _ in range(3):
    snapshot = feed.fetch()
    signals = dispatcher.dispatch_snapshot(snapshot)

    for signal in signals:
        print(signal)

print({
    symbol: list(history)
    for symbol, history in strategy.prices.items()
})
