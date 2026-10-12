"""Completed-minute causal replay; no tracker, births, or production outcome writes.

Archive final-minute observations become known at the NEXT minute boundary.
Neither LAST tape prices nor idealized stop prices are used for executable fills.
"""
import argparse,json,math,statistics
from collections import defaultdict
from datetime import datetime,timedelta
from pathlib import Path
from dataclasses import asdict
from engine.events import MarketSnapshot,Quote
from executable_paper_engine import executable_mark,classify_limit_order
from research_tools.g7.experiments import CATALOG,PARENTS,Evaluator
from importlib import import_module

def snapshot(r):
 t=datetime.fromisoformat(r['minute']);available=t+timedelta(minutes=1);quotes={s:Quote(q['legacy_price'],bid=q['bid'],ask=q['ask']) for s,q in r['quotes'].items() if q.get('legacy_price') and q['legacy_price']>0 and datetime.fromisoformat(q['collector_observed_at'])<available}
 return MarketSnapshot(t,quotes,len(quotes),len(quotes),0),r['quotes']
class Portfolio:
 def __init__(self,family,mechanism='CTL'):
  self.family=family;self.mechanism=mechanism;self.cash=5000.;self.active=[];self.trades=[];self.book={};self.peak=5000.;self.dd=0.;self.rejects=defaultdict(int);self.max_positions=0;self.last_admitted={}
 def mark(self,quotes,now):
  for r in list(self.active):
   q=quotes.get(r['symbol'],{});m=executable_mark(q,action='SELL',now=now,max_quote_age_ms=5000)
   if m['state']!='EXECUTABLE' or m.get('quote_age_ms',-1)<0:continue
   bid=m['price'];r['high']=max(r['high'],bid)
   if not r.get('pending'):
    if bid<=r['stop']:r['pending']='STOP'
    elif bid>=r['target']:r['pending']='TARGET'
    elif self.mechanism=='PROTECT' and r['high']>=r['entry']*1.005 and bid<=r['high']*.9965:r['pending']='G7_PROFIT_PROTECT'
    elif now.astimezone(__import__('zoneinfo').ZoneInfo('America/New_York')).hour*60+now.astimezone(__import__('zoneinfo').ZoneInfo('America/New_York')).minute>=955:r['pending']='EOD'
   if not r.get('pending'):continue
   quantity=self.fill(q,'SELL',r['remaining'],now,r['symbol'])
   if not quantity:continue
   proceeds=quantity*bid;self.cash+=proceeds;r['proceeds']+=proceeds;r['remaining']-=quantity
   if not r['remaining']:
    r.update(exit=now.isoformat(),exit_price=r['proceeds']/r['qty'],pnl=r['proceeds']-r['qty']*r['entry']);self.trades.append(r);self.active.remove(r)
  values=[]
  for r in self.active:
   q=quotes.get(r['symbol'],{});m=executable_mark(q,action='SELL',now=now,max_quote_age_ms=5000)
   if m['state']=='EXECUTABLE' and m.get('quote_age_ms',-1)>=0:values.append(r['remaining']*m['price'])
   else:return
  equity=self.cash+sum(values);self.peak=max(self.peak,equity);self.dd=max(self.dd,(self.peak-equity)/self.peak*100)
 def fill(self,q,action,requested,now,symbol):
  side='ask' if action=='BUY' else 'bid';key=(symbol,side);identity=q.get(side+'_time_ms',q.get('quote_time_ms'));used=self.book.get(key,(None,0))[1] if self.book.get(key,(None,0))[0]==identity else 0
  q=dict(q);raw=q.get(side+'_size_raw');q[side+'_size_raw']=max(0,int(raw)-used) if raw is not None else None
  if identity is None:return 0
  d=classify_limit_order(q,action=action,limit_price=q.get(side),requested_qty=requested,now=now,max_quote_age_ms=5000)
  if d.outcome not in ('FULL','PARTIAL') or d.quote_age_ms<0:return 0
  self.book[key]=(identity,used+d.filled_qty);return d.filled_qty
 def enter(self,event,quotes,now):
  local=now.astimezone(__import__('zoneinfo').ZoneInfo('America/New_York'))
  if not 570<=local.hour*60+local.minute<930:return
  symbol=event.symbol
  if symbol in self.last_admitted and (now-self.last_admitted[symbol]).total_seconds()<1800:return
  q=quotes.get(symbol,{});ask=q.get('ask');bid=q.get('bid')
  for action in ('BUY','SELL'):
   m=executable_mark(q,action=action,now=now,max_quote_age_ms=5000)
   if m['state']!='EXECUTABLE' or m.get('quote_age_ms',-1)<0:self.rejects['nonexecutable']+=1;return
  if self.mechanism=='COST' and (ask/bid-1)*100>.10:self.rejects['cost']+=1;return
  stop=event.data['stop_price'];target=event.data['target_price']
  if not 0<stop<bid<=ask<target:self.rejects['geometry']+=1;return
  equity=self.cash+sum(r['remaining']*r['entry'] for r in self.active)
  requested=min(math.floor(self.cash/ask),math.floor(equity*.2/ask),math.floor(equity*.01/(ask-stop)))
  if requested<1:return
  qty=self.fill(q,'BUY',requested,now,symbol)
  if not qty:self.rejects['liquidity']+=1;return
  self.cash-=qty*ask;self.last_admitted[symbol]=now;self.active.append(dict(symbol=symbol,entry_time=now.isoformat(),entry=ask,stop=stop,target=target,qty=qty,remaining=qty,proceeds=0.,high=ask,day=now.date().isoformat()));self.max_positions=max(self.max_positions,len(self.active))
 def results(self,quotes,now):
  unmarked=0;equity=self.cash
  for r in self.active:
   m=executable_mark(quotes.get(r['symbol'],{}),action='SELL',now=now,max_quote_age_ms=5000)
   if m['state']!='EXECUTABLE' or m.get('quote_age_ms',-1)<0:unmarked+=1
   else:equity+=r['remaining']*m['price']
  pnls=[r['pnl'] for r in self.trades];wins=sum(max(p,0) for p in pnls);loss=-sum(min(p,0) for p in pnls)
  return dict(return_pct=(equity/5000-1)*100 if not unmarked else None,pnl=equity-5000 if not unmarked else None,drawdown_pct=self.dd,closed=len(pnls),open=len(self.active),unmarked=unmarked,profit_factor=wins/loss if loss else None,worst_trade=min(pnls,default=None),expectancy=statistics.mean(pnls) if pnls else None,max_positions=self.max_positions,rejections=dict(self.rejects),gross_profit=wins)
def replay(root,out):
 result=defaultdict(dict)
 for p in sorted(Path(root).glob('*.jsonl')):
  controls={f:import_module('strategies.'+v[1]).Strategy() for f,v in PARENTS.items()};strategies={s.strategy_id:Evaluator(s) for s in CATALOG};ports={f:Portfolio(f) for f in controls};ports.update({s.strategy_id:Portfolio(s.family,s.mechanism) for s in CATALOG})
  for line in p.open():
   snap,books=snapshot(json.loads(line));now=snap.timestamp+timedelta(minutes=1)
   for port in ports.values():port.mark(books,now)
   for family,strategy in controls.items():
    for e in strategy.on_snapshot(snap):ports[family].enter(e,books,now)
   for sid,strategy in strategies.items():
    for e in strategy.on_snapshot(snap):ports[sid].enter(e,books,now)
  d=snap.timestamp.date().isoformat()
  for sid,port in ports.items():result[sid][d]=port.results(books,now)
  print(d,flush=True)
 data=dict(schema='G7_MINUTE_ARCHIVE_REPLAY_V1',candidates=[asdict(s) for s in CATALOG],results=dict(result),limitations=__doc__,independent_holdout=False)
 Path(out).write_text(json.dumps(data,indent=2)+'\n')
 for s in CATALOG:
  def total(sid,dates):return sum(r['return_pct'] or 0 for d,r in result[sid].items() if d in dates)
  dev=['2026-10-02','2026-10-05','2026-10-06'];val=['2026-10-07','2026-10-08','2026-10-09'];print(s.strategy_id,'dev',round(total(s.family,dev),3),round(total(s.strategy_id,dev),3),'val',round(total(s.family,val),3),round(total(s.strategy_id,val),3),'trades',sum(r['closed'] for r in result[s.strategy_id].values()))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('root');p.add_argument('out');a=p.parse_args();replay(a.root,a.out)
