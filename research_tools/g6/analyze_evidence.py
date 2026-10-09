"""Descriptive recorded-fill audit, never a historical G6 performance claim."""
import argparse
from collections import Counter,defaultdict
from datetime import datetime
import hashlib,json,statistics
from pathlib import Path
from zoneinfo import ZoneInfo
STEMS=('paper_signal_v4_bidask_independent','paper_generation_one_bidask_independent','paper_generation_two_bidask_independent','paper_generation_three_bidask_independent','paper_generation_four_bidask_independent','paper_generation_five_bidask_independent')
def dt(t):return datetime.fromisoformat(t.replace('Z','+00:00'))
def audit(root):
 root=Path(root);ranking=json.loads((root/'frozen_ranking.json').read_text());wanted={r['module_id'][:-2] if r['module_id'].endswith('BA') else r['module_id'] for r in ranking[:98]}
 trades=defaultdict(list);entries=defaultdict(dict);reject=defaultdict(Counter);bad=Counter();sources={};orphans=Counter()
 for stem in STEMS:
  p=root/'data'/(stem+'_outcomes.jsonl');sources[p.name]=hashlib.sha256(p.read_bytes()).hexdigest()
  for n,line in enumerate(p.open(),1):
   try:r=json.loads(line)
   except ValueError:bad[p.name]+=1;continue
   sid=r.get('strategy_id')
   if sid not in wanted:continue
   ev=r.get('event_type');key=r.get('setup_id')
   if ev=='PAPER_ENTRY':entries[sid][key]=r
   elif ev=='PAPER_ENTRY_REJECTED':reject[sid][r.get('reason')]+=1
   elif ev=='PAPER_EXIT':
    if entries[sid].pop(key,None) is None:orphans[sid]+=1
    price=float(r['entry_price']);exit_price=float(r['exit_price']);ret=float(r['return_pct']);pnl=float(r['pnl']);issue=[]
    if abs(price-float(r.get('entry_ask',price)))>1e-8:issue.append('entry_not_ask')
    ep=float(r.get('exit_fill_price',exit_price))
    if abs(ep-float(r.get('exit_bid',ep)))>1e-8:issue.append('exit_fill_not_bid')
    for phase in ('entry','exit'):
     age=r.get(phase+'_quote_age_ms')
     if age is None:issue.append(phase+'_missing_age')
     elif not 0<=float(age)<=5000:issue.append(phase+'_invalid_age')
    size=r.get('displayed_ask_qty');qty=r.get('filled_qty')
    if size is None or qty is None:issue.append('missing_entry_liquidity')
    elif float(qty)>float(size):issue.append('entry_over_displayed')
    if abs(ret-(exit_price/price-1)*100)>1e-6:issue.append('return_arithmetic')
    entered=r.get('entry_timestamp');exited=r.get('exit_timestamp')
    if not entered or not exited:
     bad[p.name+':missing_fill_timestamp']+=1;continue
    if dt(exited)<dt(entered):issue.append('negative_hold')
    if qty is not None and abs(pnl-(exit_price-price)*float(qty))>1e-4:issue.append('pnl_arithmetic')
    trades[sid].append(dict(symbol=r['symbol'],entry=entered,exit=exited,signal=r['signal_timestamp'],pnl=pnl,return_pct=ret,
       hold_seconds=(dt(exited)-dt(entered)).total_seconds(),entry_spread_pct=(float(r.get('entry_ask',price))/float(r.get('entry_bid',price))-1)*100,
       notional=float(r.get('notional',price*float(qty or 0))),issues=issue,full_quote_evidence='execution_evidence' in r,
       signature=(r['symbol'],r['signal_timestamp']),source=p.name,source_line=n))
 result={}
 for sid,ts in trades.items():
  ts.sort(key=lambda t:t['exit']);pnls=[t['pnl'] for t in ts];rets=[t['return_pct'] for t in ts];wins=[p for p in pnls if p>0];losses=[p for p in pnls if p<0]
  c=peak=dd=0.;by_symbol=defaultdict(float);daily=defaultdict(float);issues=Counter()
  for t in ts:
   c+=t['pnl'];peak=max(peak,c);dd=max(dd,peak-c);by_symbol[t['symbol']]+=t['pnl'];daily[t['exit'][:10]]+=t['pnl'];issues.update(t['issues'])
  chosen=[t for t in ts if '2026-10-07'<=t['exit'][:10]<='2026-10-09']
  result[sid]=dict(completed=len(ts),period_completed=len(chosen),nominal_pnl=sum(pnls),period_nominal_pnl=sum(t['pnl'] for t in chosen),
   win_rate=sum(p>0 for p in pnls)/len(ts),avg_win=statistics.mean(wins) if wins else None,avg_loss=statistics.mean(losses) if losses else None,
   profit_factor=sum(wins)/-sum(losses) if losses else None,expectancy=statistics.mean(pnls),median_return_pct=statistics.median(rets),
   realized_pnl_drawdown=dd,largest_win=max(pnls),largest_loss=min(pnls),median_hold_seconds=statistics.median(t['hold_seconds'] for t in ts),
   average_spread_pct=statistics.mean(t['entry_spread_pct'] for t in ts),pnl_less_10bps_each_side=sum(t['pnl']-.002*t['notional'] for t in ts),
   symbol_pnl=dict(sorted(by_symbol.items(),key=lambda x:-x[1])),top_winner_share_of_gross_wins=max(wins)/sum(wins) if wins else None,
   daily_nominal_pnl=dict(daily),daily_pnl_volatility=statistics.pstdev(daily.values()) if len(daily)>1 else None,
   entry_hour_et_counts=dict(Counter(str(dt(t['entry']).astimezone(ZoneInfo('America/New_York')).hour) for t in ts)),
   issue_counts=dict(issues),missing_full_quote_evidence=sum(not t['full_quote_evidence'] for t in ts),rejections=dict(reject[sid]),
   remaining_entries=len(entries[sid]),unmatched_exits=orphans[sid],trade_examples=sorted(ts,key=lambda t:-t['pnl'])[:3])
 overlaps=[]
 for a in sorted(result):
  sa={tuple(t['signature']) for t in trades[a] if '2026-10-07'<=t['exit'][:10]<='2026-10-09'}
  if not sa:continue
  for b in sorted(result):
   if a>=b:continue
   sb={tuple(t['signature']) for t in trades[b] if '2026-10-07'<=t['exit'][:10]<='2026-10-09'}
   if sb and len(sa&sb)/len(sa|sb)>=.8:overlaps.append(dict(a=a,b=b,jaccard=len(sa&sb)/len(sa|sb),common=len(sa&sb)))
 return dict(schema='G6_PARENT_AUDIT_V1',sources=sources,modules=result,high_overlap_pairs=overlaps,malformed_lines=dict(bad),
   limitations=['Nominal recorded fills; main-engine capital ranking uses separate risk-sized simulation',
   'Drawdown excludes unrealized positions; UTC daily grouping differs from exchange day for overnight trades',
   'Exact symbol/signal-time overlap is not statistical independence',
   'Cost stress adds 10 basis points per side without replaying admissions',
   'Full tapes, venue prints, historical regimes and out-of-sample days not supplied'])
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('evidence');p.add_argument('output');a=p.parse_args();Path(a.output).write_text(json.dumps(audit(a.evidence),indent=2)+'\n')
