"""Read-only legacy BA forensic review; never writes performance history."""
import argparse,json,math
from collections import Counter,defaultdict
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from reporting.capital_performance import simulate_day
NY=ZoneInfo('America/New_York')
def ts(v):
 try:return datetime.fromisoformat(str(v).replace('Z','+00:00'))
 except:return None
def day(r):
 t=ts(r.get('entry_timestamp',r.get('signal_timestamp')))
 return t.astimezone(NY).date().isoformat() if t else None
def review(root):
 entries={}; exits={}; duplicates=Counter(); malformed=[]; rejects=Counter()
 p=Path(root)/'paper_signal_v4_bidask_independent_outcomes.jsonl'
 with p.open() as f:
  for line_no,l in enumerate(f,1):
   try:r=json.loads(l)
   except:malformed.append(line_no);continue
   sid=r.get('strategy_id'); k=(sid,r.get('setup_id')); ev=r.get('event_type')
   if ev=='PAPER_ENTRY_REJECTED':rejects[sid]+=1;continue
   dest=entries if ev=='PAPER_ENTRY' else exits if ev=='PAPER_EXIT' else None
   if dest is not None:
    if k in dest:duplicates[(sid,ev)]+=1
    dest[k]=r
 grouped=defaultdict(list); flags=defaultdict(Counter); detailed=defaultdict(list)
 for k,r in exits.items():
  sid=k[0];e=entries.get(k); issues=[]
  if not e:issues.append('unmatched_exit')
  else:
   for field in ['entry_timestamp','entry_price','filled_qty']:
    if e.get(field)!=r.get(field):issues.append('entry_exit_'+field+'_mismatch')
  for field,limit in [('entry_quote_age_ms',5000),('exit_quote_age_ms',5000)]:
   age=r.get(field)
   if age is None:issues.append('missing_'+field)
   elif age<0:issues.append('future_'+field)
   elif age>limit:issues.append('stale_'+field)
  try:
   q=r['filled_qty']; ep=r['entry_price'];xp=r['exit_price']; pnl=q*(xp-ep)
   if ep!=r.get('entry_ask'):issues.append('entry_not_ask')
   if xp!=r.get('exit_bid'):issues.append('exit_not_bid')
   if q>r.get('displayed_ask_qty',0):issues.append('entry_exceeds_displayed')
   if q>r.get('requested_qty',0):issues.append('entry_exceeds_requested')
   if abs(pnl-r['pnl'])>.011:issues.append('pnl_mismatch')
   if ts(r['exit_timestamp'])<ts(r['entry_timestamp']):issues.append('exit_before_entry')
   if ts(r['entry_timestamp'])<ts(r['signal_timestamp']):issues.append('entry_before_signal')
  except (KeyError,TypeError):issues.append('missing_fill_fields');pnl=r.get('pnl',0)
  flags[sid].update(issues)
  if issues:detailed[sid].append({'setup_id':k[1],'issues':issues})
  grouped[sid].append(r)
 summaries={}
 def sim(rows):
  by=defaultdict(list)
  for r in rows:by[day(r)].append(r)
  results={d:simulate_day(rr) for d,rr in sorted(by.items()) if d}
  return results,sum(x['pnl'] if 'pnl' in x else x['end_equity']-5000 for x in results.values())
 for sid,rows in grouped.items():
  daily,total=sim(rows); raw=sum(r.get('pnl',0) for r in rows)
  sy=defaultdict(float);dy=defaultdict(float)
  for r in rows:sy[r['symbol']]+=r.get('pnl',0);dy[day(r)]+=r.get('pnl',0)
  best=max(rows,key=lambda r:r.get('pnl',0)); bestsym=max(sy,key=sy.get);bestday=max(daily,key=lambda d:daily[d]['end_equity'])
  overlaps=0;simultaneous=0;active=defaultdict(list);exitsame=Counter()
  for r in sorted((r for r in rows if ts(r.get('entry_timestamp')) and ts(r.get('exit_timestamp'))),key=lambda r:ts(r['entry_timestamp'])):
   sym=r['symbol'];now=ts(r['entry_timestamp']);active[sym]=[x for x in active[sym] if x>now]
   overlaps+=bool(active[sym]);active[sym].append(ts(r['exit_timestamp']))
   exitsame[(sym,r['exit_timestamp'],r.get('exit_bid'))]+=1
  simultaneous=sum(v-1 for v in exitsame.values() if v>1)
  summaries[sid]={'trades':len(rows),'symbols':len(sy),'traded_days':len(daily),'positive_days':sum(x['return_pct']>0 for x in daily.values()),'raw_pnl':raw,'capital_pnl':total,'equal_start_return_sum_pct':total/50,'excluding_best_trade_pnl':sim([r for r in rows if r is not best])[1],'excluding_best_symbol_pnl':sim([r for r in rows if r['symbol']!=bestsym])[1],'excluding_best_day_pnl':sim([r for r in rows if day(r)!=bestday])[1],'best_symbol':bestsym,'best_symbol_raw_pnl':sy[bestsym],'best_trade_pnl':best.get('pnl',0),'best_day':bestday,'best_day_raw_pnl':dy[bestday],'max_cost_equity_drawdown_pct':max(x['max_drawdown_pct'] for x in daily.values()),'overlapping_symbol_entries':overlaps,'same_quote_time_extra_exits':simultaneous,'rejected':rejects[sid],'flags':dict(flags[sid]),'duplicate_entries':duplicates[(sid,'PAPER_ENTRY')],'duplicate_exits':duplicates[(sid,'PAPER_EXIT')],'daily':daily,'symbol_pnl':dict(sy)}
 return {'scope':'main independent BA ledger only; other engine evidence must be audited separately','malformed_lines':malformed,'entries':len(entries),'exits':len(exits),'unclosed_entries':len(entries.keys()-exits.keys()),'modules':summaries,'flagged_trades':dict(detailed)}
if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('--root',required=True);ap.add_argument('--output',required=True);a=ap.parse_args();Path(a.output).write_text(json.dumps(review(a.root),indent=2))
