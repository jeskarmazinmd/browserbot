"""Read-only prospective event router. It never invents or backdates events."""
from __future__ import annotations
import importlib,json,os,time,urllib.parse,urllib.request
from datetime import datetime,timezone,time as clock_time
from pathlib import Path
from zoneinfo import ZoneInfo
from event_paper_tracker import EventPaperTracker
NY=ZoneInfo("America/New_York");DATA_ROOT=Path(os.getenv("EVENT_DATA_ROOT","/data"));FEED=Path(os.getenv("EVENT_FEED_PATH",str(DATA_ROOT/"event_feed.jsonl")));TOKEN=Path("/data/schwab_token.json");URL="https://api.schwabapi.com/marketdata/v1/quotes";POLL=int(os.getenv("EVENT_POLL_SECONDS","60"));MAX_AGE=int(os.getenv("EVENT_MAX_AGE_SECONDS","86400"))
# EVTSEC8K1 and EVTVOL1 disabled after persistently negative forward results.
STRATEGIES=("EVTEARNUP1","EVTEARNDN1","EVTGUIDUP1","EVTGUIDDN1","EVTANALYST1","EVTMACRO1")
STRATEGIES+=("EVTSEC8K1","EVTSEC8K1INV","EVTVOL1","EVTVOL1INV")
REQUIRED=("event_id","published_at","observed_at","symbol","event_type","direction","source","source_url")
def regular(now):
    x=now.astimezone(NY);return x.weekday()<5 and clock_time(9,30)<=x.time()<clock_time(16,0)
def validate(row,now):
    missing=[k for k in REQUIRED if not row.get(k)]
    if missing:return False,"missing:"+",".join(missing)
    try:p=datetime.fromisoformat(row["published_at"]);o=datetime.fromisoformat(row["observed_at"])
    except Exception:return False,"invalid_timestamp"
    if p.tzinfo is None or o.tzinfo is None:return False,"naive_timestamp"
    if p>o or o>now:return False,"causality_violation"
    if (now-o).total_seconds()>MAX_AGE:return False,"stale"
    if not str(row["source_url"]).startswith("https://"):return False,"unverifiable_source"
    return True,"ok"
def load_events(now):
    accepted=[];rejected=[]
    if not FEED.exists():return accepted,rejected
    for line_no,line in enumerate(FEED.read_text().splitlines(),1):
        try:row=json.loads(line);ok,reason=validate(row,now)
        except Exception:ok,reason=False,"invalid_json";row={}
        (accepted if ok else rejected).append(row if ok else {"line":line_no,"reason":reason})
    return accepted,rejected
def token():
    x=json.loads(TOKEN.read_text());return x.get("token",x)["access_token"]
def quotes(symbols):
    if not symbols:return {}
    url=URL+"?"+urllib.parse.urlencode({"symbols":",".join(sorted(symbols))});request=urllib.request.Request(url,headers={"Authorization":f"Bearer {token()}","Accept":"application/json"})
    with urllib.request.urlopen(request,timeout=20) as response: payload=json.loads(response.read())
    out={}
    for symbol,p in payload.items():
        q=p.get("quote") or {};out[symbol]={"symbol":symbol,"bid":q.get("bidPrice"),"ask":q.get("askPrice"),"last":q.get("lastPrice"),"totalVolume":q.get("totalVolume"),"quoteTime":q.get("quoteTime"),"realtime":p.get("realtime") is True}
    return {s:q for s,q in out.items() if q["realtime"] and float(q.get("bid") or 0)>0 and float(q.get("ask") or 0)>=float(q.get("bid") or 0)}
def load_strategies():
    result=[]
    for sid in STRATEGIES:
        m=importlib.import_module(f"event_strategies.strategy_{sid.lower()}");assert m.PAPER_ONLY is True and m.LIVE_ORDER_PLACEMENT is False;result.append(m.Strategy())
    return result
def status(payload):
    p=DATA_ROOT/"event_shadow_status.json";tmp=p.with_suffix(".tmp");tmp.write_text(json.dumps(payload,separators=(",",":"))+"\n");os.replace(tmp,p)
def main():
    strategies=load_strategies();tracker=EventPaperTracker(DATA_ROOT);handled=set();baselines={};errors=decisions=0
    while True:
        now=datetime.now(timezone.utc);events,rejected=load_events(now);symbols={e["symbol"] for e in events};qs={}
        try:qs=quotes(symbols) if regular(now) else {};tracker.update(now,qs)
        except Exception:errors+=1
        if regular(now):
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
        state="WAITING_EVENT_FEED" if not FEED.exists() else "WAITING_VALID_EVENTS" if not events else "RUNNING" if regular(now) else "WAITING_REGULAR_MARKET"
        status({"updated_at":now.isoformat(),"status":state,"strategies":len(strategies),"feed_path":str(FEED),"valid_events":len(events),"rejected_events":len(rejected),"rejection_sample":rejected[:5],"fresh_symbols":len(qs),"decisions":decisions,"errors":errors,"broker_execution_enabled":False,"causal_event_validation":True});time.sleep(POLL)
if __name__=="__main__":main()
