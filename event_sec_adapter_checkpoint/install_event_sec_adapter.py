from pathlib import Path
import shutil
HERE=Path(__file__).resolve().parent;ROOT=HERE.parent
shutil.copy2(HERE/"sec_event_adapter.py",ROOT/"sec_event_adapter.py")
for name in ("strategy_evtsec8k1.py","strategy_evtvol1.py"):shutil.copy2(HERE/"event_strategies"/name,ROOT/"event_strategies"/name)
worker=ROOT/"event_shadow_worker.py";s=worker.read_text()
old='    strategies=load_strategies();tracker=EventPaperTracker(DATA_ROOT);handled=set();errors=decisions=0'
new='    strategies=load_strategies();tracker=EventPaperTracker(DATA_ROOT);handled=set();baselines={};errors=decisions=0'
if old in s:s=s.replace(old,new,1)
elif new not in s:raise SystemExit("event worker initialization anchor missing")
old='''        if regular(now):
            for e in events:
                if e["event_id"] in handled or e["symbol"] not in qs:continue
                for strategy in strategies:
                    try:
                        for d in strategy.evaluate(e,qs[e["symbol"]]):decisions+=int(tracker.register(d))
                    except Exception:errors+=1
                handled.add(e["event_id"])
'''
new='''        if regular(now):
            for e in events:
                if e["symbol"] not in qs:continue
                q=qs[e["symbol"]];mid=(float(q["bid"])+float(q["ask"]))/2
                baseline=baselines.setdefault(e["event_id"],{"timestamp":now,"mid":mid,"volume":float(q.get("totalVolume") or 0)})
                enriched=dict(e);enriched["reaction_minutes"]=(now-baseline["timestamp"]).total_seconds()/60;enriched["reaction_return"]=mid/baseline["mid"]-1;enriched["reaction_volume"]=max(0,float(q.get("totalVolume") or 0)-baseline["volume"])
                for strategy in strategies:
                    key=f"{strategy.name}:{e['event_id']}"
                    if key in handled:continue
                    try:
                        emitted=False
                        for d in strategy.evaluate(enriched,q):emitted=True;decisions+=int(tracker.register(d))
                        if emitted:handled.add(key)
                    except Exception:errors+=1
'''
if old in s:s=s.replace(old,new,1)
elif new not in s:raise SystemExit("event evaluation anchor missing")
worker.write_text(s)
docker=ROOT/"Dockerfile";s=docker.read_text();line="COPY sec_event_adapter.py ."
if line not in s:s=s.replace("COPY event_shadow_worker.py .","COPY event_shadow_worker.py .\n"+line,1)
docker.write_text(s)
sup=ROOT/"supervisor.py";s=sup.read_text();anchor='    "event_shadow": [sys.executable, "-u", "event_shadow_worker.py"],';line='    "sec_event_adapter": [sys.executable, "-u", "sec_event_adapter.py"],'
if line not in s:
    if anchor not in s:raise SystemExit("event supervisor anchor missing")
    s=s.replace(anchor,anchor+"\n"+line,1)
sup.write_text(s)
(ROOT/"tests").mkdir(exist_ok=True);shutil.copy2(HERE/"tests/test_event_sec_adapter.py",ROOT/"tests/test_event_sec_adapter.py")
print("INSTALLED official SEC event adapter and prospective reaction measurement")
