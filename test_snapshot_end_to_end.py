from replay_quote_source import ReplayQuoteSource
from strategies.registry import on_snapshot
from bot_output import append_bot_event

print("SNAPSHOT END TO END TEST START")

source = ReplayQuoteSource("replay_test.csv")

count = 0
signal_count = 0

while True:
    snapshot = source.fetch_snapshot()

    if snapshot is None:
        break

    count += 1

    signals, errors = on_snapshot(snapshot)

    for signal in signals:
        signal_count += 1
        print("SIGNAL:", signal)

        append_bot_event(
            "STRATEGY_SIGNAL",
            signal=str(signal)
        )

    if getattr(source, "finished", False):
        break

print(f"SNAPSHOTS_PROCESSED={count}")
print(f"SIGNALS_FOUND={signal_count}")
print("SNAPSHOT END TO END TEST COMPLETE")
