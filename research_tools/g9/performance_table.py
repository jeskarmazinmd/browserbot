"""Permanent active-only numbered terminal table, preserving missing cells."""
import argparse
import json
from pathlib import Path
from strategies.output_switches import output_enabled
from strategies.pruning import output_is_pruned


def table(root='/data',days=5):
    root=Path(root)
    history=json.loads((root/'all_engine_bidask_daily_history.json').read_text())['days']
    live=json.loads((root/'all_engine_performance_live.json').read_text())
    from datetime import date
    selected=sorted(d for d in history if date.fromisoformat(d).weekday()<5)[-days:]
    rows=[]
    from strategies.generation_nine_retirement import enabled,plan
    from generation_nine_paper_tracker import FILE_STEM
    names=set(live['modules'])
    if enabled():names.update(plan()['retained_report_ids'])
    birth=root/(FILE_STEM+'_births.json')
    if birth.exists():names.update(json.loads(birth.read_text()))
    for sid in names:
        base=sid.removesuffix('BA')
        if not output_enabled(sid) or not output_enabled(base) or output_is_pruned(base):continue
        vals=[history[d].get('modules',{}).get(sid,{}).get('return_pct') for d in selected]
        known=[v for v in vals if v is not None]
        rows.append((sid,vals,sum(known) if known else None,len(known)))
    rows.sort(key=lambda x:(x[2] is None,-(x[2] or 0),x[0]))
    fmt=lambda v:'        --' if v is None else f'{v:+10.3f}'
    out=['Reported trading dates: '+', '.join(selected),
         'SUM adds known daily equal-start returns; KNOWN distinguishes missing days. Accounts cannot be combined.',
         f"{'#':>4} {'MODULE':<24}"+''.join(f'{d[5:]:>10}' for d in selected)+f"{'SUM %':>10} {'KNOWN':>6}"]
    for i,(sid,vals,total,n) in enumerate(rows,1):out.append(f'{i:4} {sid:<24}'+''.join(fmt(v) for v in vals)+fmt(total)+f' {n:>3}/{len(selected)}')
    out.append('TOTAL ACTIVE MODULES: '+str(len(rows)))
    return '\n'.join(out)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--days',type=int,default=5);a=p.parse_args();print(table(days=a.days))
