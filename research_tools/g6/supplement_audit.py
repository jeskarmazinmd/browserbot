"""Main-engine daily capital sensitivity and native hedge evidence limitations."""
from collections import defaultdict,Counter
from pathlib import Path
import json,statistics
from datetime import datetime
from zoneinfo import ZoneInfo
from reporting.capital_performance import simulate_day

def supplement(evidence,result):
 root=Path(evidence)/'data';wanted=set(result['modules']);groups=defaultdict(list);skipped=Counter()
 for line in (root/'paper_signal_v4_bidask_independent_outcomes.jsonl').open():
  try:r=json.loads(line)
  except ValueError:continue
  sid=r.get('strategy_id')
  if sid not in wanted or r.get('event_type')!='PAPER_EXIT':continue
  if not r.get('entry_timestamp') or not r.get('exit_timestamp'):skipped[sid]+=1;continue
  day=datetime.fromisoformat(r['entry_timestamp']).astimezone(ZoneInfo('America/New_York')).date().isoformat()
  groups[(sid,day)].append(r)
 for sid in wanted:
  daily={d:simulate_day(rows) for (s,d),rows in groups.items() if s==sid}
  if daily:result['modules'][sid]['main_capital_replay_by_day']=daily
 ts=[];opens={};errs=Counter()
 for line in (root/'statarb_paper_outcomes.jsonl').open():
  try:r=json.loads(line)
  except ValueError:continue
  if r.get('strategy_id')!='STHEDGE2':continue
  if r.get('event')=='OPEN':opens[r['group_id']]=r
  elif r.get('event')=='CLOSE':
   e=opens.pop(r['group_id'],None)
   if e is None:errs['unmatched_close']+=1;continue
   pnl=float(r['pnl']);issues=[]
   for leg in e['legs']:
    side='entry_ask' if leg['side']=='LONG' else 'entry_bid'
    if leg['entry_price']!=leg[side]:issues.append('wrong_entry_side')
   for leg in r['exit_legs']:
    side='exit_bid' if leg['side']=='LONG' else 'exit_ask'
    if leg['exit_price']!=leg[side]:issues.append('wrong_exit_side')
   ts.append(dict(opened_at=e['opened_at'],closed_at=r['closed_at'],pnl=pnl,gross_notional=e['gross_notional_used'],issues=issues))
 pnl=[r['pnl'] for r in ts];wins=[p for p in pnl if p>0];losses=[p for p in pnl if p<0]
 result['native_hedge_audit']=dict(module='STHEDGE2',completed=len(ts),period_completed=sum('2026-10-07'<=r['opened_at'][:10]<='2026-10-09' for r in ts),
 nominal_pnl=sum(pnl),profit_factor=sum(wins)/-sum(losses) if losses else None,win_rate=len(wins)/len(pnl),
 period_nominal_pnl=sum(r['pnl'] for r in ts if '2026-10-07'<=r['opened_at'][:10]<='2026-10-09'),remaining_groups=len(opens),errors=dict(errs),
 side_errors=sum(bool(r['issues']) for r in ts),limitations=['Gross group notional approximately $5000, unlike $1000 single-signal sizing',
 'No displayed liquidity or complete per-leg quote timestamp evidence in stored fills','Borrow fees and short locate not verified',
 'No G6 short or multi-leg implementation is inferred from positive native returns'])
 return result
if __name__=='__main__':
 import argparse
 p=argparse.ArgumentParser();p.add_argument('evidence');p.add_argument('audit');a=p.parse_args();path=Path(a.audit)
 path.write_text(json.dumps(supplement(a.evidence,json.loads(path.read_text())),indent=2)+'\n')
