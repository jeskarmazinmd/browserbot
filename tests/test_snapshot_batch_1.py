from datetime import datetime, timedelta, timezone
from engine.events import MarketSnapshot, Quote
from strategies.snapshot_registry import build_snapshot_strategies


def snap(t, prices, volumes=None):
    volumes=volumes or {}
    return MarketSnapshot(timestamp=t,quotes={s:Quote(price=p,total_volume=volumes.get(s)) for s,p in prices.items()},
        expected_symbol_count=len(prices),returned_symbol_count=len(prices),fetch_duration_seconds=0.01)


def test_smoke():
    strategies=build_snapshot_strategies()
    t=datetime(2026,8,3,13,30,tzinfo=timezone.utc)
    volume=1_000_000
    emitted=[]
    for i in range(3600):
        # deterministic rising stream with a late acceleration
        price=100.0 + i*0.0002 + (max(0,i-3300)*0.001)
        volume += 100 + (500 if i>3300 else 0)
        s=snap(t+timedelta(seconds=i),{"AAA":price},{"AAA":volume})
        for strategy in strategies:
            emitted.extend(strategy.on_snapshot(s))
    assert all(signal.symbol=="AAA" for signal in emitted)

if __name__ == "__main__":
    test_smoke(); print("snapshot batch 1 smoke test passed")
