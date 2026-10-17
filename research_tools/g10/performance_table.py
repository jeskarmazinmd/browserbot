"""Permanent read-only active universe table and G10 parent comparison."""
import argparse
from datetime import date
import json
from pathlib import Path
from strategies.output_switches import output_enabled
from strategies.pruning import output_is_pruned
from strategies import generation_ten as g
from generation_ten_paper_tracker import FILE_STEM


def table(root='/data',days=5,g10=False):
    if days<1:raise ValueError('days must be positive')
    root=Path(root)
    hp=root/'all_engine_bidask_daily_history.json';lp=root/'all_engine_performance_live.json'
    history=json.loads(hp.read_text())['days'] if hp.exists() else {}
    live=json.loads(lp.read_text()) if lp.exists() else {}
    history=dict(history)
    # Include today's current report even before the daily archive refresh.
    if live.get('day') and live.get('modules'):history[live['day']]=live
    selected=sorted(d for d in history if date.fromisoformat(d).weekday()<5)[-days:]
    names=set(live.get('modules',{}))
    # Retained IDs and durable births are authoritative inventory when live rows are missing.
    from strategies.generation_nine_retirement import enabled,plan
    if enabled():names.update(plan()['retained_report_ids'])
    for p in root.glob('paper_generation_*_births.json'):
        for sid in json.loads(p.read_text()):
            names.add(sid if sid.startswith('G9') else sid+'BA')
    if g10:names={sid+'BA' for sid in g.IDS}|{g.PARENT}
    rows=[]
    for sid in names:
        base=sid.removesuffix('BA')
        if not output_enabled(sid) or not output_enabled(base) or output_is_pruned(base) or output_is_pruned(sid):continue
        records=[history[d].get('modules',{}).get(sid,{}) for d in selected]
        vals=[r.get('return_pct') for r in records];known=[v for v in vals if v is not None]
        trades=[r.get('taken') for r in records if r.get('taken') is not None]
        dd=live.get('modules',{}).get(sid,{}).get('max_drawdown_pct')
        rows.append((sid,vals,sum(known) if known else None,len(known),sum(trades) if trades else None,dd,records))
    rows.sort(key=lambda r:(r[2] is None,-(r[2] or 0),r[0]))
    cell=lambda v:'        --' if v is None else f'{v:+10.3f}'
    out=['Reported trading dates: '+', '.join(selected),
        'SUM = sum of reported daily returns; accounts are independent. -- missing; NT observed no trades; Z actual zero.',
        f"{'#':>4} {'MODULE':<24}"+''.join(f'{d[5:]:>10}' for d in selected)+f"{'SUM %':>10} {'KNOWN':>6} {'TRADES':>7}"+(f" {'DD %':>8}" if g10 else '')]
    for i,(sid,vals,total,n,trades,dd,recs) in enumerate(rows,1):
        cells=[]
        for v,r in zip(vals,recs):
            if v==0 and r.get('status') in {'no_trades','no_entries'} and r.get('taken',0)==0:cells.append('        NT')
            elif v==0:cells.append('         Z')
            else:cells.append(cell(v))
        out.append(f'{i:4} {sid:<24}'+''.join(cells)+cell(total)+f" {n:>3}/{len(selected):<2} {str(trades) if trades is not None else '--':>7}"+(f" {dd:8.3f}" if dd is not None else '       --' if g10 else ''))
    out.append('TOTAL ACTIVE MODULES: '+str(len(rows)))
    if g10:out.append('Parent is unchanged legacy G3 accounting; G10ENTRY01 is the parent-entry control under G10 costs. DD is observed marked drawdown; see audit for gaps.')
    return '\n'.join(out)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',default='/data');p.add_argument('--days',type=int,default=5);p.add_argument('--g10',action='store_true');a=p.parse_args()
    print(table(a.root,a.days,a.g10))
