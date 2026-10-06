"""Synthetic incremental G3 workload. Does not certify Fly headroom."""
from datetime import datetime,timedelta,timezone
import json
from pathlib import Path
import statistics
import sys
import tempfile
import time
import tracemalloc

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from strategies import generation_three as g
from generation_three_paper_tracker import GenerationThreeBidAskTracker
from engine.events import MarketSnapshot,Quote

def main():
    now=datetime(2026,10,7,16,30,tzinfo=timezone.utc)
    event=dict(timestamp=now.isoformat(),symbol='XYZ',flash_drop_pct=1.5,pre_return_pct=2.,pre_r2=.85,pre30_return_std_pct=.22,target_price=10.5)
    def quotes(at):return dict(bid=9.999,ask=10.,bid_size_raw=100000,ask_size_raw=100000,bid_time_ms=at.timestamp()*1000,ask_time_ms=at.timestamp()*1000,realtime=True)
    admissions=[]
    for _ in range(5):
        started=time.perf_counter()
        for i in range(1000):
            for s in g.CATALOG:
                if s.strategy_id in g.IDS:g.raw_accepts(s,event,12.)
        admissions.append(time.perf_counter()-started)
    minute=[]
    strategies=[g.MinuteStrategy(sid) for sid in sorted(g.MINUTE_IDS)]
    for i in range(90):
        at=now+timedelta(minutes=i);pool=set(g.EQUITIES)|set(g.COMMODITIES)|{'OIH','UUP'}
        snap=MarketSnapshot(at,{s:Quote(100+i*.08) for s in pool},len(pool),len(pool),0.)
        started=time.perf_counter()
        for s in strategies:s.on_snapshot(snap)
        if i>=65:minute.append(time.perf_counter()-started)
    with tempfile.TemporaryDirectory() as root:
        tracker=GenerationThreeBidAskTracker(root,now_provider=lambda:now)
        started=time.perf_counter()
        accepted=0
        for spec in g.CATALOG:
            sid=spec.strategy_id
            if sid in g.IDS:signal=g.MODULES[sid].refresh_event_for_entry(event,10.)
            else:signal=dict(timestamp=now.isoformat(),completed_minute=now.isoformat(),symbol='XYZ',strategy_id=sid,entry_price=10.,target_price=10.5,stop_price=9.5,constituent_votes=[spec.source])
            signal['setup_id']=sid
            accepted+=tracker.register_signal(signal,quotes(now),now)
        fill_seconds=time.perf_counter()-started
        updates=[]
        for i in range(1,6):
            at=now+timedelta(seconds=i);started=time.perf_counter()
            tracker.update_quotes({'XYZ':quotes(at)},at)
            updates.append(time.perf_counter()-started)
        bytes_written=sum(p.stat().st_size for p in Path(root).iterdir() if p.is_file())
    result={'population':150,'flash_population':66,'minute_population':84,
        'raw_admission_1000_candidates_median_seconds':statistics.median(admissions),
        'all_84_warmed_minute_modules_median_seconds':statistics.median(minute),
        'durable_150_fill_batch_seconds':fill_seconds,'accepted_fills':accepted,
        'quote_update_median_seconds':statistics.median(updates),'short_sample_bytes':bytes_written,
        'limitations':'Synthetic local incremental work only; excludes full runner, API network, worker IPC and Fly CPU/memory/latency. Some controls use raw votes supplied by synthetic input.'}
    print(json.dumps(result,indent=2))

if __name__=='__main__':main()
