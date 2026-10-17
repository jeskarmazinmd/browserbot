"""Read-only G10 verification. Deployment success requires this command to pass."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
from strategies import generation_ten as g
from generation_ten_paper_tracker import FILE_STEM,source_hashes,EXECUTION_VERSION


def inspect(root='/data',code_root=None,expected_revision=None,allow_warmup=False):
    root=Path(root);code_root=Path(code_root or Path(__file__).resolve().parents[2]);errors=[];now=datetime.now(timezone.utc)
    hashes=code_root/'GENERATION_TEN_RUNTIME_HASHES.json'
    if not hashes.exists():errors.append('G10 runtime source hashes absent')
    else:
        for p,h in json.loads(hashes.read_text()).items():
            if not (code_root/p).exists() or hashlib.sha256((code_root/p).read_bytes()).hexdigest()!=h:errors.append('Runtime hash mismatch: '+p)
    revision=os.environ.get('G10_BUILD_REVISION')
    if expected_revision and revision!=expected_revision:errors.append('Deployed revision mismatch')
    status_path=root/(FILE_STEM+'_status.json');status=json.loads(status_path.read_text()) if status_path.exists() else {}
    error_path=root/(FILE_STEM+'_error.json')
    if error_path.exists():
        fault=json.loads(error_path.read_text())
        if not status.get('updated_at') or fault['timestamp']>=status['updated_at']:errors.append('G10 latched fault: '+fault.get('error_type','unknown'))
    birth_path=root/(FILE_STEM+'_births.json');births=json.loads(birth_path.read_text()) if birth_path.exists() else {}
    mp=root/(FILE_STEM+'_manifest.json');manifest=json.loads(mp.read_text()) if mp.exists() else {}
    if set(births)!=g.IDS:errors.append('G10 birth population mismatch')
    if manifest.get('population_hash')!=g.POPULATION_HASH or manifest.get('sources')!=source_hashes() or manifest.get('births')!=births:errors.append('G10 frozen manifest mismatch')
    if status.get('population')!=200 or status.get('known_births')!=200:errors.append('G10 registration missing')
    if status.get('broker_execution_enabled') is not False or status.get('paper_only') is not True or status.get('shorting_enabled') is not False:errors.append('G10 paper-only contract failed')
    if status.get('execution_version')!=EXECUTION_VERSION:errors.append('Wrong execution version')
    et=now.astimezone(g.NY);regular=et.weekday()<5 and 570<=et.hour*60+et.minute<960
    if not status.get('updated_at') or regular and (now-g.timestamp(status['updated_at'])).total_seconds()>180:errors.append('G10 heartbeat missing/stale')
    # Inspect only allowlisted process settings; never print tokens or arbitrary environment.
    processes=[];worker_commands=set()
    for p in Path('/proc').glob('[0-9]*'):
        try:
            cmd=(p/'cmdline').read_bytes().split(b'\0')
            worker_commands.update(x.decode(errors='replace') for x in cmd)
            if not any(x.endswith(b'live_strategy_runner.py') for x in cmd):continue
            env={}
            for field in (p/'environ').read_bytes().split(b'\0'):
                k,sep,v=field.partition(b'=')
                if sep and k in {b'ENABLE_G10_PAPER',b'G10_BUILD_REVISION'}:env[k.decode()]=v.decode()
            processes.append(dict(pid=int(p.name),settings=env))
        except OSError:continue
    if not processes or not any(p['settings'].get('ENABLE_G10_PAPER')=='1' for p in processes):errors.append('Enabled G10 runner absent')
    required_workers={'live_quote_collector.py','reporting.all_engine_performance_worker','statarb_shadow_worker.py'}
    missing_workers=sorted(required_workers-worker_commands)
    if missing_workers:errors.append('Existing worker absent: '+', '.join(missing_workers))
    from strategies import registry
    if len(g.IDS&registry.flash_strategy_configs().keys())!=200:errors.append('G10 raw scanner registration mismatch')
    report=root/'all_engine_performance_live.json';live=json.loads(report.read_text()) if report.exists() else {}
    if live.get('diagnostics',{}).get('generation_ten',{}).get('error'):errors.append('G10 reporting error')
    reported=sum(sid+'BA' in live.get('modules',{}) for sid in g.IDS)
    if not allow_warmup and reported!=200:errors.append('All-engine report has not published 200 G10 accounts')
    if not allow_warmup and g.PARENT not in live.get('modules',{}):errors.append('Unchanged parent control missing from report')
    return dict(errors=errors,population=200,known_births=len(births),reported_g10=reported,revision=revision,
        expected_revision=expected_revision,runner=processes,missing_existing_workers=missing_workers,legacy_reported_modules=len(live.get('modules',{}))-reported,regular_market=regular,active=status.get('active'),completed=status.get('completed'),
        rejected=status.get('rejected'),rejection_reasons=status.get('rejection_reasons'),
        first_birth=min(births.values()) if births else None,last_birth=max(births.values()) if births else None,
        paper_only=status.get('paper_only'),broker_execution_enabled=status.get('broker_execution_enabled'),
        live_orders_verified=False,live_orders_note='No broker order read/write capability in verifier; compare broker-side evidence separately.',
        checked_at=now.isoformat())


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',default='/data');p.add_argument('--expected-revision');p.add_argument('--allow-warmup',action='store_true');a=p.parse_args()
    result=inspect(a.root,expected_revision=a.expected_revision,allow_warmup=a.allow_warmup)
    print(json.dumps(result,indent=2));raise SystemExit(bool(result['errors']))
