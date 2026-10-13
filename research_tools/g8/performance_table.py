"""Numbered finalized ranking, current provisional column, preserved retired rows."""
import argparse,json,os
from datetime import date
from pathlib import Path
from strategies.output_switches import output_enabled
from strategies.pruning import output_is_pruned

def table(root='/data',last_finalized=4,active_only=False):
    root=Path(root);history=json.loads((root/'all_engine_bidask_daily_history.json').read_text());live=json.loads((root/'all_engine_performance_live.json').read_text())
    days=sorted(d for d in history['days'] if date.fromisoformat(d).weekday()<5)[-last_finalized:]
    names=set(live['modules'])|{s for d in days for s in history['days'][d]['modules']}
    rows=[]
    for sid in names:
        base=sid[:-2] if sid.endswith('BA') else sid
        active=output_enabled(sid) and output_enabled(base) and not output_is_pruned(base)
        if sid.startswith('G8') and os.environ.get('ENABLE_G8_PAPER','0')!='1':active=False
        if active_only and not active:continue
        vals=[history['days'][d]['modules'].get(sid,{}).get('return_pct') for d in days]
        known=[v for v in vals if v is not None]
        total=sum(known) if known else None
        rows.append((sid,active,vals,total,live['modules'].get(sid,{}).get('return_pct')))
    rows.sort(key=lambda r:(r[3] is None,-(r[3] or 0),r[0]))
    lines=['FINALIZED: '+', '.join(days),'LIVE/PROVISIONAL: '+live['day']+' as of '+live['as_of'],
           'Totals sum known equal-start daily returns; missing cells are unknown. Do not aggregate across modules.',
           f"{'#':>4} {'MODULE':<23} {'STATE':<9}"+''.join(f'{d[5:]:>10}' for d in days)+f"{'FIN SUM':>11}{'LIVE*':>11}"]
    fmt=lambda v:'         -' if v is None else f'{v:+9.3f}%'
    for i,(sid,active,vals,total,current) in enumerate(rows,1):lines.append(f"{i:>4} {sid:<23} {'ACTIVE' if active else 'RETIRED':<9}"+''.join(fmt(v) for v in vals)+fmt(total)+fmt(current))
    return '\n'.join(lines)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--last-finalized',type=int,default=4);p.add_argument('--active-only',action='store_true');a=p.parse_args();print(table(last_finalized=a.last_finalized,active_only=a.active_only))
