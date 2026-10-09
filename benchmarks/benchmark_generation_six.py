"""Synthetic load benchmark; emits no historical performance or live orders."""
import json,time,tracemalloc
from datetime import datetime,timedelta,timezone
from engine.events import MarketSnapshot,Quote
from strategies import generation_six as g

def benchmark():
 store=g.FeatureStore();strategies=[g.MinuteStrategy(sid,store) for sid in sorted(g.MINUTE_IDS)]
 start=datetime(2026,10,12,14,0,tzinfo=timezone.utc);timings=[];signals=0
 tracemalloc.start()
 for i in range(90):
  quotes={sym:Quote(100*(1.0001 if sym=='SPY' else 1.0008)**i) for sym in g.EQUITIES}
  snap=MarketSnapshot(start+timedelta(minutes=i),quotes,len(quotes),len(quotes),0)
  t=time.perf_counter()
  signals+=sum(len(s.on_snapshot(snap)) for s in strategies)
  event=dict(timestamp=snap.timestamp.isoformat(),flash_drop_pct=2.,pre_return_pct=1.5,pre_r2=.8,pre30_return_std_pct=.4,target_price=4.1)
  for module in g.MODULES.values():module.accepts_flash(event,12.)
  timings.append(time.perf_counter()-t)
 current,peak=tracemalloc.get_traced_memory();tracemalloc.stop()
 return dict(population=400,flash_modules=240,minute_modules=160,snapshots=90,synthetic_signals=signals,
             mean_evaluation_seconds=sum(timings)/len(timings),max_evaluation_seconds=max(timings),
             peak_traced_memory_bytes=peak,scope='single-process strategy evaluation; excludes disk fsync, network and worker IPC')


def tracker_benchmark():
 import tempfile
 from generation_six_paper_tracker import GenerationSixBidAskTracker
 from tests.test_generation_six import signal,book
 from dataclasses import asdict
 birth=datetime(2026,10,12,13,30,tzinfo=timezone.utc)
 started=time.perf_counter();admitted=0
 with tempfile.TemporaryDirectory() as root:
  t=GenerationSixBidAskTracker(root,now_provider=lambda:birth)
  for s in g.CATALOG:
   now=datetime(2026,10,12,s.start_minute//60,(s.start_minute%60)+5,tzinfo=g.NY).astimezone(timezone.utc)
   row=signal(s.strategy_id,now=now)
   if s.strategy_id in g.IDS:
    price=4. if s.architecture=='LOWPRICE' else 102.
    original=4.1 if s.architecture=='LOWPRICE' else 104.
    drop=6. if s.architecture=='LOWPRICE' else 3.
    if s.max_price==3.:price=2.95;original=3.25;drop=12.
    event=dict(timestamp=now.isoformat(),target_price=original,flash_drop_pct=drop,
               pre_return_pct=2.,pre_r2=.95,pre30_return_std_pct=drop/((s.min_units+s.max_units)/2))
    row=g.MODULES[s.strategy_id].refresh_event_for_entry(event,price)
    row.update(strategy_id=s.strategy_id,symbol='TEST',timestamp=now.isoformat())
   else:price=100.
   accepted=t.register_signal(row,book(now,bid=price-.001,ask=price,size=10000),now)
   if not accepted:raise AssertionError(s.strategy_id)
   admitted+=1
  elapsed=time.perf_counter()-started
  return dict(accepted=admitted,elapsed_seconds=elapsed,mean_ms=elapsed*1000/admitted,
              scope='400 independent synthetic admissions including durable fsync; temporary portfolios')

if __name__=='__main__':print(json.dumps(dict(evaluation=benchmark(),tracking=tracker_benchmark()),indent=2))
