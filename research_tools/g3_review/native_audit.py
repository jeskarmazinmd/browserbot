"""Read native outcome schemas without pooling accounting/execution regimes."""
import json
from collections import Counter,defaultdict
from pathlib import Path
from zoneinfo import ZoneInfo
from research_tools.g3_review.analyze import number,stamp,write_csv
from reporting.all_engine_performance import options_rv_closed_pnl,closed_pnl
NY=ZoneInfo('America/New_York')

def opened(row):
    return stamp(row.get('opened_at') or row.get('signal_timestamp') or row.get('entry_timestamp') or row.get('timestamp'))

def closed(row):
    return stamp(row.get('closed_at') or row.get('exit_timestamp') or row.get('exit_time'))

def run(data,out):
    out.mkdir(parents=True,exist_ok=True);trades=[];quality=[]
    for path in sorted(data.glob('*outcomes.jsonl')):
        if 'bidask' in path.name:continue
        entries={};closes={};events=Counter();bad=[];seen=set();duplicates=0;overwrite=Counter()
        with path.open(errors='replace') as f:
            for i,line in enumerate(f,1):
                try:r=json.loads(line)
                except ValueError:bad.append(i);continue
                if not isinstance(r,dict):bad.append(i);continue
                if line in seen:duplicates+=1
                seen.add(line)
                sid=r.get('strategy_id') or r.get('strategy') or r.get('module_id')
                ident=r.get('group_id') or r.get('setup_id') or r.get('event_id') or r.get('key')
                event=str(r.get('event') or r.get('event_type') or 'NO_EVENT');events[event]+=1
                if not sid or not ident:continue
                # Options-RV reuses day-level setup IDs after restart; distinct opened_at is a distinct outcome.
                if path.name.startswith('options_rv'):ident=str(ident)+'|'+str(r.get('opened_at'))
                key=(sid,str(ident));is_close=closed(r) is not None or event in {'CLOSE','OPTION_EXIT','MULTI_LEG_EXIT'}
                if is_close:
                    if key in closes:overwrite['close']+=1
                    closes[key]=r
                elif opened(r):
                    if key in entries:overwrite['entry']+=1
                    entries[key]=r
        for key,r in closes.items():
            entry=entries.get(key,r);pnl=options_rv_closed_pnl(r) if path.name.startswith('options_rv') else closed_pnl(r)
            ts=opened(entry);end=closed(r)
            symbols=sorted({str(leg.get('symbol')) for leg in entry.get('legs',[]) if leg.get('symbol')})
            if not symbols and entry.get('symbol'):symbols=[entry['symbol']]
            gross=number(entry.get('gross_notional_used',entry.get('notional_used',entry.get('group_notional'))))
            # Single-leg/multi-equity check validates recorded share economics.
            reconstructed=None
            if entry.get('shares') and r.get('exit_price') is not None:
                reconstructed=(number(r['exit_price'])-number(entry['entry_price']))*number(entry['shares'])*(1 if entry.get('side')=='LONG' else -1)
            elif path.name=='statarb_paper_outcomes.jsonl':
                exits={x['symbol']:x for x in r.get('exit_legs',[])}
                if all(x['symbol'] in exits for x in entry.get('legs',[])):
                    reconstructed=sum((number(exits[x['symbol']]['exit_price'])-number(x['entry_price']))*number(x['shares'])*(1 if x['side']=='LONG' else -1) for x in entry['legs'])
            elif path.name in {'futures_paper_outcomes.jsonl','futures_curve_paper_outcomes.jsonl','forex_paper_outcomes.jsonl'}:
                exits={x['symbol']:x for x in r.get('legs',[])}
                if all(x['symbol'] in exits for x in entry.get('legs',[])):
                    values=[]
                    for x in entry['legs']:
                        px=number(exits[x['symbol']]['close_price']);sign=1 if x['side']=='LONG' else -1
                        if path.name.startswith('forex'):
                            v=(px-number(x['entry_price']))*number(x['units'])*sign
                            if x['symbol'].startswith('USD/'):v/=px
                        else:v=(px-number(x['entry_price']))*number(x['multiplier'])*sign-number(x['entry_commission'])-2.25
                        values.append(v)
                    reconstructed=sum(values)
            elif path.name=='options_paper_outcomes.jsonl':
                exits={x['symbol']:x for x in r.get('exit_legs',[])}
                if all(x['symbol'] in exits for x in entry.get('legs',[])):
                    reconstructed=number(entry['open_cash_flow'])+sum(number(exits[x['symbol']]['close_exec'])*number(x.get('multiplier',100))*(1 if x['side']=='BUY' else -1) for x in entry['legs'])
            trades.append({'source':path.name,'module':key[0],'trade_id':key[1],
                'opened_at':ts.isoformat() if ts else None,'entry_market_day':ts.astimezone(NY).date().isoformat() if ts else None,
                'closed_at':end.isoformat() if end else None,'symbols':'|'.join(symbols),'closed_pnl':pnl,
                'stored_pnl':number(r.get('pnl_dollars',r.get('pnl',r.get('net_pnl_dollars')))),
                'cash_flow_sign_version':r.get('cash_flow_sign_version'),'gross_notional':gross,
                'exit_reason':r.get('exit_reason',r.get('reason')),
                'hold_seconds':(end-ts).total_seconds() if end and ts else None,
                'pnl_reconstruction_difference':pnl-reconstructed if pnl is not None and reconstructed is not None else None,
                **{field:r.get(field,entry.get(field)) for field in ['short_locate_verified','borrow_fees_included','financing_swap_included','overnight_financing_included','dividends_corporate_actions_modeled']}})
        quality.append({'source':path.name,'malformed_lines':len(bad),'malformed_line_numbers':bad,
            'exact_duplicate_lines':duplicates,'overwritten_keys':dict(overwrite),'events':dict(events),
            'closed_keys':len(closes),'open_keys':len(set(entries)-set(closes)),
            'close_without_separate_entry':len(set(closes)-set(entries)),
            'note':'Options RV is one self-contained closed row; no separate entry expected. Open-key P&L unmarked, excluded.'})
    groups=defaultdict(list)
    for r in trades:
        day=r['entry_market_day'] or ''
        for period,start,end in [('all_retained','0000','9999'),('modern','2026-09-18','2026-10-06'),('last5','2026-09-30','2026-10-06'),('legacy','0000','2026-09-17')]:
            if start<=day<=end:groups[(r['source'],r['module'],period)].append(r)
    summaries=[]
    for (source,sid,period),rs in sorted(groups.items()):
        pnl=[r['closed_pnl'] for r in rs if r['closed_pnl'] is not None];gain=sum(v for v in pnl if v>0);loss=-sum(v for v in pnl if v<0)
        days=defaultdict(float);syms=defaultdict(float)
        for r in rs:
            if r['closed_pnl'] is not None:days[r['entry_market_day']]+=r['closed_pnl'];syms[r['symbols']]+=r['closed_pnl']
        summaries.append({'source':source,'module':sid,'period':period,'closed':len(rs),'priced_closed':len(pnl),
            'first_entry_day':min(days) if days else None,'last_entry_day':max(days) if days else None,'entry_days':len(days),
            'closed_pnl':sum(pnl),'profit_factor':gain/loss if loss else None,'win_fraction':sum(v>0 for v in pnl)/len(pnl) if pnl else None,
            'pnl_excluding_best_trade':sum(pnl)-max(pnl) if pnl else None,
            'pnl_excluding_best_day':sum(pnl)-max(days.values()) if days else None,
            'pnl_excluding_best_symbol_set':sum(pnl)-max(syms.values()) if syms else None,
            'unique_symbol_sets':len(syms),'closed_pnl_extra_1bp_each_side':sum(r['closed_pnl']-.0002*r['gross_notional'] for r in rs) if source in {'statarb_paper_outcomes.jsonl','short_paper_outcomes.jsonl','microstructure_paper_outcomes.jsonl','swing_paper_outcomes.jsonl'} and all(r['closed_pnl'] is not None and r['gross_notional'] is not None for r in rs) else None,
            'median_gross_notional':__import__('statistics').median([r['gross_notional'] for r in rs if r['gross_notional'] is not None]) if any(r['gross_notional'] is not None for r in rs) else None,
            'unverified_short_locate_rows':sum(r['short_locate_verified'] is False for r in rs),
            'borrow_fees_omitted_rows':sum(r['borrow_fees_included'] is False for r in rs),
            'economics_note':'Native currencies/contracts/options/multi-leg; actual closed P&L, stock extra 1bp/side only where share gross exposure is known; accounting regimes separate'})
    write_csv(out/'native_closed_trades.csv',trades);write_csv(out/'native_module_metrics.csv',summaries)
    (out/'native_quality.json').write_text(json.dumps(quality,indent=2))

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--data',required=True,type=Path);p.add_argument('--out',required=True,type=Path)
    a=p.parse_args();run(a.data,a.out)
