"""Read-only deployed G6 audit. Never creates trackers, births, or fills."""
import argparse,ast,hashlib,json,os
from pathlib import Path
from datetime import datetime,timezone
from strategies import registry,generation_six as g
from strategies.generation_six_retirement import plan,entry_retired,enabled
from strategies.output_switches import output_enabled
from generation_six_paper_tracker import FILE_STEM

def verify(root='/data',repo='/app',expected_revision=None):
 root=Path(root);repo=Path(repo);p=plan();errors=[]
 raw=set(registry.flash_strategy_configs())|{s.name for s in registry.MINUTE_STRATEGIES}
 modules={s.name for s in registry.MINUTE_STRATEGIES}
 active={sid for sid in raw if output_enabled(sid)}
 births_file=root/(FILE_STEM+'_births.json');status_file=root/(FILE_STEM+'_status.json')
 births=json.loads(births_file.read_text()) if births_file.exists() else {}
 status=json.loads(status_file.read_text()) if status_file.exists() else {}
 if not enabled():errors.append('ENABLE_G6_PAPER is not 1')
 if registry.FAILED_STRATEGIES:errors.append('registry load failures')
 if raw&g.ALL_IDS!=g.ALL_IDS:errors.append('G6 registrations incomplete')
 if len(active&g.ALL_IDS)!=400:errors.append('G6 active output count is not 400')
 if set(births)!=g.ALL_IDS:errors.append('G6 durable birth population incomplete')
 if any(entry_retired(sid) for sid in active):errors.append('retired output still active')
 activation_file=root/'generation_six_activation.json'
 activation=json.loads(activation_file.read_text()) if activation_file.exists() else {}
 if activation.get('retired_report_ids')!=p['retired_report_ids']:errors.append('retirement activation record missing or mismatched')
 for suffix in ('manifest.json','outcomes.jsonl','observations.json','status.json'):
  if not (root/(FILE_STEM+'_'+suffix)).exists():errors.append('missing G6 '+suffix)
 if status.get('population_hash')!=g.POPULATION_HASH or status.get('known_births')!=400:errors.append('G6 status hash/birth mismatch')
 if status.get('broker_execution_enabled') is not False:errors.append('paper broker isolation not confirmed')
 if status.get('quote_freshness_enforced') is not True or status.get('displayed_liquidity_enforced') is not True:errors.append('paper execution safeguards not confirmed')
 selected=os.environ.get('LIVE_ORDER_PLACEMENT_ENABLED')
 if selected!='0':errors.append('live-order environment differs from captured baseline 0')
 # Check all touched runtime files against the reviewed deployment manifest.
 hashes_file=repo/'GENERATION_SIX_RUNTIME_HASHES.json';mismatches=[]
 if hashes_file.exists():
  expected=json.loads(hashes_file.read_text())
  for name,sha in expected.items():
   path=repo/name
   if not path.exists() or hashlib.sha256(path.read_bytes()).hexdigest()!=sha:mismatches.append(name)
  if mismatches:errors.append('deployed source hash mismatch')
 else:errors.append('runtime source manifest missing')
 processes=[]
 roles=('supervisor.py','live_quote_collector.py','live_strategy_runner.py','reporting.all_engine_performance_worker','forex_shadow_worker.py','statarb_shadow_worker.py','short_shadow_worker.py','microstructure_shadow_worker.py')
 for d in Path('/proc').glob('[0-9]*'):
  try:
   args=(d/'cmdline').read_bytes().split(b'\0');found=[r for r in roles if any(Path(a.decode(errors='replace')).name==r for a in args)]
   if found:processes.append(dict(pid=int(d.name),roles=found))
  except OSError:pass
 found={r for d in processes for r in d['roles']}
 if 'live_strategy_runner.py' not in found:errors.append('strategy runner process not found')
 if 'live_quote_collector.py' not in found:errors.append('collector process not found')
 if 'supervisor.py' not in found:errors.append('supervisor process not found')
 native={}
 from strategies.pruning import active_output_ids
 for worker in ('forex','statarb','microstructure','short'):
  path=repo/(worker+'_shadow_worker.py');ids=[]
  for node in ast.walk(ast.parse(path.read_text())):
   if isinstance(node,ast.Assign) and isinstance(node.value,ast.Call) and isinstance(node.value.func,ast.Name) and node.value.func.id=='active_output_ids':
    ids.extend(active_output_ids(ast.literal_eval(node.value.args[0])))
  native[worker]=[sid for sid in ids if output_enabled(sid)]
 native_ids={sid for ids in native.values() for sid in ids}
 latest_path=root/'all_engine_performance_live.json'
 latest=json.loads(latest_path.read_text()) if latest_path.exists() else {}
 retired_visible=set(latest.get('modules',{}))&set(p['retired_report_ids'])
 if retired_visible:errors.append('retired outputs remain in latest performance snapshot (reporter may not have refreshed)')
 if 'generation_six' not in latest.get('diagnostics',{}):errors.append('G6 reporter update not yet verified')
 if 'reporting.all_engine_performance_worker' not in found:errors.append('performance reporter process not found')
 duplicates=len([s.name for s in registry.MINUTE_STRATEGIES])-len(modules)
 if duplicates:errors.append('duplicate minute registration')
 build=repo/'G6_BUILD_REVISION'
 revision=build.read_text().strip() if build.exists() else None
 if not revision or len(revision)!=40 or any(c not in '0123456789abcdef' for c in revision):errors.append('valid deployed git revision marker missing')
 if expected_revision is not None and revision!=expected_revision:errors.append('deployed build revision does not match expected commit')
 return dict(checked_utc=datetime.now(timezone.utc).isoformat(),errors=errors,
  frozen_ranked_modules=498,exact_retired_outputs=400,new_g6_modules=400,
  main_registry_active_outputs=len(active),
  main_plus_four_native_candidate_outputs=len(active|native_ids),native_worker_candidates=native,
  latest_report_module_count=latest.get("module_count"),latest_report_retired_visible=len(retired_visible),
  latest_report_g6_visible=sum(s.startswith("G6") for s in latest.get("modules",{})),main_registry_retained_or_unranked=len(active-g.ALL_IDS),
  g6_flash_registered=len(set(registry.FLASH_STRATEGY_MODULES)&g.IDS),g6_minute_registered=len(modules&g.MINUTE_IDS),
  duplicate_minute_ids=duplicates,registration_failures=registry.FAILED_STRATEGIES,
  retirement_activated_utc=activation.get("activated_utc"),durable_births=len(births),birth_min=min(births.values(),default=None),birth_max=max(births.values(),default=None),
  status=status,deployed_source_mismatches=mismatches,build_revision=revision,
  processes=processes,live_order_flag=selected,
  population_note='Main registry outputs exclude separately configured native workers; historical ranked count is not active registry count.')
if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--data-root',default='/data');parser.add_argument('--repo',default='/app');parser.add_argument('--expected-revision');a=parser.parse_args()
 result=verify(a.data_root,a.repo,a.expected_revision);print(json.dumps(result,indent=2));raise SystemExit(bool(result['errors']))
