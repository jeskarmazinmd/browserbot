"""G10 as-of ledger reporting. Missing/stale observations remain unknown.

Use captured account snapshots, never today's quote to backfill yesterday.
Daily P&L divided by $5k reference; cumulative cash is sized continuously.
"""
import json
from pathlib import Path
from collections import Counter
from datetime import timedelta
from executable_paper_engine import _utc
from strategies import generation_ten as g
from strategies.output_switches import output_enabled
from strategies.pruning import output_is_pruned
from generation_ten_paper_tracker import FILE_STEM


def calculate_generation_ten(root,day,cutoff):
    root=Path(root);cutoff=_utc(cutoff);path=root/(FILE_STEM+'_births.json')
    diag=dict(entries=0,exits=0,rejected=0,unmarked=0)
    if not path.exists():return {},diag
    births=json.loads(path.read_text());accounts={};snapshot_time=None;entries=Counter();exits=Counter();rejects=Counter();last_mutation={}
    ledger=root/(FILE_STEM+'_outcomes.jsonl')
    if ledger.exists():
        with ledger.open() as f:
            sequence=0
            for line in f:
                r=json.loads(line);sequence+=1
                if r['sequence']!=sequence:raise ValueError('G10 report ledger sequence')
                t=_utc(r['timestamp'])
                if t>cutoff:continue
                sid=r.get('strategy_id')
                if sid and (sid not in g.IDS or t<_utc(births[sid])):raise ValueError('G10 report provenance')
                if t.astimezone(g.NY).date().isoformat()!=day:continue
                kind=r['event']
                if kind=='SNAPSHOT':accounts=r['accounts'];snapshot_time=t
                elif kind in {'OPEN','FILL','STATE'}:last_mutation[sid]=r['sequence']
                if kind=='OPEN':entries[sid]+=1
                elif kind=='FILL' and r['final']:exits[sid]+=1
                elif kind=='REJECT':rejects[sid]+=1
                if kind=='SNAPSHOT':
                    for sid in accounts:last_mutation.pop(sid,None)
    # Current-day polling marks expire; historical EOD snapshots must be near 15:55 ET.
    fresh=snapshot_time is not None and cutoff-snapshot_time<=timedelta(minutes=3)
    modules={}
    for sid in sorted(births):
        birth=_utc(births[sid])
        if sid not in g.IDS or birth>cutoff or birth.astimezone(g.NY).date().isoformat()>day:continue
        if not output_enabled(sid) or not output_enabled(sid+'BA') or output_is_pruned(sid):continue
        candidate=accounts.get(sid,{})
        # A flat account observed after EOD has no quote-dependent value left.
        flat_eod=(snapshot_time is not None and snapshot_time.astimezone(g.NY).hour*60+snapshot_time.astimezone(g.NY).minute>=955 and candidate.get('open_positions')==0)
        a=candidate if (fresh or flat_eod) and sid not in last_mutation else {}
        pnl=a.get('daily_pnl');unknown=pnl is None
        status=a.get('status','observation_unavailable')
        if pnl==0 and entries[sid]==0 and a.get('open_positions')==0:status='no_trades'
        modules[sid+'BA']=dict(engine='generation_ten_bidask_independent',return_pct=None if unknown else pnl/50,
            pnl=pnl,starting_cash=5000.,end_equity=a.get('equity'),signals=entries[sid]+rejects[sid],
            taken=entries[sid],skipped=rejects[sid],closed_taken=exits[sid],open_taken=a.get('open_positions'),
            status=status,prospective_start_utc=births[sid],
            cumulative_return_pct=a.get('cumulative_return_pct'),max_drawdown_pct=a.get('max_drawdown_pct'),
            drawdown_incomplete=a.get('drawdown_incomplete',True),family=g.SPECS[sid].family,
            snapshot_time=snapshot_time.isoformat() if snapshot_time else None,
            actual_fill_quantities=True,paper_only=True,broker_execution_enabled=False,portfolio_combinable=False,
            accounting='cumulative cash; daily equity change / $5000 reference; assumed commissions and adverse slippage')
        diag['entries']+=entries[sid];diag['exits']+=exits[sid];diag['rejected']+=rejects[sid];diag['unmarked']+=unknown
    return modules,diag
