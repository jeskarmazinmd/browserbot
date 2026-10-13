"""Read-only G8 verification; never construct trackers or modify provenance."""
import argparse,hashlib,json,os
from pathlib import Path
from datetime import datetime,timezone
from collections import defaultdict
from strategies import generation_eight as g,registry
from strategies.generation_eight_retirement import report_ids
from strategies.output_switches import output_enabled
from executable_paper_engine import executable_mark
from research_tools.g8.preflight import inspect
from research_tools.g8.preserve import prefix
from generation_eight_paper_tracker import FILE_STEM

def verify(root='/data',repo='/app',expected_revision=None,allow_warmup=False):
    root=Path(root);repo=Path(repo);preflight=inspect(root,repo,expected_revision);errors=list(preflight['errors']);pending=[]
    def load(p):
        try:return json.loads(p.read_text())
        except (OSError,ValueError):errors.append('Missing/corrupt '+p.name);return {}
    birth=load(root/(FILE_STEM+'_births.json'));manifest=load(root/(FILE_STEM+'_manifest.json'));status=load(root/(FILE_STEM+'_status.json'))
    if set(birth)!=g.ALL_IDS:errors.append('G8 birth population mismatch')
    if birth and min(birth.values())<g.CREATED_UTC:errors.append('G8 birth before approval')
    if manifest.get('population_hash')!=g.POPULATION_HASH or manifest.get('rule_source_sha256')!=g.RULE_SOURCE_SHA256:errors.append('G8 source/provenance mismatch')
    ids=[s.name for s in registry.MINUTE_STRATEGIES if s.name in g.ALL_IDS]
    if len(ids)!=120 or set(ids)!=g.ALL_IDS or registry.FAILED_STRATEGIES:errors.append('G8 registry incomplete')
    if len(report_ids())!=26 or any(output_enabled(s) for s in report_ids()):errors.append('Approved retirement gates incomplete')
    if any(not output_enabled(s) or not output_enabled(s+'BA') for s in g.ALL_IDS):errors.append('G8 output unexpectedly disabled')
    for key,value in [('broker_execution_enabled',False),('live_order_placement',False),('historical_backfill_enabled',False),('known_births',120),('quote_freshness_enforced',True),('displayed_liquidity_enforced',True),('displayed_participation',.1)]:
        if status.get(key)!=value:errors.append('G8 status mismatch: '+key)
    for p in preflight['processes']:
        for flag in ('ENABLE_G8_PAPER','ENABLE_G8_RETIREMENTS'):
            if p['selected_environment'].get(flag)!='1':errors.append('Runtime flag not active: '+flag)
    hashes=load(repo/'GENERATION_EIGHT_RUNTIME_HASHES.json')
    for name,digest in hashes.items():
        p=repo/name
        if not p.exists() or hashlib.sha256(p.read_bytes()).hexdigest()!=digest:errors.append('Deployed source differs: '+name)
    events=defaultdict(int);remaining={};used={};entry={};realized={};cash={};active={};ledger=root/(FILE_STEM+'_outcomes.jsonl')
    if not ledger.exists():errors.append('Missing G8 ledger')
    else:
        for ln,line in enumerate(ledger.open(),1):
            try:
                r=json.loads(line);sid=r['strategy_id'];ev=r['event_type'];events[ev]+=1
                if sid not in g.ALL_IDS or r.get('paper_only') is not True or r.get('broker_execution_enabled') is not False or r.get('live_order_placement') is not False:raise ValueError('ID/paper contract')
                if ev not in {'PAPER_ENTRY','PAPER_EXIT','PAPER_PARTIAL_EXIT'}:continue
                if datetime.fromisoformat(r['signal_timestamp'])<datetime.fromisoformat(birth[sid]):raise ValueError('prebirth fill')
                phase='entry' if ev=='PAPER_ENTRY' else 'exit';when=datetime.fromisoformat(r['entry_timestamp'] if phase=='entry' else r['exit_timestamp']);day=when.astimezone(g.NY).date().isoformat();key=(sid,day)
                if key not in cash:cash[key]=5000.-sum(x['remaining_qty']*x['entry_price'] for x in active.values() if x['strategy_id']==sid)
                setup=r['setup_id'];qty=r['filled_qty'] if phase=='entry' else r['exit_fill_qty'];q=r['execution_evidence'];side='ask' if phase=='entry' else 'bid'
                mark=executable_mark(q,action='BUY' if phase=='entry' else 'SELL',now=when,max_quote_age_ms=1000 if phase=='entry' else 5000)
                if mark['state']!='EXECUTABLE' or mark.get('quote_age_ms',-1)<0:raise ValueError('nonexecutable fill')
                price=r['entry_price'] if phase=='entry' else r['exit_fill_price']
                if abs(price-q[side])>1e-6:raise ValueError('not ask/bid')
                b=r['book_consumption'];bk=(b['key'],tuple(b['identity']));old=used.get(bk,0)
                if b['used']!=old+qty or b['used']>int(float(q.get(side+'_size_raw',q.get(side+'_size',0)))*.1):raise ValueError('liquidity reuse/participation')
                used[bk]=b['used']
                if phase=='entry':
                    if setup in entry or r['notional']>1000.00001:raise ValueError('entry duplication/notional')
                    if any(v['strategy_id']==sid and v['symbol']==r['symbol'] for v in active.values()):raise ValueError('symbol concentration')
                    remaining[setup]=qty;entry[setup]=r;realized[setup]=0.;cash[key]-=r['notional'];active[setup]=r
                    open_risk=sum(v['remaining_qty']*(v['entry_price']-v['stop_price']) for v in active.values() if v['strategy_id']==sid)
                    equity=cash[key]+sum(v['remaining_qty']*v['entry_price'] for v in active.values() if v['strategy_id']==sid)
                    if qty*(r['entry_price']-r['stop_price'])>equity*.01+1e-6 or open_risk>equity*.02+1e-6 or r['notional']>equity*.2+1e-6:raise ValueError('nominal risk/symbol cap')
                else:
                    if setup not in entry or qty>remaining[setup]:raise ValueError('orphan/duplicate exit')
                    remaining[setup]-=qty;realized[setup]+=r['exit_fill_proceeds'];cash[key]+=r['exit_fill_proceeds']
                    if remaining[setup]!=r['remaining_qty'] or abs(realized[setup]-r['realized_proceeds'])>1e-6:raise ValueError('residual/proceeds mismatch')
                    if ev=='PAPER_EXIT':active.pop(setup,None)
                    else:active[setup]=r
                if cash[key]<-1e-6:raise ValueError('negative cash')
            except (ValueError,KeyError,TypeError) as exc:errors.append(f'G8 row {ln}: {exc}')
    locator=load(root/'g8_preservation_latest.json');preserved=load(Path(locator.get('directory','/missing'))/'preservation_manifest.json')
    for name,record in preserved.get('ledger_prefixes',{}).items():
        try:
            if prefix(root/name,record['bytes'])!=record['sha256']:errors.append('Historical ledger prefix changed: '+name)
        except (OSError,ValueError):errors.append('Historical ledger missing/truncated: '+name)
    history=load(root/'all_engine_bidask_daily_history.json')
    for day,digest in preserved.get('historical_day_hashes',{}).items():
        row=history.get('days',{}).get(day)
        if row is None or hashlib.sha256(json.dumps(row,sort_keys=True,separators=(',',':')).encode()).hexdigest()!=digest:errors.append('Finalized historical snapshot changed: '+day)
    l1=load(root/'live_l1_snapshot.json');missing=sorted(g.SYMBOLS-set(l1.get('quotes',{})))
    if missing:pending.append('Quote coverage not yet complete: '+','.join(missing))
    observations=load(root/(FILE_STEM+'_observations.json'))
    observed={sid:sum(v.get('evaluated_minutes',0) for v in observations.get(sid,{}).values()) for sid in g.ALL_IDS}
    if any(v==0 for v in observed.values()):pending.append('Prospective minute evaluation pending market/session warmup')
    report=load(root/'all_engine_performance_live.json')
    if report.get('calculation_version')!=4 or 'generation_eight' not in report.get('diagnostics',{}):pending.append('Reporter refresh pending')
    if not allow_warmup:errors.extend(pending)
    return dict(checked_utc=datetime.now(timezone.utc).isoformat(),errors=errors,pending=pending,build_revision=expected_revision,
                registered=len(ids),known_births=len(birth),retirement_outputs=len(report_ids()),ledger_events=dict(events),
                earliest_birth=min(birth.values()) if birth else None,latest_birth=max(birth.values()) if birth else None,
                required_quote_symbols=len(g.SYMBOLS),missing_quote_symbols=missing,evaluated_minutes=observed,
                reporter_version=report.get('calculation_version'),preflight=preflight,
                note='Passing structural checks with pending warmup is not evidence of profitable or filled strategies.')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--expected-revision',required=True);p.add_argument('--allow-warmup',action='store_true');a=p.parse_args()
    r=verify(expected_revision=a.expected_revision,allow_warmup=a.allow_warmup);print(json.dumps(r,indent=2));raise SystemExit(bool(r['errors']))
