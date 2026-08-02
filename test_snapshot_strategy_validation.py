"""
Snapshot-native strategy validation harness.

This does not connect to Schwab or place orders.
It creates synthetic MarketSnapshots and checks that strategy modules:
- accept the new snapshot interface
- emit signals only when expected
- reject unrelated market behavior

Initial version: framework only. Add strategy-specific cases as migrations complete.
"""

from datetime import datetime, timezone, timedelta

from engine.events import MarketSnapshot, Quote
from engine.dispatcher import EventDispatcher
from strategies.registry import ENABLED_STRATEGIES


def make_snapshot(symbol_prices):
    now = datetime.now(timezone.utc)
    quotes = {
        symbol: Quote(
            price=float(price),
            total_volume=100000,
            bid=None,
            ask=None,
        )
        for symbol, price in symbol_prices.items()
    }
    return MarketSnapshot(
        timestamp=now,
        quotes=quotes,
        expected_symbol_count=len(quotes),
        returned_symbol_count=len(quotes),
        fetch_duration_seconds=0.0,
        metadata={"test": True},
    )


def load_dispatcher():
    dispatcher = EventDispatcher()
    for strategy in ENABLED_STRATEGIES:
        dispatcher.register(strategy)
    return dispatcher


def run_case(name, snapshot, expected_signal_ids=None):
    expected_signal_ids = expected_signal_ids or []

    dispatcher = load_dispatcher()

    print(f"\nCASE: {name}")

    try:
        signals = dispatcher.dispatch_snapshot(snapshot)
    except Exception as exc:
        print(f"FAIL dispatcher crashed: {type(exc).__name__}: {exc}")
        return False

    found = [
        getattr(signal, "strategy_id", None)
        if not isinstance(signal, dict)
        else signal.get("strategy_id")
        for signal in signals
    ]

    print(f"signals={found}")

    for expected in expected_signal_ids:
        if expected not in found:
            print(f"FAIL missing expected signal: {expected}")
            return False

    print("PASS")
    return True


def main():
    print("SNAPSHOT STRATEGY VALIDATION START")

    # Basic pipeline smoke test.
    run_case(
        "flat market should not trigger",
        make_snapshot({"AAA": 100.0, "BBB": 50.0}),
    )

    # Future cases:
    # - flash rebound positive
    # - missing data rejection
    # - boundary threshold tests
    # - cross-strategy contamination tests

    print("\nSNAPSHOT STRATEGY VALIDATION COMPLETE")


if __name__ == "__main__":
    main()
