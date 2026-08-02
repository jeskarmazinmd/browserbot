import time
from collections import deque

from engine.events import Quote
from engine.feed import MappingSnapshotFeed
from strategies.snapshot_registry import build_snapshot_strategies


counter = 0

prices = deque(
    [
        100,99,98,97,96,
        95,94,93,92,91,
        90,89,88,87,86,
        85,84,83,82,81,
        80,
        82,85,88,92,97,
        103,110,118,125,132
    ]
)


def fake_prices():
    global counter

    if prices:
        price = prices.popleft()
    else:
        price = 110.0

    counter += 1

    return {
        "AAA": Quote(
            price=float(price),
            total_volume=100000 + (counter * 50000),
        )
    }


def main():
    feed = MappingSnapshotFeed(
        fetch_prices=fake_prices,
        expected_symbol_count=1,
    )

    strategies = build_snapshot_strategies()

    for _ in range(35):
        snapshot = feed.fetch()

        signals = []

        for strategy in strategies:
            signals.extend(strategy.on_snapshot(snapshot))

        print(
            "SNAPSHOT",
            snapshot.timestamp,
            "price=",
            snapshot.prices["AAA"],
            "volume=",
            snapshot.quotes["AAA"].total_volume,
            "signals=",
            len(signals),
        )

        for signal in signals:
            print(signal)

        time.sleep(0.2)


if __name__ == "__main__":
    main()
