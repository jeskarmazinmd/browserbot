"""Read-only G4 evidence/coverage and population overlap report.

Run python -m research_tools.g4_review.report --root /data --as-of YYYY-MM-DD.
No historical backfill, retirement, source deletion or broker actions.
"""
import argparse
from collections import defaultdict
from datetime import date,datetime,time
import itertools
import json
from pathlib import Path
import statistics as st
from generation_four_paper_tracker import FILE_STEM
from strategies import generation_four as g4
from strategies.pruning import DEPENDENCY_PROTECTED_STRATEGY_IDS
from .evidence import review

def build(root,as_of):
    cutoff=datetime.combine(date.fromisoformat(as_of),time(),tzinfo=g4.NY)
    births=json.loads((root/(FILE_STEM+'_births.json')).read_text())
    obs_path=root/(FILE_STEM+'_observations.json')
    obs=json.loads(obs_path.read_text()) if obs_path.exists() else {}
    entries={}; residual={}; reasons=defaultdict(lambda:defaultdict(int)); signals=defaultdict(set)
    ledger=root/(FILE_STEM+'_outcomes.jsonl'); malformed=0
    if ledger.exists():
        with ledger.open() as handle:
            for line in handle:
                try:
                    r=json.loads(line); sid=r['strategy_id']; setup=r['setup_id']; event=r['event_type']
                    if sid not in g4.ALL_IDS:continue
                    event_time=g4.timestamp(r.get('exit_timestamp') or r.get('entry_timestamp') or r.get('recorded_at'))
                    signal_time=g4.timestamp(r.get('signal_timestamp'))
                    if event_time is None or signal_time is None or sid not in births:raise ValueError('missing provenance')
                    if event_time>=cutoff or signal_time<g4.timestamp(births[sid]):continue
                    signals[sid].add((r['symbol'],r.get('signal_timestamp')))
                    if event=='PAPER_ENTRY': entries[setup]=r;residual[setup]=r
                    elif event in {'PAPER_EXIT','PAPER_PARTIAL_EXIT'}:residual[setup]=r
                    elif event=='PAPER_ENTRY_REJECTED':reasons[sid][r.get('reason','unknown')]+=1
                except (KeyError,TypeError,ValueError):malformed+=1
    daily=defaultdict(lambda:defaultdict(lambda:dict(pnl=0.,closed=0,open=0)))
    for setup,entry in entries.items():
        r=residual[setup];sid=entry['strategy_id']
        day=g4.timestamp(entry['signal_timestamp']).astimezone(g4.NY).date().isoformat()
        x=daily[sid][day]
        if r['remaining_qty']:x['open']+=1
        else:x['pnl']+=r['realized_proceeds']-entry['notional'];x['closed']+=1
    evidence={}
    for sid,born in births.items():
        if sid not in g4.ALL_IDS:continue
        sessions=[]
        for day,o in obs.get(sid,{}).items():
            x=daily[sid][day]
            # Fixed universe; require nearly a full session of usable decisions.
            # Early closures/partial activation conservatively remain unverified.
            sessions.append(dict(day=day,return_pct=x['pnl']/5000*100,
                                 closed_trades=x['closed'],residual_positions=x['open'],
                                 coverage_verified=o['ready_minutes']>=300 and o['error_minutes']==0 and malformed==0))
        evidence[sid]=dict(birth_date=g4.timestamp(born).astimezone(g4.NY).date().isoformat(),sessions=sessions)
    overlap=[]
    for a,b in itertools.combinations(sorted(signals),2):
        union=signals[a]|signals[b]
        overlap.append(dict(a=a,b=b,signal_jaccard=len(signals[a]&signals[b])/len(union),
                            intersection=len(signals[a]&signals[b]),union=len(union)))
    # Pairwise complete sessions only. Missing dates never become zeros.
    correlations=[]
    for a,b in itertools.combinations(sorted(evidence),2):
        da={r['day']:r['return_pct'] for r in evidence[a]['sessions'] if r['coverage_verified'] and not r['residual_positions']}
        db={r['day']:r['return_pct'] for r in evidence[b]['sessions'] if r['coverage_verified'] and not r['residual_positions']}
        common=sorted(da.keys()&db.keys());xs=[da[d] for d in common];ys=[db[d] for d in common]
        if len(common)>=20 and st.pstdev(xs)>0 and st.pstdev(ys)>0:
            correlations.append(dict(a=a,b=b,complete_common_sessions=len(common),correlation=g4.corr(xs,ys)))
    return dict(as_of=as_of,population_hash=g4.POPULATION_HASH,population=36,
                evidence=evidence,age_review=review(evidence,as_of,protected=DEPENDENCY_PROTECTED_STRATEGY_IDS),
                rejection_reasons={k:dict(v) for k,v in reasons.items()},malformed_ledger_rows=malformed,
                signal_overlap=sorted(overlap,key=lambda r:r['signal_jaccard'],reverse=True),
                daily_return_correlations=correlations,
                note='Paper experiments are separate $5000 daily equal-start portfolios. Do not sum returns across experiments. Current date excluded from retirement review.')

def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--as-of',default=date.today().isoformat());a=p.parse_args()
    print(json.dumps(build(a.root,a.as_of),indent=2))
if __name__=='__main__':main()
