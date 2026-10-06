"""Reconcile retained main fills to the exact finite-capital reporting model."""
import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from reporting.capital_performance import simulate_day
from research_tools.g3_review.analyze import write_csv,stamp

def run(data,out):
    entries,exits={},{}
    invalid=[]
    path=data/'paper_signal_v4_bidask_independent_outcomes.jsonl'
    with path.open() as f:
        for i,line in enumerate(f,1):
            try:r=json.loads(line)
            except ValueError:
                invalid.append({'line':i,'bytes':len(line.encode()),'nul_prefix':len(line)-len(line.lstrip('\x00'))});continue
            sid,setup=r.get('strategy_id'),r.get('setup_id')
            if not sid or not setup:continue
            if r.get('event_type')=='PAPER_ENTRY':entries[(sid,setup)]=r
            elif r.get('event_type')=='PAPER_EXIT':exits[(sid,setup)]=r
    grouped=defaultdict(list);unclosed=[]
    for key,e in entries.items():
        x=exits.get(key);ts=stamp(e.get('entry_timestamp') or e.get('signal_timestamp'))
        if not x or not ts:unclosed.append(key);continue
        day=stamp(e['signal_timestamp']).astimezone(ZoneInfo('America/New_York')).date().isoformat()
        grouped[(key[0]+'BA',day)].append({**e,'exit_timestamp':x['exit_timestamp'],'exit_price':x['exit_price']})
    h=json.loads((data/'all_engine_bidask_daily_history.json').read_text())['days']
    rows=[]
    for (sid,day),trades in sorted(grouped.items()):
        modeled=simulate_day(trades)
        recorded=h.get(day,{}).get('modules',{}).get(sid)
        rows.append({'module':sid,'day':day,'retained_entries':len(trades),'simulated_taken':modeled['taken'],
                     'simulated_return_pct':modeled['return_pct'],
                     'recorded_return_pct':recorded['return_pct'] if recorded else None,
                     'difference_pct':modeled['return_pct']-recorded['return_pct'] if recorded else None,
                     'match_1e_6':abs(modeled['return_pct']-recorded['return_pct'])<1e-6 if recorded else None})
    write_csv(out/'main_history_reconciliation.csv',rows)
    (out/'main_ledger_integrity.json').write_text(json.dumps({'invalid_lines':invalid,'unclosed_retained_setups':unclosed,
        'entries':len(entries),'exits':len(exits),'row_matches':sum(r['match_1e_6'] is True for r in rows),
        'row_mismatches':sum(r['match_1e_6'] is False for r in rows),
        'limitations':'Retained fills only; historical cutoff or code changes and deleted/malformed rows can cause discrepancies. No source records changed.'},indent=2))

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--data',required=True,type=Path);p.add_argument('--out',required=True,type=Path)
    a=p.parse_args();run(a.data,a.out)
