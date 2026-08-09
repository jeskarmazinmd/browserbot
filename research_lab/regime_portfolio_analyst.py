"""Advisory-only, causally lagged regime portfolio analyst.

This command never edits strategy registries, changes worker configuration,
allocates capital, or places orders.  A regime recorded on market day D is
used only to characterize returns on a later market day.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime
from itertools import combinations
import json
import math
from pathlib import Path
from statistics import fmean,pstdev
from zoneinfo import ZoneInfo

NY=ZoneInfo("America/New_York")

def number(value):
    try:
        x=float(value)
        return x if math.isfinite(x) else None
    except (TypeError,ValueError):return None

def parse_time(value):
    try:
        x=datetime.fromisoformat(str(value).replace("Z","+00:00"))
        return x if x.tzinfo else x.replace(tzinfo=NY)
    except (TypeError,ValueError):return None

def load_capital(path):
    value=json.loads(Path(path).read_text())
    days=value.get("days",{}) if isinstance(value,dict) else {}
    result={}
    for day,modules in days.items():
        if not isinstance(modules,dict):continue
        clean={}
        for sid,row in modules.items():
            if not isinstance(row,dict):continue
            ret=number(row.get("return_pct"))
            if ret is None:
                end=number(row.get("end_equity"))
                ret=(end/5000-1)*100 if end is not None else None
            if ret is not None:clean[str(sid)]={"return_pct":ret,"signals":int(row.get("signals",0) or 0)}
        if clean:result[str(day)]=clean
    return result

def regime_label(row):
    labels=row.get("labels",{}) or {}
    trend=(row.get("trend",{}) or {}).get("classification","UNKNOWN")
    vol=(row.get("volatility",{}) or {}).get("classification","UNKNOWN")
    return "|".join(str(x or "UNKNOWN") for x in (labels.get("direction","UNKNOWN"),trend,vol,labels.get("breadth","UNKNOWN")))

def load_close_regimes(path):
    latest={}
    with Path(path).open(errors="replace") as handle:
        for line in handle:
            try:row=json.loads(line)
            except (TypeError,ValueError):continue
            stamp=parse_time(row.get("timestamp") or row.get("logged_at"))
            if stamp is None or (row.get("data_quality",{}) or {}).get("quality")!="GOOD":continue
            day=stamp.astimezone(NY).date().isoformat()
            if day not in latest or stamp>latest[day][0]:latest[day]=(stamp,regime_label(row))
    return {day:item[1] for day,item in latest.items()}

def lagged_regimes(days,close_regimes):
    """Map each evidence day to the last strictly earlier close regime."""
    known=sorted(close_regimes)
    out={}
    for day in sorted(days):
        prior=[x for x in known if x<day]
        if prior:out[day]=close_regimes[prior[-1]]
    return out

def compound(values):
    total=1.0
    for x in values:total*=1+x/100
    return (total-1)*100

def max_drawdown(values):
    equity=peak=1.0;worst=0.0
    for x in values:
        equity*=1+x/100;peak=max(peak,equity);worst=max(worst,(peak-equity)/peak*100)
    return worst

def correlation(left,right):
    if len(left)<2:return 0.0
    lm,rm=fmean(left),fmean(right);a=[x-lm for x in left];b=[x-rm for x in right]
    den=math.sqrt(sum(x*x for x in a)*sum(x*x for x in b))
    return sum(x*y for x,y in zip(a,b))/den if den else 0.0

def module_rows(capital,min_days=3,min_signals=20):
    modules=sorted({sid for rows in capital.values() for sid in rows})
    result={}
    for sid in modules:
        rows={day:items[sid] for day,items in capital.items() if sid in items}
        if len(rows)>=min_days and sum(x["signals"] for x in rows.values())>=min_signals:result[sid]=rows
    return result

def rank_baskets(capital,close_regimes,*,max_size=4,candidate_limit=20,min_days=3,min_signals=20,shrink_days=5):
    lagged=lagged_regimes(capital,close_regimes);eligible=module_rows(capital,min_days,min_signals)
    if not lagged or not eligible:return {"status":"INSUFFICIENT_EVIDENCE","reason":"no causally lagged regime/day evidence","recommendations":[]}
    target_day=max(close_regimes);target_regime=close_regimes[target_day]
    scored=[]
    for sid,rows in eligible.items():
        all_values=[rows[d]["return_pct"] for d in sorted(rows)]
        regime_values=[rows[d]["return_pct"] for d in sorted(rows) if lagged.get(d)==target_regime]
        weight=len(regime_values)/(len(regime_values)+shrink_days)
        estimate=weight*fmean(regime_values)+(1-weight)*fmean(all_values) if regime_values else fmean(all_values)
        scored.append((estimate,sid))
    candidates=[sid for _,sid in sorted(scored,reverse=True)[:candidate_limit]]
    results=[]
    for size in range(1,min(max_size,len(candidates))+1):
        for basket in combinations(candidates,size):
            common=sorted(set.intersection(*(set(eligible[s]) for s in basket)))
            if len(common)<min_days:continue
            daily=[fmean(eligible[s][d]["return_pct"] for s in basket) for d in common]
            regime_daily=[daily[i] for i,d in enumerate(common) if lagged.get(d)==target_regime]
            weight=len(regime_daily)/(len(regime_daily)+shrink_days)
            expected=weight*fmean(regime_daily)+(1-weight)*fmean(daily) if regime_daily else fmean(daily)
            pair_corr=[correlation([eligible[a][d]["return_pct"] for d in common],[eligible[b][d]["return_pct"] for d in common]) for a,b in combinations(basket,2)]
            avg_corr=fmean(pair_corr) if pair_corr else 0.0
            volatility=pstdev(daily) if len(daily)>1 else 0.0;dd=max_drawdown(daily)
            score=expected-.20*volatility-.10*dd-.10*max(0,avg_corr)
            results.append({"basket":list(basket),"score":score,"expected_daily_return_pct":expected,"compound_return_pct":compound(daily),"max_drawdown_pct":dd,"daily_volatility_pct":volatility,"average_pair_correlation":avg_corr,"common_days":len(common),"target_regime_days":len(regime_daily),"common_day_list":common})
    results.sort(key=lambda x:(-x["score"],len(x["basket"]),x["basket"]))
    status="ADVISORY_ONLY" if results else "INSUFFICIENT_EVIDENCE"
    return {"status":status,"target_regime":target_regime,"regime_observed_on":target_day,"causal_rule":"only regimes from strictly earlier market days score a return day","eligible_modules":len(eligible),"recommendations":results[:20]}

def render(report):
    print("HUMAN-CONTROLLED REGIME PORTFOLIO ANALYST")
    print("ADVISORY ONLY — no registry, allocation, or broker changes")
    print(f"status: {report['status']}")
    if report.get("reason"):print(f"reason: {report['reason']}");return
    print(f"target_regime: {report['target_regime']}")
    print(f"regime_observed_on: {report['regime_observed_on']}")
    print(f"eligible_modules: {report['eligible_modules']}")
    print("\nCANDIDATE PAPER BASKETS")
    for i,row in enumerate(report["recommendations"],1):
        print(f"{i:2}. {'+'.join(row['basket']):28} score={row['score']:+.3f} expected={row['expected_daily_return_pct']:+.3f}% compound={row['compound_return_pct']:+.2f}% dd={row['max_drawdown_pct']:.2f}% corr={row['average_pair_correlation']:+.2f} days={row['common_days']} regime_days={row['target_regime_days']}")

def main(argv=None):
    p=argparse.ArgumentParser();p.add_argument("--capital-history",default="/data/capital_constrained_history.json");p.add_argument("--regime-history",default="/data/regime_history.jsonl");p.add_argument("--max-size",type=int,default=4);p.add_argument("--candidate-limit",type=int,default=20);p.add_argument("--min-days",type=int,default=3);p.add_argument("--min-signals",type=int,default=20);p.add_argument("--json-output");args=p.parse_args(argv)
    report=rank_baskets(load_capital(args.capital_history),load_close_regimes(args.regime_history),max_size=args.max_size,candidate_limit=args.candidate_limit,min_days=args.min_days,min_signals=args.min_signals)
    render(report)
    if args.json_output:Path(args.json_output).write_text(json.dumps(report,indent=2,sort_keys=True)+"\n")
    return 0

if __name__=="__main__":raise SystemExit(main())
