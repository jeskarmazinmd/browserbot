"""Concurrent, literal strategy-family capacity replay for browserbot.

Every production strategy module is imported and evaluated in its native family
process.  Synthetic inputs match worker schemas.  Network connects and writes
under /data are denied by an audit hook.  Output is confined to /tmp.
"""
from __future__ import annotations
import argparse,json,math,multiprocessing as mp,os,sys,tempfile,time
from datetime import datetime,timedelta,timezone
from pathlib import Path

FAMILIES=("collector","main","xs","options","options_rv","futures","futures_curve","forex","short","microstructure","crosssection","statarb","swing")

def deny_external(event,args):
    if event in {"socket.connect","socket.connect_ex","socket.getaddrinfo"}:raise PermissionError("load test network denied")
    if event=="open" and args:
        path=str(args[0]);mode=str(args[1]) if len(args)>1 else "r"
        if path.startswith("/data") and any(x in mode for x in ("w","a","x","+")):raise PermissionError("load test /data write denied")

def rss_mb():
    try:
        for line in Path(f"/proc/{os.getpid()}/status").read_text().splitlines():
            if line.startswith("VmRSS:"):return int(line.split()[1])/1024
    except OSError:return 0.0
    return 0.0

def p95(xs):
    if not xs:return 0.0
    s=sorted(xs);return s[min(len(s)-1,math.ceil(.95*len(s))-1)]

def symbols(n):return ("SPY","QQQ","IWM",*[f"Z{i:04d}" for i in range(max(0,n-3))])

def equity_quotes(names,step,now):
    out={};stamp=int(now.timestamp()*1000)
    for i,s in enumerate(names):
        base=20+(i%400)*.37;last=base*(1+math.sin((step+i%19)/23)*.004);spread=max(.01,last*.0004)
        out[s]={"symbol":s,"realtime":True,"bid":last-spread/2,"ask":last+spread/2,"last":last,"mark":last,"close":base,"open":base*.998,"bidSize":100+i%50,"askSize":90+(i*3)%50,"bid_size":100+i%50,"ask_size":90+(i*3)%50,"quoteTime":stamp,"tradeTime":stamp,"quote_time_ms":stamp,"bid_time_ms":stamp,"ask_time_ms":stamp,"trade_time_ms":stamp,"totalVolume":100000+i*100,"total_volume":100000+i*100}
    return out

def option_contracts(underlying,step):
    rows=[];spot=100+step*.01
    for dte in (14,30,45):
        expiry=f"2026-09-{min(28,10+dte//3):02d}T20:00:00+00:00"
        for kind in ("CALL","PUT"):
            for j in range(-10,11):
                strike=spot+j;delta=(.5-j*.04) if kind=="CALL" else (-.5-j*.04);mark=max(.15,3-abs(j)*.18+dte*.01);spread=max(.02,mark*.03)
                rows.append({"symbol":f"{underlying}{dte}{kind[0]}{strike:.0f}","description":"synthetic load-test contract","putCall":kind,"bid":mark-spread/2,"ask":mark+spread/2,"last":mark,"mark":mark,"bidSize":100,"askSize":100,"lastSize":1,"totalVolume":5000,"openInterest":5000,"volatility":25+abs(j)*.35+math.sin(step/7),"delta":delta,"gamma":.05,"theta":-.05,"vega":.1,"rho":.01,"strikePrice":strike,"daysToExpiration":dte,"expirationDate":expiry,"inTheMoney":j<0 if kind=="CALL" else j>0,"intrinsicValue":max(0,spot-strike) if kind=="CALL" else max(0,strike-spot),"timeValue":mark,"multiplier":100,"quoteTimeInLong":1786370400000+step*1000,"tradeTimeInLong":1786370400000+step*1000,"underlyingPrice":spot})
    return rows

def futures_roots(step,now):
    vals={"/MES":7777.,"/MNQ":29840.,"/MGC":4400.,"/MCL":77.,"/M6E":1.157}
    return {r:{"contractSymbol":f"{r}U26","root":r,"realtime":True,"bid":v*(1-.00005),"ask":v*(1+.00005),"last":v,"mark":v,"bidSize":10,"askSize":10,"quoteTime":int(now.timestamp()*1000),"tradeTime":int(now.timestamp()*1000),"openInterest":10000,"totalVolume":50000,"tick":.01,"tickAmount":1,"multiplier":5 if r=="/MES" else 2 if r=="/MNQ" else 10 if r=="/MGC" else 100 if r=="/MCL" else 12500,"expiration":1790000000000,"active":True} for r,v in vals.items()}

def curves(step,now):
    out={}
    for root,front,mult in (("/MES",7777,5),("/MNQ",29840,2),("/MCL",77,100),("/MGC",4400,10),("/M6E",1.157,12500)):
        rows=[]
        for i in range(3):
            mid=front*(1+i*.006)+math.sin(step/9)*front*.0001;spread=max(.0001,mid*.00005)
            rows.append({"symbol":f"{root}{'UZH'[i]}26","realtime":True,"bid":mid-spread/2,"ask":mid+spread/2,"quote_time_ms":int(now.timestamp()*1000),"multiplier":mult,"expiration_ms":int((now+timedelta(days=30+90*i)).timestamp()*1000),"active":i==0})
        out[root]=rows
    return out

def report(queue,family,modules,cycles,errors,latencies,started):
    queue.put({"family":family,"modules":modules,"cycles":cycles,"errors":errors,"wall_seconds":time.perf_counter()-started,"p95_ms":1000*p95(latencies),"max_ms":1000*max(latencies,default=0),"peak_rss_mb":rss_mb()})

def warm_steps(warm,prewarm_mode):
    """Return exhaustive history steps or one history-rich terminal snapshot."""
    return range(warm) if prewarm_mode=="replay" else (() if warm<=0 else (warm-1,))

def run_evaluators(strategies,builder,interval,duration,multiplier,warm,queue,family,prewarm_mode):
    errors=cycles=0;lat=[];started=time.perf_counter();now=datetime(2026,8,10,14,30,tzinfo=timezone.utc)
    for step in warm_steps(warm,prewarm_mode):
        snap=builder(step,now+timedelta(seconds=step))
        for strategy in strategies:
            try:strategy.evaluate(snap)
            except Exception:errors+=1
    deadline=time.perf_counter();end=deadline+duration;step=warm
    while time.perf_counter()<end:
        if time.perf_counter()<deadline:time.sleep(min(.01,deadline-time.perf_counter()));continue
        t=time.perf_counter();snap=builder(step,now+timedelta(seconds=step))
        for strategy in strategies:
            try:strategy.evaluate(snap)
            except Exception:errors+=1
        lat.append(time.perf_counter()-t);cycles+=1;step+=1;deadline+=interval/multiplier
    report(queue,family,len(strategies),cycles,errors,lat,started)

def family_entry(family,multiplier,duration,count,temp,queue,prewarm_mode="snapshot"):
    sys.addaudithook(deny_external);os.environ["LIVE_ORDER_PLACEMENT_ENABLED"]="0";os.environ["RUN_MODE"]="REPLAY"
    try:
        if family=="collector":
            from market_quotes import extract_quote_snapshot
            from quote_source import _merge_minute_cache,_parse_quote_bytes,_to_minute_cache
            tape=Path(temp)/"collector.csv";tape.write_text("timestamp_utc,symbol,last_price\n");cache=None;started=time.perf_counter();deadline=started;end=started+duration;lat=[];cycles=errors=0
            while time.perf_counter()<end:
                if time.perf_counter()<deadline:time.sleep(min(.005,deadline-time.perf_counter()));continue
                t=time.perf_counter();now=datetime(2026,8,10,14,tzinfo=timezone.utc)+timedelta(seconds=cycles);qs=equity_quotes(symbols(count),cycles,now);snapshots={s:extract_quote_snapshot(s,{"realtime":True,"quote":{"lastPrice":q["last"],"mark":q["mark"],"bidPrice":q["bid"],"askPrice":q["ask"],"bidSize":q["bidSize"],"askSize":q["askSize"],"quoteTime":q["quoteTime"],"tradeTime":q["tradeTime"]}}) for s,q in qs.items()};text="".join(f"{now.isoformat()},{s},{q.legacy_price}\n" for s,q in snapshots.items());tape.open("a").write(text);cache=_merge_minute_cache(cache,_to_minute_cache(_parse_quote_bytes(text.encode())));lat.append(time.perf_counter()-t);cycles+=1;deadline+=1/multiplier
            report(queue,family,1,cycles,errors,lat,started);return
        if family=="main":
            from engine.events import MarketSnapshot,Quote
            from strategies import registry
            from strategies.derived_runtime import derive_signals
            class D:
                def evaluated(self,*a,**k):pass
            registry.diagnostics=D();names=symbols(count);started=time.perf_counter();lat=[];errors=cycles=0;now=datetime(2026,8,10,14,30,tzinfo=timezone.utc)
            def minute(step):
                raw=equity_quotes(names,step,now+timedelta(minutes=step));q={s:Quote(x["last"],x["totalVolume"],x["bid"],x["ask"]) for s,x in raw.items()};return MarketSnapshot(now+timedelta(minutes=step),q,len(q),len(q),0,{"source":"full_load_test"})
            for i in warm_steps(75,prewarm_mode):
                _,errs=registry.on_minute_snapshot(minute(i));errors+=len(errs)
            event={"symbol":"SPY","timestamp":now.isoformat(),"setup_id":"load","strategy_id":"A","entry_price":100.,"target_price":102.,"stop_price":95.,"flash_drop_pct":2.,"original_flash_drop_pct":2.,"remaining_upside_pct":2.,"pre_return_pct":2.,"pre_r2":.9,"pre30_return_std_pct":.2,"flash_dollar_volume_3m":1000000,"flash_volume_ratio":2.,"rebound_volume_ratio":1.,"distance_below_rolling_vwap_pct":1.,"confirmation_wait_seconds":1.,"volume_data_status_flash":"OK","market_5m_return_pct":.1,"market_1m_return_pct":.1}
            deadline=time.perf_counter();end=deadline+duration;step=75
            while time.perf_counter()<end:
                if time.perf_counter()<deadline:time.sleep(min(.01,deadline-time.perf_counter()));continue
                t=time.perf_counter();_,errs=registry.on_minute_snapshot(minute(step));errors+=len(errs)
                for module in registry.FLASH_STRATEGY_MODULES.values():
                    try:module.accepts_flash(event,12.)
                    except Exception:errors+=1
                for parent in ("A","B","D"):
                    try:derive_signals({**event,"strategy_id":parent})
                    except Exception:errors+=1
                lat.append(time.perf_counter()-t);cycles+=1;step+=1;deadline+=5/multiplier
            report(queue,family,len(registry.MINUTE_STRATEGIES)+len(registry.FLASH_STRATEGY_MODULES)+32,cycles,errors,lat,started);return
        if family=="xs":
            import numpy as np,pandas as pd
            from research_lab.xs_executor import XSSharedRuntime
            from research_lab.xs_shadows import ready_shadow_specs
            specs=ready_shadow_specs();runtime=XSSharedRuntime(specs);cols=symbols(min(count,300));idx=pd.date_range("2026-08-10 13:30",periods=76,freq="min",tz="UTC");wide=pd.DataFrame(100*np.cumprod(1+np.random.default_rng(1).normal(0,.001,(76,len(cols))),axis=0),index=idx,columns=cols)
            class X:
                def evaluate(self,snapshot):return runtime.update(snapshot)
            run_evaluators([X()],lambda step,now:wide*(1+step*1e-6),60,duration,multiplier,0,queue,family,prewarm_mode);return
        if family=="options":
            import options_shadow_worker as w
            ss=w._load_strategies();run_evaluators(ss,lambda step,now:{"timestamp":now.isoformat(),"underlying":"SPY","underlyingPrice":100.,"isDelayed":False,"status":"SUCCESS","contracts":option_contracts("SPY",step)},120,duration,multiplier,12,queue,family,prewarm_mode);return
        if family=="options_rv":
            import options_rv_shadow_worker as w
            mods=w.load_strategies()
            class W:
                def __init__(self,m):self.m=m
                def evaluate(self,snap):return self.m.evaluate("SPY",snap["contracts"],snap["timestamp"])
            ss=[W(m) for m in mods];run_evaluators(ss,lambda step,now:{"timestamp":now,"contracts":option_contracts("SPY",step)},300,duration,multiplier,12,queue,family,prewarm_mode);return
        if family=="futures":
            import futures_shadow_worker as w
            ss=w.load_strategies();run_evaluators(ss,lambda step,now:{"timestamp":now,"roots":futures_roots(step,now)},60,duration,multiplier,20,queue,family,prewarm_mode);return
        if family=="futures_curve":
            import futures_curve_shadow_worker as w
            ss=w.load_strategies();run_evaluators(ss,lambda step,now:{"timestamp":now,"curves":curves(step,now)},300,duration,multiplier,20,queue,family,prewarm_mode);return
        if family=="forex":
            import forex_shadow_worker as w
            ss=w.load_strategies();run_evaluators(ss,lambda step,now:{"timestamp":now,"pairs":equity_quotes(w.PAIRS,step,now)},60,duration,multiplier,75,queue,family,prewarm_mode);return
        module=__import__(f"{family}_shadow_worker")
        ss=module.load_strategies();names=getattr(module,"SYMBOLS",symbols(min(count,1500)))
        if family=="swing":
            history={s:[((datetime(2026,6,1,tzinfo=timezone.utc)+timedelta(days=i)).date().isoformat(),100+i*.2+math.sin(i/3)) for i in range(45)] for s in names}
            builder=lambda step,now:{"timestamp":now,"completed_daily_history":history,"quotes":equity_quotes(names,step,now)};interval=300;warm=2
        else:
            builder=lambda step,now:{"timestamp":now,"quotes":equity_quotes(names,step,now)};interval=5 if family=="microstructure" else 60;warm=75
        run_evaluators(ss,builder,interval,duration,multiplier,warm,queue,family,prewarm_mode)
    except Exception as exc:
        queue.put({"family":family,"modules":0,"cycles":0,"errors":1,"fatal":f"{type(exc).__name__}: {exc}","peak_rss_mb":rss_mb()})

def mem_available_mb():
    for line in Path("/proc/meminfo").read_text().splitlines():
        if line.startswith("MemAvailable:"):return int(line.split()[1])/1024
    return 0

def main(argv=None):
    ap=argparse.ArgumentParser();ap.add_argument("--symbols",type=int,default=2700);ap.add_argument("--duration",type=float,default=80,help="seconds per multiplier stage; 80 gives about five minutes total");ap.add_argument("--multipliers",default="1,2,4");ap.add_argument("--prewarm-mode",choices=("snapshot","replay"),default="snapshot",help="snapshot is the five-minute steady-state test; replay exhaustively rebuilds sequential history");ap.add_argument("--min-memory-mb",type=float,default=1024);ap.add_argument("--output",default="/tmp/full_system_load_test_report.json");args=ap.parse_args(argv);all_results=[]
    for mult in [int(x) for x in args.multipliers.split(",")]:
        temp=tempfile.mkdtemp(prefix=f"full-load-{mult}x-",dir="/tmp");queue=mp.Queue();processes=[mp.Process(target=family_entry,args=(f,mult,args.duration,args.symbols,temp,queue,args.prewarm_mode),name=f"full-{f}") for f in FAMILIES];started=time.perf_counter();before=mem_available_mb()
        print(f"FULL STAGE {mult}x families={len(processes)} memory_available={before:.0f}MiB",flush=True)
        for p in processes:p.start()
        aborted=None
        while any(p.is_alive() for p in processes):
            available=mem_available_mb()
            if available<args.min_memory_mb:
                aborted=f"memory {available:.0f}MiB below {args.min_memory_mb:.0f}MiB"
                for p in processes:
                    if p.is_alive():p.terminate()
                break
            time.sleep(.25)
        for p in processes:p.join(2)
        rows=[]
        for _ in processes:
            try:rows.append(queue.get(timeout=.3))
            except Exception:break
        result={"multiplier":mult,"wall_seconds":time.perf_counter()-started,"memory_available_before_mb":before,"memory_available_after_mb":mem_available_mb(),"aborted":aborted,"families":sorted(rows,key=lambda x:x["family"]),"modules_exercised":sum(x.get("modules",0) for x in rows),"errors":sum(x.get("errors",0) for x in rows)};all_results.append(result)
        print(f"  modules={result['modules_exercised']} errors={result['errors']} memory_after={result['memory_available_after_mb']:.0f}MiB aborted={aborted}",flush=True)
        import shutil;shutil.rmtree(temp,ignore_errors=True)
        if aborted:break
    report={"role":"FULL_OFFLINE_REPLAY_NOT_TRADING_EVIDENCE","generated_at":datetime.now(timezone.utc).isoformat(),"prewarm_mode":args.prewarm_mode,"stages":all_results,"guards":{"network":"audit denied","data_writes":"audit denied","broker_execution":"environment disabled"},"limitations":["synthetic snapshots rather than Schwab network responses","snapshot prewarm does not reconstruct every stateful rolling window sequentially","orchestration and paper-ledger I/O are not exact for every isolated worker"]};Path(args.output).write_text(json.dumps(report,indent=2,sort_keys=True)+"\n");print(f"REPORT {args.output}",flush=True);return 2 if any(x["aborted"] or x["errors"] for x in all_results) else 0

if __name__=="__main__":raise SystemExit(main())
