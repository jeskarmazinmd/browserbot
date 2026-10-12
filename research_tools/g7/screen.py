"""Causal admission screens on recorded opportunities, NOT quote-tape replay.

Kept trades retain parent quantities and exits. This cannot evaluate altered
entry decisions, cash reuse, new signals, or exit paths. No independent holdout.
"""
import argparse,json,heapq
from collections import defaultdict
from datetime import datetime
from pathlib import Path
PARENTS=('CMDROT1BA','CMDGAS1BA','CMDBRD1BA','PT315H12BA','QV4XU1S50V8BA')
CONTRASTS={'COST': 'Reject contemporaneous entry spread above 0.15%',
 'SYMBOL': 'One open position per symbol within the independent account',
 'STOPDAY': 'After a realized STOP loss, block that symbol until next session'}
def stamp(t):return datetime.fromisoformat(t)
def retain(rows,mode):
 accepted=[];events=[];active=defaultdict(int);blocked=set();previous=None
 for seq,r in enumerate(sorted(rows,key=lambda r:(r['entry'],r['setup']))):
  now=stamp(r['entry'])
  if r['day']!=previous:blocked.clear();previous=r['day']
  while events and events[0][0]<=now:
   _,_,closed=heapq.heappop(events);active[closed['symbol']]-=1
   if closed['day']==r['day'] and closed['reason']=='STOP' and closed['pnl']<0:blocked.add(closed['symbol'])
  if mode=='COST' and r['spread_pct']>.15:continue
  if mode=='SYMBOL' and active[r['symbol']]>0:continue
  if mode=='STOPDAY' and r['symbol'] in blocked:continue
  accepted.append(r);active[r['symbol']]+=1;heapq.heappush(events,(stamp(r['exit']),seq,r))
 return accepted

def measures(rows):
 pnl=peak=dd=0.;daily=defaultdict(float);wins=losses=0.
 for r in sorted(rows,key=lambda r:r['exit']):
  pnl+=r['pnl'];peak=max(peak,pnl);dd=max(dd,peak-pnl);daily[r['day']]+=r['pnl'];wins+=max(0,r['pnl']);losses-=min(0,r['pnl'])
 return dict(trades=len(rows),nominal_pnl=pnl,return_on_5000_pct=pnl/50,realized_drawdown_usd=dd,worst_trade_usd=min((r['pnl'] for r in rows),default=None),worst_day_usd=min(daily.values(),default=None),profit_factor=wins/losses if losses else None,expectancy=pnl/len(rows) if rows else None,gross_profit=wins,stress10bps_each_side=pnl-sum(.002*r['notional'] for r in rows))
def screen(trades):
 result=[]
 for i,parent in enumerate(PARENTS,1):
  allrows=trades.get(parent,[])
  for mode,idea in CONTRASTS.items():
   kept=retain(allrows,mode);periods={}
   for label,predicate in [('development',lambda r:r['day']<='2026-10-06'),('retrospective_validation',lambda r:'2026-10-07'<=r['day']<='2026-10-09'),('oct12_diagnostic',lambda r:r['day']=='2026-10-12'),('all',lambda r:True)]:
    base=measures([r for r in allrows if predicate(r)]);variant=measures([r for r in kept if predicate(r)])
    periods[label]=dict(parent=base,screen=variant,trade_retention=variant['trades']/base['trades'] if base['trades'] else None,gross_profit_preserved=variant['gross_profit']/base['gross_profit'] if base['gross_profit'] else None)
   result.append(dict(proposed_id=f'G7P{i:02d}{mode}',parent=parent,track='both' if mode!='SYMBOL' else 'A',hypothesis=idea,periods=periods,accepted_for_activation=False,reason='Full causal replay and independent prospective evidence missing'))
 return dict(schema='G7_RECORDED_OPPORTUNITY_SCREEN_V1',candidates=result,independent_holdout=False,limitations=__doc__)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('trades');p.add_argument('output');a=p.parse_args();result=screen(json.loads(Path(a.trades).read_text()));Path(a.output).write_text(json.dumps(result,indent=2)+'\n')
 for c in result['candidates']:
  a=c['periods']['all'];v=c['periods']['retrospective_validation'];print(c['proposed_id'],c['parent'],round(a['parent']['nominal_pnl'],2),'->',round(a['screen']['nominal_pnl'],2),'trades',a['screen']['trades'],'/',a['parent']['trades'],'validation',round(v['parent']['nominal_pnl'],2),'->',round(v['screen']['nominal_pnl'],2))
