"""Deterministic CPU, fsync and polling/storage benchmark; not a profitability test."""
from datetime import timedelta
import json
from pathlib import Path
import statistics
import tempfile
import time
import os
import tracemalloc
from strategies import generation_ten as g
from generation_ten_paper_tracker import GenerationTenTracker
from tests.test_generation_ten import NOW,BIRTH,quote,signal


def run():
    loops=1000;start=time.perf_counter()
    event=dict(flash_drop_pct=3.,pre_return_pct=2.,pre_r2=.8)
    for _ in range(loops):
        for s in g.CATALOG:g.raw_accepts(s,event)
    raw_ms=(time.perf_counter()-start)*1000/loops
    samples=[];tracemalloc.start()
    with tempfile.TemporaryDirectory() as root:
        t=GenerationTenTracker(root,now_provider=lambda:BIRTH)
        os.environ['ENABLE_G10_PAPER']='1'
        t.observe_scan(NOW,1000)
        # Worst-case active accounts at one time; time cohorts not open now are naturally rejected.
        for s in g.CATALOG:
            e=signal(s.strategy_id,entry_price=20.,original_target_price=22.4,flash_start_price=24.,running_low_price=19.6)
            t.register_signal(e,quote(ask=20,bid=19.999),NOW)
        active=len(t.active)
        before=t.ledger_path.stat().st_size
        for i in range(10):
            now=NOW+timedelta(seconds=(i+1)*60);start=time.perf_counter()
            t.update_quotes({'XYZ':quote(now,ask=20,bid=19.999)},now)
            samples.append((time.perf_counter()-start)*1000)
        growth=(t.ledger_path.stat().st_size-before)/10
        _,peak=tracemalloc.get_traced_memory();tracemalloc.stop();t.close()
    return dict(population=200,raw_predicates_per_batch=200,predicate_batch_ms=raw_ms,
        worst_case_active_accounts=active,update_median_ms=statistics.median(samples),
        update_max_ms=max(samples),traced_peak_mb=peak/1024**2,ledger_bytes_per_poll=growth,
        estimated_390_poll_session_mb=growth*390/1024**2,
        scope='synthetic local fsync benchmark; production scanner latency and disk capacity must be measured separately')

if __name__=='__main__':print(json.dumps(run(),indent=2))
