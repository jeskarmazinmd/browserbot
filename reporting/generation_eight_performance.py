"""Actual G8 quantities, explicit unknown marks and carry; no hindsight sizing."""
import json
from collections import defaultdict
from executable_paper_engine import executable_mark
from generation_eight_paper_tracker import FILE_STEM, IDS
from strategies import generation_eight as g
from strategies.output_switches import output_enabled
from paper_outcome_tracker import _utc, NY

def _rows(path):
    with path.open() as handle:
        for line in handle:yield json.loads(line)

def calculate_generation_eight(root,day,cutoff,marks,quote_for):
    birth_path=root/(FILE_STEM+'_births.json')
    diagnostics=dict(entries=0,exits=0,partial_exits=0,rejected=0,unmarked=0,overnight_carry_unverified_modules=0)
    if not birth_path.exists():return {},diagnostics
    births=json.loads(birth_path.read_text());entries={};last={};reject=defaultdict(int);carry=set()
    path=root/(FILE_STEM+'_outcomes.jsonl')
    if path.exists():
        for row in _rows(path):
            sid=row['strategy_id'];event=row['event_type'];setup=row['setup_id']
            if sid not in IDS:raise ValueError('Unknown G8 performance ID')
            when=_utc(row.get('exit_timestamp') if event in {'PAPER_EXIT','PAPER_PARTIAL_EXIT'} else row.get('entry_timestamp') if event=='PAPER_ENTRY' else row['recorded_at'])
            if when>cutoff:continue
            if event=='PAPER_ENTRY_REJECTED':
                if when.astimezone(NY).date().isoformat()==day:reject[sid]+=1;diagnostics['rejected']+=1
                continue
            if event=='PAPER_ENTRY':
                if _utc(row['signal_timestamp'])<_utc(births[sid]):raise ValueError('Prebirth G8 entry')
                entries[setup]=row;last[setup]=row
            elif event in {'PAPER_EXIT','PAPER_PARTIAL_EXIT'}:
                if setup not in entries:raise ValueError('Orphan G8 performance exit')
                last[setup]=row
                if _utc(entries[setup]['entry_timestamp']).astimezone(NY).date().isoformat()<day and when.astimezone(NY).date().isoformat()==day:carry.add(sid)
    grouped=defaultdict(list)
    for setup,e in entries.items():
        d=_utc(e['entry_timestamp']).astimezone(NY).date().isoformat();residual=last[setup]
        if d<day and residual['remaining_qty']>0:carry.add(e['strategy_id'])
        if d==day:grouped[e['strategy_id']].append((e,residual))
    modules={}
    for sid in sorted(IDS):
        if sid not in births or _utc(births[sid])>cutoff or not output_enabled(sid):continue
        pairs=grouped[sid];pnl=0.;opened=closed=0;unknown=sid in carry
        for e,r in pairs:
            if r['remaining_qty']:
                opened+=1;q=quote_for(e['symbol'],marks);mark=executable_mark(q,action='SELL',now=cutoff,max_quote_age_ms=5000)
                if mark['state']!='EXECUTABLE' or mark.get('quote_age_ms',-1)<0:unknown=True;diagnostics['unmarked']+=1;continue
                pnl+=r['realized_proceeds']+r['remaining_qty']*mark['price']-e['notional']
            else:closed+=1;pnl+=r['realized_proceeds']-e['notional']
        diagnostics['entries']+=len(pairs);diagnostics['exits']+=closed
        modules[sid+'BA']=dict(engine='generation_eight_bidask_independent',starting_cash=5000.,
            pnl=None if unknown else pnl,return_pct=None if unknown else pnl/50.,end_equity=None if unknown else 5000.+pnl,
            signals=len(pairs)+reject[sid],taken=len(pairs),skipped=reject[sid],open_taken=opened,closed_taken=closed,
            status='carry_unverified' if sid in carry else 'mark_unavailable' if unknown else 'prospective' if pairs else 'no_entries',
            prospective_start_utc=births[sid],actual_fill_quantities=True,portfolio_combinable=False,
            accounting='actual quantities; daily equal-start $5k; no cross-strategy aggregation',research_metadata=g.metadata(sid))
    diagnostics['overnight_carry_unverified_modules']=len(carry)
    return modules,diagnostics
