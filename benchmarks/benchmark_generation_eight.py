"""Synthetic causal/load and durable tracking benchmark; no historical P&L."""
import json,time,statistics,resource,tempfile,sys
from datetime import datetime,timedelta,timezone
import numpy as np
from engine.events import MarketSnapshot,Quote
from strategies import generation_eight as g

def reachability():
    rng=np.random.default_rng(8);u,l=g.ROUTES['TECH'];n=len(u)+len(l)
    counts={x:0 for x in g.GATES};signatures={x:[] for x in g.GATES}
    for scenario in range(20):
        r=rng.normal(0,.08,(220,n))
        for j in range(len(u)):
            lag=1+j%3;r[lag:,j]+=.7*r[:-lag,len(u)+j%len(l)]
        p=100*np.exp(np.cumsum(r,axis=0)/100)
        for i in range(96,220,3):
            rows=g._route_features(p[i-96:i],u,l)
            for code in g.GATES:
                hits=tuple(s for s,e in rows.items() if g.admission_accepts('G8'+code+'TECH',e,s))
                counts[code]+=len(hits);signatures[code].append(hits)
    # Directed AR hub plus peripheral impulse preceding delayed hub response.
    r=rng.normal(0,.01,(95,n));hub=np.zeros(95)
    for i in range(1,95):hub[i]=.85*hub[i-1]+rng.normal(0,.04)
    r[:,0]=hub
    for j in range(1,len(u)):r[1:,j]=hub[:-1]+rng.normal(0,.003,94)
    r[-8:-5,:len(u)]=.08;r[-8:-5,0]=0.;r[-5:-3,0]=0.;r[-3:,0]=.06
    p=np.vstack([np.ones(n)*100,100*np.exp(np.cumsum(r,axis=0)/100)])
    rows=g._route_features(p,u,l)
    hits=tuple(s for s,e in rows.items() if g.admission_accepts('G8B02TECH',e,s))
    counts['B02']+=len(hits)
    if not hits:raise AssertionError('Periphery-to-hub causal fixture unreachable')
    if any(v==0 for v in counts.values()):raise AssertionError('Unreachable features: '+str(counts))
    if len({tuple(v) for v in signatures.values()})!=30:raise AssertionError('Synthetic behavior fingerprints duplicated')
    return counts

def benchmark():
    from strategies import registry
    from tests.test_generation_eight import signal,book,NOW
    strategies=registry.MINUTE_STRATEGIES
    start=datetime(2026,10,14,13,30,tzinfo=timezone.utc);times=[];signals=0;errors=[]
    symbol_count=523  # Worst-case 36-symbol quote union on the 487 baseline.
    symbols=sorted(g.SYMBOLS)+['SYN'+str(i) for i in range(symbol_count-len(g.SYMBOLS))]
    rng=np.random.default_rng(80);prices=np.ones(symbol_count)*100
    for i in range(180):
        prices*=np.exp(rng.normal(.00005,.0005,symbol_count))
        snap=MarketSnapshot(start+timedelta(minutes=i),{s:Quote(float(p)) for s,p in zip(symbols,prices)},symbol_count,symbol_count,0)
        began=time.perf_counter()
        for s in strategies:
            try:signals+=len(s.on_snapshot(snap) or [])
            except Exception as exc:errors.append((s.name,str(exc)))
        times.append(time.perf_counter()-began)
    with tempfile.TemporaryDirectory() as root:
        from generation_eight_paper_tracker import GenerationEightBidAskTracker
        began=time.perf_counter();t=GenerationEightBidAskTracker(root,now_provider=lambda:NOW)
        accepted=sum(t.register_signal(signal(s.strategy_id),book(),NOW) for s in g.CATALOG)
        elapsed=time.perf_counter()-began;t.close()
        began=time.perf_counter();t=GenerationEightBidAskTracker(root,now_provider=lambda:NOW);recovery=time.perf_counter()-began;t.close()
    result=dict(population=120,combined_minute_strategies=len(strategies),symbols=symbol_count,snapshots=180,
        mean_ms=statistics.mean(times)*1000,p95_ms=sorted(times)[int(.95*len(times))-1]*1000,max_ms=max(times)*1000,
        synthetic_signals=signals,errors=errors,durable_admissions=accepted,admission_seconds=elapsed,recovery_seconds=recovery,
        rss_mib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024,
        scope='Combined single-process evaluation and actual G8 fsync/admission/recovery. Network and worker IPC excluded.')
    if errors or accepted!=120 or result['p95_ms']>=1000 or result['max_ms']>=5000:raise AssertionError(result)
    return result

def ipc_benchmark():
    from strategies.registry import MinuteStrategyPool
    start=datetime(2026,10,14,13,30,tzinfo=timezone.utc);rng=np.random.default_rng(808);prices=np.ones(523)*100
    symbols=sorted(g.SYMBOLS)+['SYN'+str(i) for i in range(523-len(g.SYMBOLS))]
    times=[];signals=0
    with tempfile.TemporaryDirectory() as root:
        pool=MinuteStrategyPool(shard_count=8,timeout_seconds=30)
        try:
            for i in range(110):
                prices*=np.exp(rng.normal(.00005,.0005,523))
                snap=MarketSnapshot(start+timedelta(minutes=i),{s:Quote(float(p)) for s,p in zip(symbols,prices)},523,523,0)
                began=time.perf_counter();events,errors=pool.evaluate(snap);times.append(time.perf_counter()-began)
                if errors:raise AssertionError(errors)
                signals+=len(events)
        finally:pool.close()
    result=dict(shards=8,snapshots=110,symbols=523,mean_ms=statistics.mean(times)*1000,
                p95_ms=sorted(times)[int(.95*len(times))-1]*1000,max_ms=max(times)*1000,synthetic_signals=signals,
                scope='Actual eight-process evaluator IPC, excludes quote-network fetch and production disk.')
    if result['p95_ms']>=1000 or result['max_ms']>=5000:raise AssertionError(result)
    return result

if __name__=='__main__':
    if '--ipc-only' in sys.argv:print(json.dumps(ipc_benchmark(),indent=2))
    else:print(json.dumps(dict(causal_reachability=reachability(),capacity=benchmark()),indent=2))
