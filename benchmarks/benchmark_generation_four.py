"""Synthetic incremental G4 workload, not a production capacity certificate."""
from datetime import datetime,timedelta,timezone
import json
import math
from pathlib import Path
import statistics as st
import sys
import tempfile
import time
import tracemalloc
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from strategies import generation_four as g4
from generation_four_paper_tracker import GenerationFourBidAskTracker
from engine.events import MarketSnapshot,Quote

def main():
    now=datetime(2026,10,8,14,0,tzinfo=timezone.utc)
    pool=sorted({x for s in g4.CATALOG for x in (s.benchmark,)+s.universe})
    tracemalloc.start()
    prices={x:100. for x in pool};strategies=[g4.MinuteStrategy(sid) for sid in sorted(g4.ALL_IDS)]
    timings=[]; signals=0
    peak=0
    for i in range(180):
        ts=now+timedelta(minutes=i)
        for j,symbol in enumerate(pool):
            prices[symbol]*=math.exp((.04*math.sin(i*.6)+.025*math.cos(i*.3+j)+.008)/100)
        snapshot=MarketSnapshot(ts,{s:Quote(p) for s,p in prices.items()},len(pool),len(pool),0.)
        start=time.perf_counter()
        for s in strategies:signals+=len(s.on_snapshot(snapshot))
        if i==65:
            _,peak=tracemalloc.get_traced_memory();tracemalloc.stop()
        if i>=66:timings.append(time.perf_counter()-start)
    at=now+timedelta(minutes=120)
    q=dict(bid=99.99,ask=100.,bid_size_raw=10000,ask_size_raw=10000,
           bid_time_ms=at.timestamp()*1000,ask_time_ms=at.timestamp()*1000,realtime=True)
    with tempfile.TemporaryDirectory() as root:
        tracker=GenerationFourBidAskTracker(root,now_provider=lambda:at)
        start=time.perf_counter();fills=0
        for s in g4.CATALOG:
            r=dict(strategy_id=s.strategy_id,symbol=s.universe[0],timestamp=at.isoformat(),completed_minute=at.isoformat(),
                   entry_price=100.,paper_only=True,live_order_placement=False,
                   rule_version=g4.RULE_VERSION,population_hash=g4.POPULATION_HASH,rule_source_sha256=g4.RULE_SOURCE_SHA256,
                   constituent_votes=[s.mechanism],admission_evidence={'synthetic':True})
            fills+=tracker.register_signal(r,q,at)
        fill_seconds=time.perf_counter()-start
        start=time.perf_counter();tracker.checkpoint(force=True);checkpoint_seconds=time.perf_counter()-start
        later=at+timedelta(seconds=1);q.update(bid_time_ms=later.timestamp()*1000,ask_time_ms=later.timestamp()*1000)
        start=time.perf_counter();tracker.update_quotes({s:q for s in pool},later);update_seconds=time.perf_counter()-start
        byte_count=sum(p.stat().st_size for p in Path(root).iterdir())
    print(json.dumps(dict(population=36,bounded_symbols=len(pool),warmed_minute_median_seconds=st.median(timings),
        warmed_minute_p95_seconds=sorted(timings)[int(.95*len(timings))],
        scanner_peak_traced_bytes=peak,synthetic_signals=signals,
        synthetic_fill_count=fills,durable_fill_batch_seconds=fill_seconds,
        checkpoint_seconds=checkpoint_seconds,quote_update_seconds=update_seconds,sample_bytes_written=byte_count,
        limitations='Local synthetic incremental test only. Tracemalloc is not RSS. Excludes API, full runner, worker IPC, Fly contention and growing ledgers. No return optimization.'),indent=2))
if __name__=='__main__':main()
