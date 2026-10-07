"""Advisory prospective G5 evidence. Paired contrasts are not discoveries."""
import argparse
from collections import defaultdict
import json
from pathlib import Path
from datetime import datetime,timezone
from strategies import generation_five as g
from generation_five_paper_tracker import FILE_STEM
from paper_outcome_tracker import NY,_utc

def build(root,as_of=None):
    root=Path(root);cutoff=_utc(as_of or datetime.now(timezone.utc));birth_path=root/(FILE_STEM+'_births.json')
    if not birth_path.exists():return {'status':'not_activated','modules':{},'verified':False}
    births=json.loads(birth_path.read_text());coverage_path=root/(FILE_STEM+'_observations.json')
    coverage=json.loads(coverage_path.read_text()) if coverage_path.exists() else {}
    entries={};closed={};residual={};rejects=defaultdict(int);bad=[];duplicate=[];execution=defaultdict(list)
    path=root/(FILE_STEM+'_outcomes.jsonl')
    if path.exists():
        with path.open() as handle:
            for n,line in enumerate(handle,1):
                try:r=json.loads(line)
                except ValueError:bad.append(n);continue
                sid=r.get('strategy_id');key=r.get('setup_id');event=r.get('event_type')
                if sid not in births or sid not in g.ALL_IDS:continue
                try:
                    when=_utc(r.get('exit_timestamp') or r.get('entry_timestamp') or r['recorded_at'])
                    signal_time=_utc(r['signal_timestamp'])
                except (KeyError,ValueError,TypeError):bad.append(n);continue
                if when>cutoff:continue
                if signal_time<_utc(births[sid]):
                    if event!='PAPER_ENTRY_REJECTED':execution[sid].append('prebirth_fill')
                    continue
                if event=='PAPER_ENTRY_REJECTED':rejects[sid]+=1;continue
                if event=='PAPER_ENTRY':
                    if key in entries:duplicate.append(key)
                    entries[key]=r;residual[key]=r
                    if r.get('entry_price')!=r.get('entry_ask'):execution[sid].append('entry_not_ask')
                    if r.get('filled_qty',0)>r.get('displayed_ask_qty',0):execution[sid].append('entry_exceeds_available_book')
                elif event in {'PAPER_PARTIAL_EXIT','PAPER_EXIT'}:
                    if key not in entries:execution[sid].append('unmatched_exit');continue
                    if r.get('exit_fill_price')!=r.get('exit_bid'):execution[sid].append('exit_not_bid')
                    if event=='PAPER_EXIT':
                        if key in closed:duplicate.append(key)
                        closed[key]=r
                    residual[key]=r
                for field in ('entry_quote_age_ms','exit_quote_age_ms'):
                    if field not in r:continue
                    age=r[field]
                    if age is None or age<0 or age>g.spec_for(sid).max_quote_age_ms:execution[sid].append('invalid_'+field)
    grouped=defaultdict(list)
    for key,r in closed.items():grouped[r['strategy_id']].append(r)
    modules={}
    for sid in sorted(births.keys()&g.ALL_IDS):
        if _utc(births[sid])>cutoff:continue
        rows=grouped[sid];symbols=defaultdict(float);days=defaultdict(float)
        for r in rows:
            symbols[r['symbol']]+=r['pnl'];days[_utc(r['entry_timestamp']).astimezone(NY).date().isoformat()]+=r['pnl']
        total=sum(days.values());best_trade=max([r['pnl'] for r in rows],default=0.)
        best_symbol=max(symbols.values(),default=0.);best_day=max(days.values(),default=0.)
        pnl=peak=dd=0.
        for r in sorted(rows,key=lambda r:r['exit_timestamp']):
            pnl+=r['pnl'];peak=max(peak,pnl);dd=max(dd,peak-pnl)
        positive_gross=sum(max(r['pnl'],0.) for r in rows)
        obs={d:r for d,r in coverage.get(sid,{}).items() if d<=cutoff.astimezone(NY).date().isoformat()}
        modules[sid]=dict(birth=births[sid],closed_trades=len(rows),symbol_count=len(symbols),
            traded_days=len(days),profitable_traded_days=sum(v>0 for v in days.values()),
            closed_fill_pnl=total,closed_fill_return_sum_pct=total/50,
            excluding_best_trade_pnl=total-best_trade,excluding_best_symbol_pnl=total-best_symbol,
            excluding_best_day_pnl=total-best_day,best_trade_fraction_of_gross_profit=best_trade/positive_gross if positive_gross else None,
            best_symbol_fraction_of_gross_profit=best_symbol/positive_gross if positive_gross else None,
            best_day_fraction_of_gross_profit=best_day/positive_gross if positive_gross else None,
            symbol_pnl=dict(symbols),day_pnl=dict(days),closed_trade_drawdown_dollars=dd,
            drawdown_basis='completed trades only; no intratrade mark drawdown claim',
            residual_positions=sum(r['strategy_id']==sid and r.get('remaining_qty',0)>0 for r in residual.values()),
            rejects=rejects[sid],execution_issues=execution[sid],coverage=obs,
            hypothesis=g.spec_for(sid).hypothesis,comparison_id=g.spec_for(sid).comparison_id,
            evidence_label='prospective experiment; no durability or significance claim')
    return dict(as_of=cutoff.isoformat(),verified=not bad and not duplicate and not any(execution.values()),
                malformed_lines=bad,duplicate_events=duplicate,modules=modules,
                accounting='actual fills; separate $5k daily equal-start portfolios; never sum strategies',
                multiplicity='12 related admissions x 8 paired interventions; no independent-discovery claim')
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',default='/data');p.add_argument('--as-of');a=p.parse_args()
    print(json.dumps(build(a.root,a.as_of),indent=2))
