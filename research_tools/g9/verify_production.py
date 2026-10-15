"""Read-only G9 structural and paper-execution verification, safe in Fly SSH."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
from generation_nine_paper_tracker import FILE_STEM,source_hashes
from strategies import generation_nine as g
from strategies.generation_nine_retirement import plan
from strategies.output_switches import output_enabled


def inspect(root='/data',allow_warmup=False):
    root=Path(root);errors=[];p=plan()
    repo=Path(__file__).resolve().parents[2]
    hashes=json.loads((repo/'GENERATION_NINE_RUNTIME_HASHES.json').read_text())
    for name,expected in hashes.items():
        if hashlib.sha256((repo/name).read_bytes()).hexdigest()!=expected:errors.append('Runtime hash mismatch: '+name)
    manifest=root/(FILE_STEM+'_manifest.json');birth=root/(FILE_STEM+'_births.json');status=root/(FILE_STEM+'_status.json')
    m=json.loads(manifest.read_text()) if manifest.exists() else {}
    b=json.loads(birth.read_text()) if birth.exists() else {}
    st=json.loads(status.read_text()) if status.exists() else {}
    if m.get('population_hash')!=g.POPULATION_HASH or m.get('sources')!=source_hashes():errors.append('Frozen rule manifest mismatch')
    if set(b)!=g.IDS:errors.append('400 births not present')
    if os.environ.get('ENABLE_G9_RETIREMENTS')!='1':errors.append('G9 retirements not enabled')
    if os.environ.get('ENABLE_G9_PAPER')!='1':errors.append('G9 entries not enabled')
    kept_off=[s for s in p['retained_report_ids'] if not output_enabled(s)]
    retired_on=[s for s in p['retired_report_ids'] if output_enabled(s)]
    if kept_off:errors.append('Retained outputs disabled: '+','.join(kept_off))
    if retired_on:errors.append('Retired outputs enabled: '+','.join(retired_on))
    count={'OPEN':0,'CLOSE':0,'PENDING':0,'REJECT':0};active=set()
    ledger=root/(FILE_STEM+'_outcomes.jsonl')
    if ledger.exists():
        with ledger.open() as handle:
            for line in handle:
                r=json.loads(line);sid=r['strategy_id'];event=r['event'];count[event]+=1
                if sid not in b or g.utc(r['timestamp'])<g.utc(b[sid]):errors.append('Unknown/prebirth G9 event')
                if event=='OPEN':
                    if sid in active:errors.append('Overlapping G9 groups')
                    active.add(sid)
                    if r['gross_notional_used']>1000.000001:errors.append('Oversized G9 group')
                    if r.get('paper_only') is not True or r.get('broker_execution_enabled') is not False:errors.append('G9 paper contract violation')
                    for leg in r['legs']:
                        q=leg['quote'];t=g.utc(r['timestamp']);side='ask' if leg['side']=='LONG' else 'bid'
                        if not g.valid_quote(q,t):errors.append('Invalid entry quote evidence')
                        if leg['shares']>float(q.get(side+'_size_raw',0))*g.SPECS[sid].participation:errors.append('Entry exceeds displayed participation')
                elif event=='CLOSE':active.discard(sid)
    if st.get('population')!=400 or st.get('broker_execution_enabled') is not False:errors.append('G9 status population/paper mismatch')
    worker=root/'statarb_shadow_status.json'
    ws=json.loads(worker.read_text()) if worker.exists() else {}
    regular=ws.get('status')!='WAITING_REGULAR_MARKET'
    if not st.get('updated_at') or (regular and (datetime.now(timezone.utc)-g.utc(st['updated_at'])).total_seconds()>300):errors.append('G9 heartbeat missing/stale')
    if not allow_warmup and regular and ws.get('status')!='RUNNING':errors.append('Statarb worker not running')
    livepath=root/'all_engine_performance_live.json'
    live=json.loads(livepath.read_text()) if livepath.exists() else {}
    modules=live.get('modules',{})
    reported=len(g.IDS & set(modules))
    if not allow_warmup and reported!=400:errors.append('400 G9 accounts not yet reported')
    if not allow_warmup and set(modules)&set(p['retired_report_ids']):errors.append('Retired rows remain in current report')
    return dict(errors=errors,population=400,known_births=len(b),reported_g9=reported,
                retained_disabled=kept_off,retired_enabled=retired_on,events=count,active=len(active),
                worker_status=ws.get('status'),status=st,first_birth=min(b.values()) if b else None,
                last_birth=max(b.values()) if b else None,production_returns_validated=False)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--allow-warmup',action='store_true');a=parser.parse_args()
    r=inspect(allow_warmup=a.allow_warmup);print(json.dumps(r,indent=2));raise SystemExit(bool(r['errors']))
