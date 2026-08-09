"""Official SEC current-filings adapter. Writes provenance-only causal events."""
from __future__ import annotations
import hashlib,json,os,re,time,urllib.parse,urllib.request,xml.etree.ElementTree as ET
from datetime import datetime,timezone
from pathlib import Path
DATA_ROOT=Path(os.getenv("EVENT_DATA_ROOT","/data"));FEED=Path(os.getenv("EVENT_FEED_PATH",str(DATA_ROOT/"event_feed.jsonl")));STATUS=DATA_ROOT/"sec_event_adapter_status.json"
USER_AGENT=os.getenv("SEC_USER_AGENT","").strip();POLL=max(30,int(os.getenv("SEC_EVENT_POLL_SECONDS","60")))
ATOM="https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent&type=8-k&company=&dateb=&owner=include&start=0&count=100&output=atom"
TICKERS="https://www.sec.gov/files/company_tickers.json";NS={"a":"http://www.w3.org/2005/Atom"}
def _get(url):
    if not USER_AGENT:raise RuntimeError("SEC_USER_AGENT is required (app name plus contact email)")
    req=urllib.request.Request(url,headers={"User-Agent":USER_AGENT,"Accept-Encoding":"identity","Accept":"application/atom+xml,application/json"})
    with urllib.request.urlopen(req,timeout=30) as r:return r.read()
def ticker_map():
    data=json.loads(_get(TICKERS));return {str(v["cik_str"]):v["ticker"].upper() for v in data.values()}
def parse_atom(raw,ciks,observed):
    root=ET.fromstring(raw);rows=[]
    for entry in root.findall("a:entry",NS):
        title=(entry.findtext("a:title",default="",namespaces=NS) or "").strip();updated=entry.findtext("a:updated",default="",namespaces=NS);link=entry.find("a:link",NS);url=(link.get("href") if link is not None else "")
        summary=entry.findtext("a:summary",default="",namespaces=NS) or "";cik=""
        for candidate in re.findall(r"(?<!\d)(\d{1,10})(?!\d)",title+" "+summary+" "+url):
            candidate=candidate.lstrip("0") or "0"
            if candidate in ciks:cik=candidate;break
        symbol=ciks.get(cik)
        if not symbol or not updated or not url.startswith("https://www.sec.gov/"):continue
        event_id="sec-"+hashlib.sha256(url.encode()).hexdigest()[:24]
        rows.append({"event_id":event_id,"published_at":updated,"observed_at":observed.isoformat(),"symbol":symbol,"event_type":"SEC_8K","direction":"UNKNOWN","magnitude":0.0,"source":"SEC_EDGAR_CURRENT_FILINGS","source_url":url,"form":"8-K","cik":cik})
    return rows
def existing_ids():
    if not FEED.exists():return set()
    out=set()
    for line in FEED.read_text().splitlines():
        try:out.add(json.loads(line)["event_id"])
        except Exception:pass
    return out
def atomic_status(x):
    STATUS.parent.mkdir(parents=True,exist_ok=True);tmp=STATUS.with_suffix(".tmp");tmp.write_text(json.dumps(x,separators=(",",":"))+"\n");os.replace(tmp,STATUS)
def cycle():
    now=datetime.now(timezone.utc);ciks=ticker_map();rows=parse_atom(_get(ATOM),ciks,now);known=existing_ids();new=[x for x in rows if x["event_id"] not in known];FEED.parent.mkdir(parents=True,exist_ok=True)
    if new:
        with FEED.open("a") as f:
            for row in new:f.write(json.dumps(row,separators=(",",":"))+"\n")
    atomic_status({"updated_at":now.isoformat(),"status":"RUNNING","official_source":"SEC_EDGAR","fetched":len(rows),"appended":len(new),"feed_path":str(FEED),"direction_inferred":False,"broker_execution_enabled":False});return len(new)
def main():
    while True:
        try:cycle()
        except Exception as e:atomic_status({"updated_at":datetime.now(timezone.utc).isoformat(),"status":"WAITING_CONFIGURATION" if not USER_AGENT else "ERROR_BACKOFF","error":f"{type(e).__name__}: {e}","broker_execution_enabled":False})
        time.sleep(POLL)
if __name__=="__main__":main()
