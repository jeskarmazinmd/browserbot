"""Safe, offline capacity test for browserbot.

Uses real quote normalization, minute-cache transforms and registered minute
strategy evaluation.  Isolated research-family work is conservatively emulated
in parallel because those workers normally require live APIs.  No token, broker,
network, /data write or order path is used.
"""
from __future__ import annotations

import argparse
import gzip
import json
import math
import multiprocessing as mp
import os
import shutil
import statistics
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path


FAMILIES=("xs","options","futures","forex","short","microstructure","crosssection","statarb")


class AbortTest(RuntimeError): pass


class NullDiagnostics:
    def evaluated(self,*_args,**_kwargs): pass


def percentile(values,p):
    if not values:return 0.0
    ordered=sorted(values);index=min(len(ordered)-1,max(0,math.ceil(p*len(ordered))-1))
    return ordered[index]


def mem_available_mb():
    for line in Path("/proc/meminfo").read_text().splitlines():
        if line.startswith("MemAvailable:"):return int(line.split()[1])/1024
    return 0.0


def proc_rss_mb(pid):
    try:
        for line in Path(f"/proc/{pid}/status").read_text().splitlines():
            if line.startswith("VmRSS:"):return int(line.split()[1])/1024
    except OSError:pass
    return 0.0


def worker_rss():
    result={}
    for child in Path("/proc").iterdir():
        if not child.name.isdigit():continue
        try:cmd=(child/"cmdline").read_bytes().replace(b"\0",b" ").decode()
        except OSError:continue
        if any(x in cmd for x in ("supervisor.py","live_quote_collector.py","live_strategy_runner.py","shadow_worker.py")):
            result[f"{child.name}:{Path(cmd.split()[-1]).name}"]=round(proc_rss_mb(int(child.name)),2)
    return result


def host_cpu():
    parts=Path("/proc/stat").read_text().splitlines()[0].split()[1:]
    nums=[int(x) for x in parts];return sum(nums),nums[3]+(nums[4] if len(nums)>4 else 0)


def cpu_pct(before,after):
    total=after[0]-before[0];idle=after[1]-before[1]
    return 0.0 if total<=0 else 100*(total-idle)/total


def directory_bytes(path):
    return sum(x.stat().st_size for x in path.rglob("*") if x.is_file())


def synthetic_payloads(count,step):
    now_ms=1786370400000+step*1000;result={}
    anchors=("SPY","QQQ","IWM")
    for i in range(count):
        symbol=anchors[i] if i<len(anchors) else f"Z{i:04d}"
        base=20+(i%400)*.37;move=math.sin((step+i%17)/31)*.002
        last=base*(1+move);spread=max(.01,last*.0004)
        result[symbol]={"symbol":symbol,"realtime":True,"quote":{
            "lastPrice":last,"mark":last,"bidPrice":last-spread/2,"askPrice":last+spread/2,
            "bidSize":100+i%40,"askSize":90+(i*3)%40,"lastSize":1+i%10,
            "quoteTime":now_ms,"tradeTime":now_ms}}
    return result


def collector_cycle(count,step,tape,rich,do_rich):
    from market_quotes import extract_quote_snapshot
    payloads=synthetic_payloads(count,step);snapshots={k:extract_quote_snapshot(k,v) for k,v in payloads.items()}
    ts=(datetime(2026,8,10,14,tzinfo=timezone.utc)+timedelta(seconds=step)).isoformat()
    lines="".join(f"{ts},{s},{q.legacy_price}\n" for s,q in snapshots.items() if q.legacy_price)
    with tape.open("a") as handle:handle.write(lines)
    if do_rich:
        with gzip.open(rich,"at") as handle:
            for q in snapshots.values():handle.write(json.dumps({"timestamp":ts,**q.as_dict()},separators=(",",":"))+"\n")
    return lines.encode(),snapshots


def snapshot_from_quotes(snapshots,when):
    from engine.events import MarketSnapshot,Quote
    quotes={s:Quote(price=q.legacy_price,bid=q.bid,ask=q.ask) for s,q in snapshots.items() if q.legacy_price}
    return MarketSnapshot(when,quotes,len(snapshots),len(quotes),0.0,{"source":"offline_load_test","cadence":"minute"})


def family_child(name,multiplier,duration,symbols,queue):
    import numpy as np
    rng=np.random.default_rng(abs(hash(name))%2**32);rows=300 if name in {"xs","statarb"} else min(symbols,1500)
    matrix=rng.normal(0,.001,(rows,75));interval=(1 if name in {"microstructure","crosssection"} else 5)/multiplier
    deadline=time.perf_counter();end=deadline+duration;ops=missed=0;lat=[]
    while time.perf_counter()<end:
        now=time.perf_counter()
        if now<deadline:time.sleep(min(.01,deadline-now));continue
        started=time.perf_counter()
        matrix[:,-1]=rng.normal(0,.001,rows)
        if name in {"xs","statarb"}:np.corrcoef(matrix[:120,-30:])
        elif name=="crosssection":np.argsort(matrix[:,-1])
        elif name=="microstructure":np.tanh(matrix[:,-20:]).sum(axis=1)
        else:np.quantile(matrix[-min(rows,300):,-30:],[.1,.5,.9],axis=0)
        elapsed=time.perf_counter()-started;lat.append(elapsed);ops+=1;deadline+=interval
        if elapsed>interval or time.perf_counter()>deadline+interval:missed+=1
    queue.put({"family":name,"operations":ops,"missed_deadlines":missed,"p95_ms":1000*percentile(lat,.95),"max_ms":1000*max(lat,default=0),"peak_rss_mb":proc_rss_mb(os.getpid())})


def safety(temp,min_memory_mb,max_temp_mb,max_load_per_cpu):
    available=mem_available_mb();used=directory_bytes(temp)/(1024**2);load=os.getloadavg()[0];cpus=os.cpu_count() or 1
    if available<min_memory_mb:raise AbortTest(f"memory available {available:.0f} MiB below {min_memory_mb}")
    if used>max_temp_mb:raise AbortTest(f"temporary output {used:.1f} MiB above {max_temp_mb}")
    if load>cpus*max_load_per_cpu:raise AbortTest(f"load average {load:.2f} above {cpus*max_load_per_cpu:.2f}")
    return available,used,load


def run_stage(multiplier,duration,symbols,temp,args,registry):
    from quote_source import _merge_minute_cache,_parse_quote_bytes,_to_minute_cache
    tape=temp/f"tape_{multiplier}x.csv";rich=temp/f"rich_{multiplier}x.jsonl.gz"
    tape.write_text("timestamp_utc,symbol,last_price\n")
    queue=mp.Queue();children=[mp.Process(target=family_child,args=(name,multiplier,duration,symbols,queue),name=f"load-{name}") for name in FAMILIES]
    cpu0=host_cpu();proc0=time.process_time();wall0=time.perf_counter();rss_peak=proc_rss_mb(os.getpid());worker_peak=worker_rss();collector_lat=[];strategy_lat=[];miss_col=miss_strat=0;step=0;next_col=wall0;next_strat=wall0;last_rich=-60;last_sample=wall0-1;aborted=None;latest_raw=b"";minute_cache=None
    for p in children:p.start()
    try:
        while time.perf_counter()-wall0<duration:
            now=time.perf_counter()
            if now>=next_col:
                started=time.perf_counter();latest_raw,snaps=collector_cycle(symbols,step,tape,rich,step-last_rich>=60);elapsed=time.perf_counter()-started;collector_lat.append(elapsed)
                if step-last_rich>=60:last_rich=step
                next_col+=1/multiplier;step+=1
                if elapsed>1/multiplier or now>next_col+1/multiplier:miss_col+=1
            if now>=next_strat:
                started=time.perf_counter();minute_cache=_merge_minute_cache(minute_cache,_to_minute_cache(_parse_quote_bytes(latest_raw)));when=datetime(2026,8,10,14,tzinfo=timezone.utc)+timedelta(minutes=len(strategy_lat));registry.on_minute_snapshot(snapshot_from_quotes(snaps,when));elapsed=time.perf_counter()-started;strategy_lat.append(elapsed);next_strat+=60/multiplier
                if elapsed>60/multiplier or now>next_strat+60/multiplier:miss_strat+=1
            if now-last_sample>=.5:
                safety(temp,args.min_memory_mb,args.max_temp_mb,args.max_load_per_cpu)
                rss_peak=max(rss_peak,proc_rss_mb(os.getpid()))
                for key,value in worker_rss().items():worker_peak[key]=max(worker_peak.get(key,0),value)
                last_sample=now
            time.sleep(.002)
    except AbortTest as exc:aborted=str(exc)
    finally:
        for p in children:
            p.join(timeout=2)
            if p.is_alive():p.terminate();p.join()
    family=[]
    for _ in children:
        try:family.append(queue.get(timeout=.2))
        except Exception:break
    wall=time.perf_counter()-wall0;cpu1=host_cpu();temp_mb=directory_bytes(temp)/(1024**2)
    return {"multiplier":multiplier,"wall_seconds":wall,"collector_cycles":len(collector_lat),"collector_p95_ms":1000*percentile(collector_lat,.95),"collector_max_ms":1000*max(collector_lat,default=0),"collector_missed_deadlines":miss_col,"minute_strategy_cycles":len(strategy_lat),"strategy_p95_ms":1000*percentile(strategy_lat,.95),"strategy_max_ms":1000*max(strategy_lat,default=0),"strategy_missed_deadlines":miss_strat,"host_cpu_pct":cpu_pct(cpu0,cpu1),"harness_cpu_core_pct":100*(time.process_time()-proc0)/max(wall,.001),"harness_peak_rss_mb":rss_peak,"production_worker_peak_rss_mb":worker_peak,"temp_output_mb_cumulative":temp_mb,"family_emulation":sorted(family,key=lambda x:x["family"]),"aborted":aborted}


def main(argv=None):
    ap=argparse.ArgumentParser();ap.add_argument("--symbols",type=int,default=2700);ap.add_argument("--duration",type=float,default=30);ap.add_argument("--multipliers",default="1,2,4,8");ap.add_argument("--min-memory-mb",type=float,default=1024);ap.add_argument("--max-temp-mb",type=float,default=256);ap.add_argument("--max-load-per-cpu",type=float,default=1.5);ap.add_argument("--output",default="/tmp/browserbot_load_test_report.json");args=ap.parse_args(argv)
    from strategies import registry
    registry.diagnostics=NullDiagnostics()
    temp=Path(tempfile.mkdtemp(prefix="browserbot-load-",dir="/tmp"));started=datetime.now(timezone.utc);results=[]
    print(f"LOAD TEST temp={temp} symbols={args.symbols} modules={len(registry.MINUTE_STRATEGIES)}",flush=True)
    # Explicitly measure the real 75-minute cold-start warm-up.
    payload=synthetic_payloads(args.symbols,0)
    from market_quotes import extract_quote_snapshot
    snaps={k:extract_quote_snapshot(k,v) for k,v in payload.items()};cold=[]
    for minute in range(75):
        t=time.perf_counter();registry.on_minute_snapshot(snapshot_from_quotes(snaps,datetime(2026,8,10,13,30,tzinfo=timezone.utc)+timedelta(minutes=minute)));cold.append(time.perf_counter()-t)
    print(f"COLD START 75 minutes total={sum(cold):.3f}s p95={1000*percentile(cold,.95):.1f}ms",flush=True)
    try:
        for multiplier in [int(x) for x in args.multipliers.split(",") if x.strip()]:
            print(f"STAGE {multiplier}x",flush=True);result=run_stage(multiplier,args.duration,args.symbols,temp,args,registry);results.append(result)
            print(f"  cpu={result['host_cpu_pct']:.1f}% collector_p95={result['collector_p95_ms']:.1f}ms strategy_p95={result['strategy_p95_ms']:.1f}ms missed={result['collector_missed_deadlines']+result['strategy_missed_deadlines']} temp={result['temp_output_mb_cumulative']:.1f}MiB",flush=True)
            if result["aborted"]:break
    finally:
        report={"role":"OFFLINE_CAPACITY_TEST_NOT_TRADING_EVIDENCE","started_at":started.isoformat(),"finished_at":datetime.now(timezone.utc).isoformat(),"symbols":args.symbols,"registered_minute_strategies":len(registry.MINUTE_STRATEGIES),"cold_start":{"minutes":75,"total_seconds":sum(cold),"p95_ms":1000*percentile(cold,.95),"max_ms":1000*max(cold)},"stages":results,"safety":{"minimum_available_memory_mb":args.min_memory_mb,"maximum_temporary_output_mb":args.max_temp_mb,"maximum_load_per_cpu":args.max_load_per_cpu},"limitations":["no Schwab network or rate-limit load","research-family processes are workload emulations","no broker, token, order, /data or production-ledger access"]}
        Path(args.output).write_text(json.dumps(report,indent=2,sort_keys=True)+"\n");shutil.rmtree(temp,ignore_errors=True)
        print(f"REPORT {args.output}",flush=True)
    return 2 if any(x.get("aborted") for x in results) else 0


if __name__=="__main__":raise SystemExit(main())
