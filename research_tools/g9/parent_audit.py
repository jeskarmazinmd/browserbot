"""Read-only current STHEDGE2 ledger audit. No tokens, network, or file writes."""
from collections import Counter,defaultdict
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import statistics


def audit(root='/data'):
    path=Path(root)/'statarb_paper_outcomes.jsonl';opens={};closed=[];bad=0;orphans=0;seen=set();duplicates=0
    if not path.exists():return dict(error='Production statarb ledger unavailable')
    digest=hashlib.sha256()
    with path.open('rb') as handle:
        for raw in handle:
            digest.update(raw)
            try:r=json.loads(raw)
            except ValueError:bad+=1;continue
            if r.get('strategy_id')!='STHEDGE2':continue
            gid=r.get('group_id')
            if r.get('event')=='OPEN':
                if gid in opens:duplicates+=1
                opens[gid]=r
            elif r.get('event')=='CLOSE':
                if gid in seen:duplicates+=1;continue
                seen.add(gid)
                if gid not in opens:orphans+=1;continue
                closed.append((opens[gid],r))
    byday=defaultdict(float);bysymbol=defaultdict(float);reasons=Counter();pnl=[];sizes=[];holds=[];pricing_errors=0;recalc_errors=0
    for e,c in closed:
        profit=float(c['pnl']);pnl.append(profit);sizes.append(e['gross_notional_used'])
        byday[c['closed_at'][:10]]+=profit;reasons[c['exit_reason']]+=1
        bysymbol['+'.join(sorted(x['symbol'] for x in e['legs']))]+=profit
        holds.append((datetime.fromisoformat(c['closed_at'])-datetime.fromisoformat(e['opened_at'])).total_seconds()/60)
        ex={x['symbol']:x for x in c['exit_legs']};calc=0.
        for leg in e['legs']:
            x=ex.get(leg['symbol'])
            if not x:pricing_errors+=1;continue
            long=leg['side']=='LONG';ep=leg['entry_ask'] if long else leg['entry_bid'];xp=x['exit_bid'] if long else x['exit_ask']
            if abs(ep-leg['entry_price'])>1e-8 or abs(xp-x['exit_price'])>1e-8:pricing_errors+=1
            calc+=(1 if long else -1)*(xp-ep)*leg['shares']
        if abs(calc-profit)>1e-6:recalc_errors+=1
    wins=sum(x for x in pnl if x>0);loss=-sum(x for x in pnl if x<0);eq=peak=dd=0.
    for _,c in sorted(closed,key=lambda x:x[1]['closed_at']):
        eq+=c['pnl'];peak=max(peak,eq);dd=max(dd,peak-eq)
    return dict(ledger_sha256=digest.hexdigest(),completed=len(closed),open_groups=len(set(opens)-seen),malformed_lines=bad,orphan_closes=orphans,duplicate_groups=duplicates,
        nominal_pnl=sum(pnl),profit_factor=wins/loss if loss else None,win_rate=sum(x>0 for x in pnl)/len(pnl) if pnl else None,
        mean_pnl=statistics.fmean(pnl) if pnl else None,median_pnl=statistics.median(pnl) if pnl else None,
        mean_gross_notional=statistics.fmean(sizes) if sizes else None,median_hold_minutes=statistics.median(holds) if holds else None,
        nominal_max_drawdown=dd,pricing_errors=pricing_errors,recalculated_pnl_errors=recalc_errors,
        by_close_day=dict(sorted(byday.items())),by_pair=dict(sorted(bysymbol.items(),key=lambda x:-x[1])),exit_reasons=dict(reasons),
        limitations=['Nominal group P&L is not independent $5k portfolio return','No historical per-leg displayed liquidity or borrow/locate proof','Minute polling can skip stops and atomic paired execution is hypothetical'])

if __name__=='__main__':print(json.dumps(audit(),indent=2))
