"""Synthetic G7 evaluation and durable fill cost; never production data."""
import json,time,tempfile
from datetime import timedelta
from engine.events import MarketSnapshot,Quote
from strategies import generation_seven as g
from generation_seven_paper_tracker import GenerationSevenBidAskTracker
from tests.test_generation_seven import NOW,signal,book

def benchmark():
 strategies=[g.Strategy(sid) for sid in sorted(g.ALL_IDS)];timings=[];signals=0
 for i in range(120):
  now=NOW+timedelta(minutes=i);q={s:Quote(100*(1.001**i)) for s in g.POOL};snap=MarketSnapshot(now,q,len(q),len(q),0)
  start=time.perf_counter();signals+=sum(len(s.on_snapshot(snap)) for s in strategies);timings.append(time.perf_counter()-start)
 with tempfile.TemporaryDirectory() as root:
  t=GenerationSevenBidAskTracker(root,now_provider=lambda:NOW);start=time.perf_counter()
  accepted=sum(t.register_signal(signal(sid),book(NOW),NOW) for sid in sorted(g.ALL_IDS));fill_seconds=time.perf_counter()-start
  if accepted!=len(g.ALL_IDS):raise AssertionError('G7 synthetic admission incomplete')
 return dict(population=len(g.ALL_IDS),snapshots=120,synthetic_signals=signals,mean_evaluation_seconds=sum(timings)/len(timings),max_evaluation_seconds=max(timings),durable_admitted=accepted,durable_admission_seconds=fill_seconds,scope='synthetic single-process; excludes broker/network/worker IPC')
if __name__=='__main__':print(json.dumps(benchmark(),indent=2))
