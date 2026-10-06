"""Exact JSON history metrics, evidence ages, overlap, and retirement review."""
import argparse
import json
import statistics
from collections import defaultdict
from datetime import date
from pathlib import Path
from research_tools.g3_review.analyze import summarize, write_csv, pair_stats

def run(data,out):
    h=json.loads((data/'all_engine_bidask_daily_history.json').read_text())['days']
    live=json.loads((data/'all_engine_performance_live.json').read_text())
    if live['as_of'] >= h.get(live['day'],{}).get('as_of',''):
        h[live['day']]=live
    dates=sorted(d for d in h if date.fromisoformat(d).weekday()<5)
    ids=sorted({sid for day in h.values() for sid in day['modules']})
    rows=[];paths={}
    for sid in ids:
        daily={d:h[d]['modules'].get(sid,{}).get('return_pct') for d in dates}
        paths[sid]=daily
        own=[h[d]['modules'][sid] for d in dates if sid in h[d]['modules']]
        occupied=[d for d in dates if sid in h[d]['modules']]
        row={'module':sid,'engine':own[-1]['engine'] if own else None,
             'first_recorded_day':occupied[0] if occupied else None,
             'last_recorded_day':occupied[-1] if occupied else None,
             'reported_taken':sum(r.get('taken',0) for r in own),
             'reported_skipped':sum(r.get('skipped',0) for r in own),
             'currently_ranked':sid in live['modules'],
             **summarize(list(daily.values()))}
        row.update({'last5_'+k:v for k,v in summarize([daily[d] for d in dates[-5:]]).items()})
        row.update({'prior_'+k:v for k,v in summarize([daily[d] for d in dates[:-5]]).items()})
        row['positive_after_removing_best_day']=(row['excluding_best_session_pct'] or 0)>0
        row['research_label']=('no_observed_returns' if not own else
            'very_young' if len(own)<5 else 'sparse' if row['reported_taken']<20 else
            'positive_candidate' if (row['sum_pct'] or 0)>0 else 'negative_candidate')
        rows.append(row)
    rows.sort(key=lambda r:r['sum_pct'] if r['sum_pct'] is not None else -1e99,reverse=True)
    write_csv(out/'all_modules_exact_history.csv',rows)
    write_csv(out/'exact_daily_returns.csv',({'module':sid,**daily} for sid,daily in paths.items()))
    write_csv(out/'full_history_pmid_overlap.csv',({'module':sid,**stats} for sid,daily in paths.items() if (stats:=pair_stats(paths.get('PMIDBA',{}),daily))))
    legacy=json.loads((data/'all_engine_daily_history.json').read_text())['days']
    legacy_rows=[]
    for sid in sorted({s for x in legacy.values() for s in x['modules']}):
        rs=[x['modules'].get(sid,{}).get('return_pct') for d,x in sorted(legacy.items()) if date.fromisoformat(d).weekday()<5]
        legacy_rows.append({'module':sid,'accounting':'legacy_separate_do_not_pool',**summarize(rs)})
    write_csv(out/'legacy_history_separate.csv',legacy_rows)
    from strategies.pruning import DEPENDENCY_PROTECTED_STRATEGY_IDS
    from strategies.output_switches import output_enabled
    candidates=list(__import__('csv').DictReader((out.parent/'audit/recent_all_modules.csv').open()))[299:]
    by_id={r['module']:r for r in rows}
    decisions=[]
    for r in candidates:
        sid=r['module'];base=sid[:-2] if sid.endswith('BA') else sid
        stats=by_id.get(sid,{})
        protected=base in DEPENDENCY_PROTECTED_STRATEGY_IDS or base=='PMID'
        reason=('protected_source_keep_output_and_evaluation' if protected else
                'not_currently_ranked_verify_switches_and_activity' if sid not in live['modules'] else
                'review_pause_new_entries_keep_draining_and_history' if stats.get('reported_taken',0)>=20 and stats.get('observed_sessions',0)>=5 and (stats.get('sum_pct') or 0)<0 and (stats.get('last5_sum_pct') or 0)<0 else
                'insufficient_evidence_keep_pending_review')
        decisions.append({'recent_rank':r['rank'],'module':sid,'base_id':base,
                          'local_default_output_enabled':output_enabled(base,path='/nonexistent/g3-control.json'),
                          'dependency_protected':protected,'decision':reason,
                          **{k:stats.get(k) for k in ['currently_ranked','observed_sessions','reported_taken','sum_pct','last5_sum_pct']}})
    write_csv(out/'retirement_review.csv',decisions)
    (out/'coverage.json').write_text(json.dumps({'dates':dates,'historical_union':len(ids),
        'current_ranked':len(live['modules']),'as_of':live['as_of'],
        'missing_is_not_zero':True,'legacy_pooled':False},indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--data',required=True,type=Path);p.add_argument('--out',required=True,type=Path)
    a=p.parse_args();a.out.mkdir(parents=True,exist_ok=True);run(a.data,a.out)
