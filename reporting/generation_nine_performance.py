"""Actual G9 fills, $5k daily equal starts, no synthetic sizing or backfill."""
import json
from pathlib import Path
from strategies import generation_nine as g
from strategies.output_switches import output_enabled
from generation_nine_paper_tracker import FILE_STEM,mark_group


def calculate_generation_nine(root,day,cutoff,quotes):
    root=Path(root);birth_path=root/(FILE_STEM+'_births.json')
    diagnostics=dict(entries=0,closes=0,rejected=0,unmarked=0,carry_unverified=0)
    if not birth_path.exists():return {},diagnostics
    births=json.loads(birth_path.read_text());entries={};closes={};rejected={};carry=set()
    path=root/(FILE_STEM+'_outcomes.jsonl')
    if path.exists():
        with path.open() as handle:
            for line in handle:
                r=json.loads(line);sid=r['strategy_id'];t=g.utc(r['timestamp'])
                if t>cutoff:continue
                if sid not in g.IDS or sid not in births or t<g.utc(births[sid]):raise ValueError('Invalid G9 provenance')
                d=t.astimezone(g.NY).date().isoformat()
                if r['event']=='OPEN':entries[r['group_id']]=r
                elif r['event']=='CLOSE':
                    gid=r['group_id']
                    if gid not in entries:raise ValueError('Orphan G9 close')
                    closes[gid]=r
                    if g.utc(entries[gid]['opened_at']).astimezone(g.NY).date().isoformat()<day and d==day:carry.add(sid)
                elif r['event']=='REJECT' and d==day:rejected[sid]=rejected.get(sid,0)+1
    grouped={sid:[] for sid in g.IDS}
    for gid,e in entries.items():
        d=g.utc(e['opened_at']).astimezone(g.NY).date().isoformat()
        if d<day and gid not in closes:carry.add(e['strategy_id'])
        if d==day:grouped[e['strategy_id']].append((gid,e))
    modules={}
    for sid in sorted(g.IDS):
        if sid not in births or g.utc(births[sid])>cutoff or g.utc(births[sid]).astimezone(g.NY).date().isoformat()>day or not output_enabled(sid):continue
        pnl=0.;opened=closed=0;unknown=sid in carry
        for gid,e in grouped[sid]:
            if gid in closes:pnl+=closes[gid]['pnl'];closed+=1
            else:
                opened+=1;mark=mark_group(e,quotes,cutoff,g.SPECS[sid])
                if mark is None:unknown=True;diagnostics['unmarked']+=1
                else:pnl+=mark['pnl']
        count=len(grouped[sid]);skip=rejected.get(sid,0)
        modules[sid]=dict(engine='generation_nine_sthedge2',starting_cash=5000.,
            return_pct=None if unknown else pnl/50.,pnl=None if unknown else pnl,end_equity=None if unknown else 5000.+pnl,
            signals=count+skip,taken=count,skipped=skip,open_taken=opened,closed_taken=closed,
            status='carry_unverified' if sid in carry else 'mark_unavailable' if unknown else 'prospective' if count else 'no_entries',
            prospective_start_utc=births[sid],actual_fill_quantities=True,portfolio_combinable=False,
            short_locate_verified=False,borrow_fees='estimated, not verified',family=g.SPECS[sid].family,
            accounting='actual paired fills, commissions and estimated borrow; daily equal-start $5k')
        diagnostics['entries']+=count;diagnostics['closes']+=closed;diagnostics['rejected']+=skip
    diagnostics['carry_unverified']=len(carry)
    return modules,diagnostics
