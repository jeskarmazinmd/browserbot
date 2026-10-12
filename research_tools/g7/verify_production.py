"""Read-only G7 deployment verification. Never creates trackers or provenance."""
import argparse,hashlib,json,os
from pathlib import Path
from datetime import datetime,timezone
from strategies import registry,generation_seven as g
from strategies.output_switches import output_enabled
from generation_seven_paper_tracker import FILE_STEM

def prefix_matches(path,record):
 if not path.exists():return False
 digest=hashlib.sha256();remaining=record['bytes']
 with path.open('rb') as handle:
  while remaining:
   chunk=handle.read(min(1048576,remaining))
   if not chunk:break
   digest.update(chunk);remaining-=len(chunk)
 return remaining==0 and digest.hexdigest()==record['sha256']

def verify(root='/data',repo='/app',expected_revision=None):
 root=Path(root);repo=Path(repo);errors=[]
 def read(name):
  p=root/name
  if not p.exists():errors.append('missing '+name);return {}
  try:return json.loads(p.read_text())
  except ValueError:errors.append('corrupt '+name);return {}
 births=read(FILE_STEM+'_births.json');manifest=read(FILE_STEM+'_manifest.json');status=read(FILE_STEM+'_status.json');observations=read(FILE_STEM+'_observations.json')
 if set(births)!=g.ALL_IDS:errors.append('G7 birth population mismatch')
 if manifest.get('population_hash')!=g.POPULATION_HASH or manifest.get('rule_source_sha256')!=g.RULE_SOURCE_SHA256 or manifest.get('parent_sources')!=g.SOURCE_HASHES:errors.append('G7 immutable manifest mismatch')
 ids=[s.name for s in registry.MINUTE_STRATEGIES if s.name in g.ALL_IDS]
 if len(ids)!=len(g.ALL_IDS) or set(ids)!=g.ALL_IDS:errors.append('G7 registrations incomplete or duplicated')
 if registry.FAILED_STRATEGIES:errors.append('registry load failures')
 if any(not output_enabled(sid) or not output_enabled(sid+'BA') for sid in g.ALL_IDS):errors.append('G7 output disabled')
 for key,value in [('broker_execution_enabled',False),('quote_freshness_enforced',True),('displayed_liquidity_enforced',True),('historical_backfill_enabled',False),('known_births',len(g.ALL_IDS)),('population_hash',g.POPULATION_HASH)]:
  if status.get(key)!=value:errors.append('G7 status mismatch: '+key)
 observed={sid:sum(r.get('evaluated_minutes',0) for r in observations.get(sid,{}).values()) for sid in g.ALL_IDS}
 if any(v<1 for v in observed.values()):errors.append('G7 evaluation not yet observed; wait for a current market minute')
 ledger=root/(FILE_STEM+'_outcomes.jsonl');events={};first=last=None
 if not ledger.exists():errors.append('missing G7 ledger')
 else:
  for n,line in enumerate(ledger.open(),1):
   try:
    r=json.loads(line);sid=r['strategy_id'];event=r['event_type'];events[event]=events.get(event,0)+1
    if sid not in g.ALL_IDS:raise ValueError('unknown ID')
    when=r.get('recorded_at');first=first or when;last=when
    if event in ('PAPER_ENTRY','PAPER_PARTIAL_EXIT','PAPER_EXIT'):
     if datetime.fromisoformat(r['signal_timestamp'])<datetime.fromisoformat(births[sid]):raise ValueError('prebirth fill')
     if r.get('broker_execution_enabled') is not False or r.get('paper_only') is not True:raise ValueError('paper contract')
   except (KeyError,ValueError,TypeError) as exc:errors.append(f'G7 ledger row {n}: {exc}')
 expected_path=repo/'GENERATION_SEVEN_RUNTIME_HASHES.json';mismatches=[]
 if not expected_path.exists():errors.append('runtime hash manifest missing')
 else:
  for name,digest in json.loads(expected_path.read_text()).items():
   p=repo/name
   if not p.exists() or hashlib.sha256(p.read_bytes()).hexdigest()!=digest:mismatches.append(name)
  if mismatches:errors.append('G7 deployed source hash mismatch')
 revision_path=repo/'G7_BUILD_REVISION';revision=revision_path.read_text().strip() if revision_path.exists() else None
 if expected_revision is None or revision!=expected_revision:errors.append('G7 deployment revision not verified')
 roles=('supervisor.py','live_strategy_runner.py','live_quote_collector.py','reporting.all_engine_performance_worker');processes=[]
 selected=('LIVE_ORDER_PLACEMENT_ENABLED','ENABLE_G3_PAPER','ENABLE_G4_PAPER','ENABLE_G5_PAPER','ENABLE_G6_PAPER','ENABLE_G7_PAPER')
 for p in Path('/proc').glob('[0-9]*'):
  try:
   args=(p/'cmdline').read_bytes().split(b'\0');found=[r for r in roles if any(Path(a.decode(errors='replace')).name==r for a in args)]
   if not found:continue
   env={}
   for item in (p/'environ').read_bytes().split(b'\0'):
    key,sep,value=item.partition(b'=')
    if sep and key.decode(errors='replace') in selected:env[key.decode()]=value.decode(errors='replace')
   processes.append(dict(pid=int(p.name),roles=found,selected_environment=env))
  except OSError:continue
 for role in roles:
  found=[p for p in processes if role in p['roles']]
  if not found:errors.append('missing running '+role)
  if role in ('live_strategy_runner.py','supervisor.py'):
   for p in found:
    if p['selected_environment'].get('LIVE_ORDER_PLACEMENT_ENABLED')!='0':errors.append(role+' live orders not confirmed disabled')
    if any(p['selected_environment'].get('ENABLE_G'+str(n)+'_PAPER')!='1' for n in range(3,8)):errors.append(role+' generation activation differs from intended G3-G7 flags')
 latest=read('all_engine_performance_live.json')
 if 'generation_seven' not in latest.get('diagnostics',{}):errors.append('G7 reporter not yet refreshed')
 history_prefixes={}
 evidence_path=Path(__file__).with_name('evidence_manifest.json')
 for name,record in json.loads(evidence_path.read_text()).items():
  history_prefixes[name]=prefix_matches(root/name,record)
  if not history_prefixes[name]:errors.append('original ledger prefix differs: '+name)
 from research_tools.g6.verify_production import verify as verify_g6
 previous_generations=verify_g6(root,repo,expected_revision)
 errors.extend('G1-G6 verification: '+e for e in previous_generations['errors'])
 parent_visibility={sid:output_enabled(sid) and output_enabled(sid+'BA') for sid in ('CMDROT1','CMDBRD1')}
 if not all(parent_visibility.values()):errors.append('original parent controls disabled')
 return dict(checked_utc=datetime.now(timezone.utc).isoformat(),errors=errors,build_revision=revision,g7_registered=ids,g7_population=len(g.ALL_IDS),births=births,evaluated_minutes=observed,status=status,ledger_events=events,first_ledger_record=first,last_ledger_record=last,source_mismatches=mismatches,parent_controls=parent_visibility,processes=processes,latest_report_day=latest.get('day'),latest_report_g7_visible=sum(s in latest.get('modules',{}) for s in (sid+'BA' for sid in g.ALL_IDS)),original_ledger_prefixes_unchanged=history_prefixes,previous_generations=previous_generations)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--data-root',default='/data');p.add_argument('--repo',default='/app');p.add_argument('--expected-revision',required=True);a=p.parse_args();r=verify(a.data_root,a.repo,a.expected_revision);print(json.dumps(r,indent=2));raise SystemExit(bool(r['errors']))
