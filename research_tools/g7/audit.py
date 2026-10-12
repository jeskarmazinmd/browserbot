"""Read-only G7 evidence audit; frozen input, no birth or ledger mutations."""
import json,hashlib,statistics,argparse
from pathlib import Path
from collections import defaultdict,Counter
from datetime import datetime,date
from zoneinfo import ZoneInfo
NY=ZoneInfo('America/New_York')
STEMS=['paper_signal_v4_bidask_independent']+['paper_generation_'+x+'_bidask_independent' for x in ['one','two','three','four','five','six']]
def day(t):return datetime.fromisoformat(t.replace('Z','+00:00')).astimezone(NY).date().isoformat()
def audit(root,out):
 root=Path(root);out=Path(out);out.mkdir(parents=True,exist_ok=True)
 history=json.loads((root/'all_engine_bidask_daily_history.json').read_text())['days'];live=json.loads((root/'all_engine_performance_live.json').read_text());history[live['day']]=live
 daily=defaultdict(list)
 for d,r in sorted(history.items()):
  if date.fromisoformat(d).weekday()>4:continue
  for s,m in r['modules'].items():daily[s].append(dict(day=d,return_pct=m.get('return_pct',0),taken=m.get('taken',0),drawdown=m.get('max_drawdown_pct'),engine=m.get('engine')))
 trades=defaultdict(list);sources={};bad={};openrows=[];today=[]
 for stem in STEMS:
  p=root/(stem+'_outcomes.jsonl');entries={};last={};errors=0;counts=Counter()
  with p.open() as f:
   for n,line in enumerate(f,1):
    try:r=json.loads(line)
    except ValueError:errors+=1;continue
    counts[r.get('event_type')]+=1;k=r.get('setup_id')
    if r.get('event_type')=='PAPER_ENTRY':entries[k]=(r,n);last[k]=r
    elif r.get('event_type') in ('PAPER_PARTIAL_EXIT','PAPER_EXIT'):last[k]=r
  for k,(e,n) in entries.items():
   r=last[k];sid=e['strategy_id']+'BA';closed=r['event_type']=='PAPER_EXIT'
   if not closed:openrows.append(dict(strategy=sid,setup=k,symbol=e['symbol'],entry=e['entry_timestamp'],remaining=r.get('remaining_qty',e.get('filled_qty')),source=p.name));continue
   qty=e.get('filled_qty',0);price=e['entry_price'];exit=r['exit_price'];pnl=r.get('pnl',qty*(exit-price));issue=[]
   if abs(price-e.get('entry_ask',price))>1e-7:issue.append('entry_not_ask')
   if abs(r.get('exit_fill_price',exit)-r.get('exit_bid',r.get('exit_fill_price',exit)))>1e-7:issue.append('exit_not_bid')
   if abs(pnl-qty*(exit-price))>1e-4:issue.append('pnl_arithmetic')
   for phase in ['entry','exit']:
    age=(e if phase=='entry' else r).get(phase+'_quote_age_ms')
    if age is None or not 0<=age<=5000:issue.append(phase+'_quote_age')
   row=dict(strategy=sid,setup=k,symbol=e['symbol'],day=day(e['entry_timestamp']),entry=e['entry_timestamp'],exit=r['exit_timestamp'],signal=e['signal_timestamp'],entry_price=price,exit_price=exit,stop=e['stop_price'],qty=qty,notional=e.get('notional',price*qty),pnl=pnl,return_pct=(exit/price-1)*100,spread_pct=(price/e.get('entry_bid',price)-1)*100,hold_seconds=(datetime.fromisoformat(r['exit_timestamp'])-datetime.fromisoformat(e['entry_timestamp'])).total_seconds(),reason=r.get('exit_reason'),issues=issue,source=p.name,entry_line=n,metadata=e.get('research_metadata'),highest_price=r.get('highest_price'))
   trades[sid].append(row)
   if row['day']=='2026-10-12':today.append(row)
  sources[p.name]=dict(bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest(),events=dict(counts));bad[p.name]=errors
 modules={}
 for sid,ts in trades.items():
  ts.sort(key=lambda t:t['exit']);pnls=[t['pnl'] for t in ts];wins=[p for p in pnls if p>0];losses=[p for p in pnls if p<0];symbols=defaultdict(float);gain=defaultdict(float);d=defaultdict(float);cum=peak=dd=0
  for t in ts:
   symbols[t['symbol']]+=t['pnl'];gain[t['symbol']]+=max(0,t['pnl']);d[t['day']]+=t['pnl'];cum+=t['pnl'];peak=max(peak,cum);dd=max(dd,peak-cum)
  ds=daily.get(sid,[])
  modules[sid]=dict(closed=len(ts),sessions=len(d),nominal_pnl=sum(pnls),profit_factor=sum(wins)/-sum(losses) if losses else None,expectancy=statistics.mean(pnls),win_rate=len(wins)/len(ts),worst_trade=min(pnls),largest_win=max(pnls),realized_drawdown=dd,mean_spread=statistics.mean(t['spread_pct'] for t in ts),median_hold=statistics.median(t['hold_seconds'] for t in ts),symbol_pnl=dict(symbols),gross_winner_symbol_share=max(gain.values())/sum(wins) if wins else None,nominal_daily=dict(d),report_sum_return=sum(x['return_pct'] for x in ds),report_sessions=len(ds),report_taken=sum(x['taken'] for x in ds),report_worst_day=min((x['return_pct'] for x in ds),default=None),issues=dict(Counter(i for t in ts for i in t['issues'])))
 result=dict(as_of=live['as_of'],report_day=live['day'],report_modules=live['module_count'],weekday_union=len(daily),weekday_sessions=len([d for d in history if date.fromisoformat(d).weekday()<5]),sources=sources,malformed=bad,modules=modules,daily=dict(daily),open_positions=openrows,limitations=['Snapshot is intraday; export files are copied sequentially, not atomically','Main BA report uses finite-capital resimulation; ledger nominal P&L is a different measure','Generation reports lack max_drawdown_pct; absent values are unknown, not zero','No historical quote tapes were included; exit replay and independent heldout entry replay are unavailable','Missing daily report rows are not zero-return observations'])
 (out/'audit.json').write_text(json.dumps(result,indent=2)+'\n');(out/'closed_trades.json').write_text(json.dumps(dict(trades))+'\n');(out/'oct12_trades.json').write_text(json.dumps(today,indent=2)+'\n')
 print(json.dumps({k:result[k] for k in ['as_of','report_modules','weekday_union','weekday_sessions','malformed']}))
 print('Ledger leaders (>=10 completed):')
 for s,m in sorted(modules.items(),key=lambda x:-x[1]['report_sum_return']):
  if m['closed']>=10 and m['report_sum_return']>0:print(s,{k:m[k] for k in ['closed','sessions','report_sum_return','nominal_pnl','profit_factor','gross_winner_symbol_share']})
 print('Worst Oct12 closed fills:')
 for t in sorted(today,key=lambda t:t['pnl'])[:15]:print({k:t[k] for k in ['strategy','symbol','entry','exit','entry_price','exit_price','stop','qty','pnl','spread_pct','reason']})
if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('root');a.add_argument('out');v=a.parse_args();audit(v.root,v.out)
