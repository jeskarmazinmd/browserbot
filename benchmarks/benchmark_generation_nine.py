"""Deterministic CPU benchmark; synthetic stream is not return evidence."""
from datetime import datetime,timedelta,timezone
import json
import random
import statistics
import time
import tracemalloc
from strategies import generation_nine as g
from statarb_shadow_worker import SYMBOLS


def run():
    rng=random.Random(9015);pop=g.Population();prices={s:100.+i for i,s in enumerate(SYMBOLS)}
    start=datetime(2026,10,16,13,35,tzinfo=timezone.utc);times=[];decisions=0;features=0
    tracemalloc.start()
    for i in range(190):
        now=start+timedelta(minutes=i);r=rng.gauss(0,.0008);quotes={}
        for j,symbol in enumerate(SYMBOLS):
            prices[symbol]*=1+r*(.6+j%10*.1)+rng.gauss(0,.0003)
            if 165<=i<175 and symbol=='AAPL':prices[symbol]*=1.001
            quotes[symbol]=dict(bid=prices[symbol]-.001,ask=prices[symbol]+.001,
                bid_size_raw=1000,ask_size_raw=1000,quote_time_ms=now.timestamp()*1000,realtime=True)
        pop.observe(now,quotes)
        if i<165:continue
        before=time.perf_counter()
        for spec in g.CATALOG:decisions+=pop.decision(spec,now) is not None
        times.append(time.perf_counter()-before);features=max(features,len(pop._cache))
    _,peak=tracemalloc.get_traced_memory();tracemalloc.stop()
    ordered=sorted(times);p95=ordered[int(.95*(len(times)-1))]
    result=dict(population=400,population_hash=g.POPULATION_HASH,symbols=len(SYMBOLS),measured_minutes=len(times),
        median_seconds=statistics.median(times),p95_seconds=p95,max_seconds=max(times),
        feature_cache_keys=features,peak_traced_mb=peak/1024**2,synthetic_decisions=decisions,
        market_requests_added=0,performance_evidence=False)
    if p95>15:raise RuntimeError('G9 population exceeds 15-second minute budget')
    if peak>128*1024**2:raise RuntimeError('G9 traced allocations exceed 128 MiB')
    return result

if __name__=='__main__':print(json.dumps(run(),indent=2))
