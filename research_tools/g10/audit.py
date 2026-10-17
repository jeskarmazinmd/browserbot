"""Read-only source-ledger research audit. No hindsight fills or configuration selection."""
import argparse
from collections import Counter,defaultdict
from datetime import datetime
import hashlib
import json
from pathlib import Path
import statistics
from strategies import generation_ten as g
from strategies.generation_three import CATALOG as G3_CATALOG
from executable_paper_engine import _utc
from generation_ten_paper_tracker import FILE_STEM


def summary(values):
    if not values:return dict(trades=0,net_pnl=None,win_rate=None,profit_factor=None,payoff_ratio=None)
    wins=[v for v in values if v>0];loss=[v for v in values if v<0]
    return dict(trades=len(values),net_pnl=sum(values),win_rate=len(wins)/len(values),
        profit_factor=sum(wins)/-sum(loss) if loss else None,
        payoff_ratio=statistics.mean(wins)/-statistics.mean(loss) if wins and loss else None,
        mean_trade=statistics.mean(values),median_trade=statistics.median(values))


def rows(path):
    if not path.exists():return
    with path.open() as f:
        for n,line in enumerate(f,1):
            try:yield json.loads(line)
            except ValueError as e:raise ValueError(f'{path.name}: malformed line {n}') from e


def parent_audit(root):
    root=Path(root);path=root/'paper_generation_three_bidask_independent_outcomes.jsonl'
    if not path.exists():return dict(status='production ledger unavailable; no historical validation performed')
    parent='G3MPR150';entries={};exits={};fingerprints=defaultdict(set);rejects=Counter();duplicate=0
    for r in rows(path):
        sid=r.get('strategy_id');event=r.get('event_type');setup=r.get('setup_id')
        if event=='PAPER_ENTRY':
            stamp=r.get('signal_timestamp',r.get('timestamp'))
            if stamp:fingerprints[sid].add((r.get('symbol'),_utc(stamp).replace(second=0,microsecond=0).isoformat()))
            if sid==parent:
                duplicate+=setup in entries;entries[setup]=r
        if sid!=parent:continue
        if event=='PAPER_EXIT':
            duplicate+=setup in exits;exits[setup]=r
        elif event=='PAPER_ENTRY_REJECTED':rejects[r.get('reason','unknown')]+=1
    trades=[];byday=defaultdict(float);bysymbol=defaultdict(float);holds=[];arithmetic=0;missing_evidence=0;notional=0.;stress={str(v):0. for v in [1,3,5,10]}
    for setup,c in exits.items():
        e=entries.get(setup)
        if not e:continue
        qty=g.num(e.get('filled_qty'));entry=g.num(e.get('entry_price'));exitprice=g.num(c.get('exit_price'));pnl=g.num(c.get('pnl'))
        if None in (qty,entry,exitprice,pnl):continue
        arithmetic+=abs((exitprice-entry)*qty-pnl)>1e-5
        missing_evidence+=not bool(e.get('execution_evidence'))
        when=_utc(c['exit_timestamp']);opened=_utc(e['entry_timestamp']);holds.append((when-opened).total_seconds()/60)
        day=when.astimezone(g.NY).date().isoformat();byday[day]+=pnl;bysymbol[e['symbol']]+=pnl;notional+=entry*qty
        for bps in stress:stress[bps]+=pnl-qty*(entry+exitprice)*float(bps)/10000-max(.01,.005*qty)*2
        trades.append(dict(setup_id=setup,symbol=e['symbol'],entered_at=e['entry_timestamp'],exited_at=c['exit_timestamp'],
            quantity=qty,entry_price=entry,exit_price=exitprice,pnl=pnl,exit_reason=c.get('exit_reason'),
            entry_quote_age_ms=e.get('entry_quote_age_ms'),entry_bid=e.get('entry_bid'),entry_ask=e.get('entry_ask'),
            pre_return_pct=e.get('pre_return_pct'),pre_r2=e.get('pre_r2'),flash_drop_pct=e.get('original_flash_drop_pct',e.get('flash_drop_pct'))))
    reference=fingerprints[parent];overlap=[]
    for sid,fp in fingerprints.items():
        if sid==parent:continue
        common=len(fp&reference);union=len(fp|reference)
        overlap.append(dict(strategy_id=sid,parent_entry_overlap=common/len(reference) if reference else None,jaccard=common/union if union else None))
    gross_positive=sum(max(0,v) for v in bysymbol.values())
    history_path=root/'all_engine_bidask_daily_history.json';daily=[]
    if history_path.exists():
        history=json.loads(history_path.read_text()).get('days',{})
        daily=[dict(day=d,return_pct=history[d].get('modules',{}).get(g.PARENT,{}).get('return_pct')) for d in sorted(history)]
    dates=sorted(byday);n=len(dates);a=max(1,int(n*.6));b=max(a+1,int(n*.8))
    splits=dict(discovery=dates[:a],validation=dates[a:b],test=dates[b:])
    return dict(parent=g.PARENT,ledger_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        status='recorded forward fills audited; not a quote-path backtest',**summary([x['pnl'] for x in trades]),
        entries=len(entries),open_unresolved=len(set(entries)-set(exits)),duplicate_records=duplicate,
        pnl_arithmetic_errors=arithmetic,entries_without_full_quote_evidence=missing_evidence,
        by_close_day=dict(sorted(byday.items())),by_symbol=dict(sorted(bysymbol.items(),key=lambda x:-x[1])),
        largest_positive_symbol_share=max((max(0,v) for v in bysymbol.values()),default=0)/gross_positive if gross_positive else None,
        pnl_excluding_best_day=sum(byday.values())-max(byday.values()) if byday else None,
        median_hold_minutes=statistics.median(holds) if holds else None,rejection_reasons=dict(rejects),
        fixed_path_extra_cost_sensitivity_pnl=stress,daily_reported_returns=daily,
        chronological_evidence_partitions=splits,
        chronological_validation='descriptive only; no variant selection or out-of-sample claim from a parent-selected sample',
        most_overlapping_g3_entries=sorted(overlap,key=lambda x:-(x['jaccard'] or 0))[:20],
        individual_trades=trades,
        limitations=['Legacy G3 ledgers do not establish commissions, impact, queue priority or intrapoll stop fills.',
            'Fixed-path cost stress holds historical quantity and exit times constant; not an executable backtest.',
            'Sibling overlap is same-symbol/same-minute entry overlap, not proof of identical trades.',
            'All days used to select this parent are discovery data; future sessions are the untouched test.',
            'No chronological quote-path dataset is supplied; variant net returns, walk-forward selection, or statistical significance are not established.'])


def challenger_audit(root):
    root=Path(root);path=root/(FILE_STEM+'_outcomes.jsonl');trades={};closed=defaultdict(list);reasons=defaultdict(Counter);turnover=Counter();symbols=defaultdict(Counter);latest={};snap_time=None;observations={}
    for r in rows(path):
        sid=r.get('strategy_id');kind=r['event']
        if kind=='OPEN':
            trades[r['setup_id']]=dict(net=-r['entry_fee'],sid=sid,symbol=r['symbol'],timestamp=r['timestamp'])
            turnover[sid]+=r['entry_price']*r['filled_qty'];symbols[sid][r['symbol']]+=r['entry_price']*r['filled_qty']
        elif kind=='FILL':
            t=trades[r['setup_id']];t['net']+=r['pnl']
            if r['final']:closed[sid].append(t['net'])
        elif kind=='REJECT':reasons[sid][r['reason']]+=1
        elif kind=='SNAPSHOT':latest=r['accounts'];snap_time=r['timestamp']
        elif kind=='OBSERVE':observations.update(r['observations'])
    history_path=root/'all_engine_bidask_daily_history.json'
    history=json.loads(history_path.read_text()).get('days',{}) if history_path.exists() else {}
    live_path=root/'all_engine_performance_live.json'
    if live_path.exists():
        live=json.loads(live_path.read_text())
        if live.get('day'):history[live['day']]=live
    def comparison(sid,other):
        pairs=[]
        for d in sorted(history):
            modules=history[d].get('modules',{})
            a=modules.get(sid+'BA',{}).get('return_pct');b=modules.get(other,{}).get('return_pct')
            if a is not None and b is not None:pairs.append((a,b))
        x=[a for a,b in pairs];y=[b for a,b in pairs]
        corr=None
        if len(pairs)>=3 and statistics.pstdev(x)>0 and statistics.pstdev(y)>0:
            corr=sum((a-statistics.mean(x))*(b-statistics.mean(y)) for a,b in pairs)/len(pairs)/statistics.pstdev(x)/statistics.pstdev(y)
        return dict(paired_days=len(pairs),paired_excess_sum_pct=sum(a-b for a,b in pairs) if pairs else None,day_return_correlation=corr)
    fingerprints=defaultdict(set)
    for t in trades.values():fingerprints[t['sid']].add((t['symbol'],_utc(t['timestamp']).replace(second=0,microsecond=0).isoformat()))
    parent_entries=set()
    for r in rows(root/'paper_generation_three_bidask_independent_outcomes.jsonl'):
        if r.get('strategy_id')=='G3MPR150' and r.get('event_type')=='PAPER_ENTRY':
            parent_entries.add((r['symbol'],_utc(r['signal_timestamp']).replace(second=0,microsecond=0).isoformat()))
    result={}
    for sid in sorted(g.IDS):
        a=latest.get(sid,{})
        result[sid]=dict(family=g.SPECS[sid].family,hypothesis=g.SPECS[sid].hypothesis,
            **summary(closed[sid]),account=a,entry_turnover=turnover[sid],
            symbol_notional=dict(symbols[sid]),rejection_reasons=dict(reasons[sid]),
            scanner_observation=observations.get(sid),snapshot_time=snap_time,
            parent_comparison=comparison(sid,g.PARENT),common_execution_control_comparison=comparison(sid,'G10ENTRY01BA'),
            parent_same_symbol_minute_entry_overlap=len(fingerprints[sid]&parent_entries)/len(fingerprints[sid]) if fingerprints[sid] else None)
    return dict(modules=result,comparison_policy='G10ENTRY01 controls for common costs, liquidity and capital; unchanged legacy parent is a secondary benchmark.',
        uncertainty='200 correlated hypotheses; no promotion from maximum observed return. Require untouched prospective periods and cost stress; evaluate families before individual winners.')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',default='/data');p.add_argument('--parent',action='store_true');a=p.parse_args()
    print(json.dumps(parent_audit(a.root) if a.parent else challenger_audit(a.root),indent=2))
