"""Read-only G11 runtime, accounting, population and historical-prefix gates."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
from strategies import generation_eleven as g
from strategies import generation_eleven_retirement as retirement
from strategies.output_switches import output_enabled
from generation_eleven_paper_tracker import FILE_STEM, source_hashes
from research_tools.g11.activate import prefix


def inspect(root='/data', allow_warmup=False, expected_revision=None, check_processes=False):
    root=Path(root);errors=[];activation=retirement.require_activation(root)
    status=json.loads((root/(FILE_STEM+'_status.json')).read_text())
    births=json.loads((root/(FILE_STEM+'_births.json')).read_text())
    manifest=json.loads((root/(FILE_STEM+'_manifest.json')).read_text())
    if set(births)!=g.IDS or manifest.get('births')!=births:errors.append('G11 birth population mismatch')
    if manifest.get('sources')!=source_hashes() or manifest.get('population_hash')!=g.POPULATION_HASH:errors.append('G11 frozen source mismatch')
    if len(manifest.get('specs',[]))!=722:errors.append('G11 missing executable specs')
    if status.get('source_hashes')!=source_hashes():errors.append('G11 runtime source mismatch')
    if status.get('paper_only') is not True or status.get('broker_execution_enabled') is not False:errors.append('G11 paper contract')
    if (root/(FILE_STEM+'_error.json')).exists():errors.append('G11 latched execution error')
    if not all(output_enabled(s) for s in retirement.plan()['parents']):errors.append('Parent disabled')
    if any(output_enabled(s) for s in retirement.plan()['retired_report_ids']):errors.append('Retired output re-enabled')
    if not all(output_enabled(s) for s in g.IDS):errors.append('G11 output disabled')
    for name,r in activation['verified_prefixes'].items():
        if prefix(root/name,r['bytes'])!=r['sha256']:errors.append('Historical ledger prefix changed: '+name)
    days=activation.get('verified_historical_days',{})
    if days:
        current=json.loads((root/'all_engine_bidask_daily_history.json').read_text())['days']
        for day,digest in days.items():
            if day not in current or hashlib.sha256(json.dumps(current[day],sort_keys=True,separators=(',',':')).encode()).hexdigest()!=digest:
                errors.append('Historical finalized day changed: '+day)
    live=json.loads((root/'all_engine_performance_live.json').read_text())
    expected=set(retirement.plan()['parents'])|{sid+'BA' for sid in g.IDS}
    fresh=set(live['modules'])==expected
    if not fresh and not allow_warmup:errors.append('Reporting population differs from exact 734 expected outputs')
    if live.get('diagnostics',{}).get('generation_eleven',{}).get('error'):errors.append('G11 reporting error')
    ledger=root/(FILE_STEM+'_outcomes.jsonl');events={};observed=set();sequence=0
    with ledger.open() if ledger.exists() else open('/dev/null') as f:
        for line in f:
            r=json.loads(line);sequence+=1
            if r.get('sequence')!=sequence:errors.append('G11 broken ledger sequence');break
            if r.get('event')=='OBSERVE':observed.update(r['observations'])
            sid=r.get('strategy_id')
            if sid is not None:
                if sid not in g.IDS or r['timestamp']<births[sid]:errors.append('G11 unknown or prebirth event')
                events.setdefault(sid,{});events[sid][r['event']]=events[sid].get(r['event'],0)+1
    if not allow_warmup and observed!=g.IDS:errors.append('Not all 722 accounts have observed their data path yet')
    runner=[]
    if check_processes:
        for proc in Path('/proc').glob('[0-9]*'):
            try:
                command=(proc/'cmdline').read_bytes().split(b'\0')
                if not any(part.endswith(b'live_strategy_runner.py') for part in command):continue
                fields={}
                for field in (proc/'environ').read_bytes().split(b'\0'):
                    key,sep,value=field.partition(b'=')
                    if sep and key in {b'ENABLE_G11_PAPER',b'G11_BUILD_REVISION'}:fields[key.decode()]=value.decode()
                runner.append(dict(pid=int(proc.name),settings=fields))
            except OSError:continue
        if not any(r['settings'].get('ENABLE_G11_PAPER')=='1' for r in runner):errors.append('Enabled G11 runner absent')
        now=datetime.now(timezone.utc);et=now.astimezone(g.NY)
        if et.weekday()<5 and 570<=et.hour*60+et.minute<960 and (now-g.timestamp(status['updated_at'])).total_seconds()>180:
            errors.append('G11 runtime heartbeat stale during regular market')
    revision=os.environ.get('G11_BUILD_REVISION')
    if expected_revision is not None and revision!=expected_revision:errors.append('Deployed build revision differs from tested commit')
    return dict(errors=errors,revision=revision,runner=runner,preserved_active=sum(output_enabled(s) for s in retirement.plan()['parents']),
                original_retired=sum(not output_enabled(s) for s in retirement.plan()['retired_report_ids']),
                g11_active=sum(output_enabled(s) for s in g.IDS),expected_active_total=734,
                reported_active_total=len(live['modules']),report_population_verified=fresh,
                known_births=len(births),observed_modules=len(observed),modules_with_outcomes=len(events),
                recorded_opens=sum(v.get('OPEN',0) for v in events.values()),
                recorded_closes=sum(v.get('FILL',0) for v in events.values()),
                execution_sequence=sequence,source_hashes_verified=manifest.get('sources')==source_hashes(),
                accounting_status='independent cumulative paper cash; no historical backfill',status=status.get('execution_version'),
                paper_only=True,production_trade_evidence='actual ledger events only; simulated test trades excluded')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',default='/data');p.add_argument('--allow-warmup',action='store_true');p.add_argument('--expected-revision');a=p.parse_args()
    r=inspect(a.root,a.allow_warmup,expected_revision=a.expected_revision,check_processes=True);print(json.dumps(r,indent=2));raise SystemExit(bool(r['errors']))
