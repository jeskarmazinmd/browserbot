"""Independent, advisory-only shared-capital prospective basket tracker."""
from __future__ import annotations
import argparse,gzip,heapq,json,math
from collections import defaultdict
from datetime import datetime,timezone
from pathlib import Path
from statistics import median
from zoneinfo import ZoneInfo

NY=ZoneInfo("America/New_York")
DEFAULT_START="2026-08-10T13:30:00+00:00"
DEFAULT_BASKETS=("C2+P","C2+C1+P")

def timestamp(value):
    try:
        x=datetime.fromisoformat(str(value).replace("Z","+00:00"))
        return x if x.tzinfo else x.replace(tzinfo=timezone.utc)
    except (TypeError,ValueError):return None

def effective_entry(row):
    if "entry_timestamp" in row:return timestamp(row.get("entry_timestamp"))
    if row.get("exit_model")=="second_leg":return timestamp(row.get("second_leg_entry_time"))
    return timestamp(row.get("signal_timestamp"))

def compact(row,sequence=None):
    result={key:row.get(key) for key in ("setup_id","strategy_id","signal_timestamp","entry_price","stop_price","exit_timestamp","exit_price","entry_timestamp","second_leg_entry_time","exit_model","entered") if key in row}
    result["entry_sequence"]=row.get("entry_sequence",sequence)
    return result

def load_archive(path):
    rows=[]
    with gzip.open(path,"rt",errors="replace") as handle:
        for line in handle:
            try:row=json.loads(line)
            except (TypeError,ValueError):continue
            if row.get("event_type")=="PAPER_EXIT" and row.get("entry_sequence") is not None:rows.append(compact(row))
    return rows

def load_live(path):
    order={};rows=[]
    try:handle=Path(path).open(errors="replace")
    except OSError:return rows
    with handle:
        for line in handle:
            try:row=json.loads(line)
            except (TypeError,ValueError):continue
            setup=str(row.get("setup_id") or "")
            if row.get("event_type")=="PAPER_ENTRY" and setup and setup not in order:order[setup]=len(order)
            elif row.get("event_type")=="PAPER_EXIT" and setup in order:rows.append(compact(row,order[setup]))
    return rows

def load_completed(data_root):
    root=Path(data_root);rows=[]
    for path in sorted((root/"archive").glob("paper_trades.*.jsonl.gz")):rows.extend(load_archive(path))
    rows.extend(load_live(root/"paper_signal_outcomes.jsonl"))
    unique={}
    for row in rows:
        setup=str(row.get("setup_id") or "")
        if setup:unique[setup]=row
    return list(unique.values())

def prepare(rows,members,forward_start):
    start=timestamp(forward_start);prepared=[]
    for fallback,row in enumerate(rows):
        if str(row.get("strategy_id")) not in members:continue
        entry=effective_entry(row);exit_time=timestamp(row.get("exit_timestamp"))
        try:entry_price=float(row["entry_price"]);exit_price=float(row["exit_price"]);stop=float(row["stop_price"])
        except (KeyError,TypeError,ValueError):continue
        if entry is None or exit_time is None or entry<start or entry_price<=0 or exit_price<=0 or exit_time<entry:continue
        sequence=row.get("entry_sequence");sequence=fallback if sequence is None else int(sequence)
        prepared.append((entry,sequence,str(row.get("setup_id") or ""),exit_time,entry_price,exit_price,stop,str(row.get("strategy_id"))))
    return sorted(prepared,key=lambda x:(x[0],x[1],x[2]))

def simulate(rows,members,forward_start=DEFAULT_START,starting_cash=5000.,risk_fraction=.01,max_position_fraction=.20):
    prepared=prepare(rows,set(members),forward_start);cash=float(starting_cash);deployed=0.;active=[];taken=defaultdict(int);skipped=defaultdict(int);holds=[];peak=starting_cash;max_dd=0.;peak_deployed=0.;max_positions=0
    def equity_record():
        nonlocal peak,max_dd
        equity=cash+deployed;peak=max(peak,equity);max_dd=max(max_dd,(peak-equity)/peak*100 if peak else 0)
    def release(until):
        nonlocal cash,deployed
        while active and active[0][0]<=until:
            _,_,shares,entry,exit_price,_=heapq.heappop(active);cash+=shares*exit_price;deployed-=shares*entry;equity_record()
    for order,item in enumerate(prepared):
        entry_time,_,_,exit_time,entry,exit_price,stop,strategy=item;release(entry_time);equity=cash+deployed;risk=abs(entry-stop)
        shares=min(math.floor(equity*risk_fraction/risk) if risk>0 else 0,math.floor(equity*max_position_fraction/entry),math.floor(cash/entry))
        if shares<1:skipped[strategy]+=1;continue
        cost=shares*entry;cash-=cost;deployed+=cost;taken[strategy]+=1;holds.append((exit_time-entry_time).total_seconds());heapq.heappush(active,(exit_time,order,shares,entry,exit_price,strategy));peak_deployed=max(peak_deployed,deployed);max_positions=max(max_positions,len(active));equity_record()
    if prepared:release(datetime.max.replace(tzinfo=prepared[0][0].tzinfo))
    end=cash+deployed
    return {"members":sorted(members),"signals":len(prepared),"taken":sum(taken.values()),"skipped":sum(skipped.values()),"taken_by_strategy":dict(sorted(taken.items())),"skipped_by_strategy":dict(sorted(skipped.items())),"end_equity":end,"return_pct":(end/starting_cash-1)*100,"max_drawdown_pct":max_dd,"peak_deployed":peak_deployed,"max_positions":max_positions,"median_hold_seconds":median(holds) if holds else 0.}

def market_day(row):
    entry=effective_entry(row)
    return entry.astimezone(NY).date().isoformat() if entry else None

def compound(values):
    x=1.
    for value in values:x*=1+value/100
    return (x-1)*100

def analyze(rows,baskets,forward_start=DEFAULT_START):
    by_day=defaultdict(list)
    for row in rows:
        day=market_day(row)
        if day:by_day[day].append(row)
    reports=[]
    for members in baskets:
        daily=[]
        for day in sorted(by_day):
            result=simulate(by_day[day],members,forward_start); 
            if result["signals"]:daily.append({"day":day,**result})
        member_totals={m:simulate(rows,[m],forward_start) for m in members}
        reports.append({"basket":"+".join(members),"members":list(members),"forward_start":forward_start,"days":daily,"completed_days":len(daily),"compound_return_pct":compound(x["return_pct"] for x in daily),"member_comparators":member_totals,"role":"ADVISORY_SHARED_CAPITAL_PAPER_EVIDENCE"})
    return reports

def parse_baskets(values):
    return [tuple(x.strip() for x in value.split("+") if x.strip()) for value in values]

def status(data_root):
    try:return json.loads((Path(data_root)/"paper_signal_status.json").read_text())
    except (OSError,ValueError,TypeError):return {}

def render(reports,tracker_status):
    print("PROSPECTIVE SHARED-$5,000 BASKET TRACKER")
    print("ADVISORY ONLY — no broker, registry, or capital-allocation changes")
    print(f"paper_active: {tracker_status.get('active','UNKNOWN')}")
    for report in reports:
        print(f"\n{report['basket']} start={report['forward_start']} days={report['completed_days']} compound={report['compound_return_pct']:+.3f}%")
        for row in report["days"]:print(f"  {row['day']} return={row['return_pct']:+.3f}% end=${row['end_equity']:.2f} signals={row['signals']} taken={row['taken']} skipped={row['skipped']} dd={row['max_drawdown_pct']:.3f}%")
        print("  members:",", ".join(f"{m}={x['return_pct']:+.3f}%" for m,x in report["member_comparators"].items()))

def main(argv=None):
    p=argparse.ArgumentParser();p.add_argument("--data-root",default="/data");p.add_argument("--basket",action="append",default=[]);p.add_argument("--forward-start",default=DEFAULT_START);p.add_argument("--json-output");args=p.parse_args(argv)
    baskets=parse_baskets(args.basket or DEFAULT_BASKETS);rows=load_completed(args.data_root);reports=analyze(rows,baskets,args.forward_start);tracker_status=status(args.data_root);render(reports,tracker_status)
    if args.json_output:Path(args.json_output).write_text(json.dumps({"generated_at":datetime.now(timezone.utc).isoformat(),"paper_status":tracker_status,"reports":reports},indent=2,sort_keys=True)+"\n")
    return 0
if __name__=="__main__":raise SystemExit(main())
