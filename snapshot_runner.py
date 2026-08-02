import time
from collections import deque

from random import uniform

from engine.events import Quote
from engine.feed import MappingSnapshotFeed
from strategies.snapshot_registry import build_snapshot_strategies


counter = 0
previous_timestamp = None

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
        ),
        "BBB": Quote(
            price=50.0,
            total_volume=50000 + (counter * 10000),
        ),
    }


def main():
    global previous_timestamp

    feed = MappingSnapshotFeed(
        fetch_prices=fake_prices,
        expected_symbol_count=2,
    )

    strategies = build_snapshot_strategies()

    for _ in range(35):
        snapshot = feed.fetch()

        gap = None
        if previous_timestamp is not None:
            gap = (snapshot.timestamp - previous_timestamp).total_seconds()

        previous_timestamp = snapshot.timestamp

        signals = []

        for strategy in strategies:
            signals.extend(strategy.on_snapshot(snapshot))

        print(
            "SNAPSHOT",
            snapshot.timestamp,
            "gap=",
            f"{gap:.2f}s" if gap is not None else "first",
            "AAA=",
            snapshot.prices["AAA"],
            "BBB=",
            snapshot.prices["BBB"],
            "symbols=",
            snapshot.returned_symbol_count,
            "signals=",
            len(signals),
        )

        for signal in signals:
            print(signal)

        time.sleep(uniform(0.5, 2.0))


if __name__ == "__main__":
    main()
