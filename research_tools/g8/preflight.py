"""Read-only first production inspection. Stdlib-only for execution on baseline."""
import json,os,shutil
from datetime import datetime,timezone
from pathlib import Path

BASELINE='fc22309f399dfb089e135022dc96b0c5abd2e3ee'
RETIRE=('CMDMETMR1','QV4VB608','PT315VU40','G2PGT50','G2PGB1','PMID','C3N25S10NH015LATE','RS2','RS1','G1PGT75','G2PGB2','PT315T75','ARXP3S35','M2','PT315PLOW','PT315H10','G2PGK10','G2PGCTL','G2PGK20','G2PGD4','G2PGE2','G2PGK5','PT315FD200','FXEUR1','G2PGU100','G2PGU200')
SELECTED=('LIVE_ORDER_PLACEMENT_ENABLED','LIVE_STRATEGY_ID','ENABLE_G3_PAPER','ENABLE_G4_PAPER','ENABLE_G5_PAPER','ENABLE_G6_PAPER','ENABLE_G7_PAPER','ENABLE_G8_PAPER','ENABLE_G8_RETIREMENTS','G3_RETIREMENT_PLAN_PATH','STRATEGY_OUTPUT_SWITCHES_PATH')
ROLES=('supervisor.py','live_strategy_runner.py','live_quote_collector.py','reporting.all_engine_performance_worker')

def inspect(root='/data',repo='/app',expected_revision=BASELINE):
    root=Path(root);repo=Path(repo);errors=[];processes=[]
    for proc in Path('/proc').glob('[0-9]*'):
        try:
            args=[x.decode(errors='replace') for x in (proc/'cmdline').read_bytes().split(b'\0')]
            roles=[r for r in ROLES if any(Path(a).name==r for a in args)]
            if not roles:continue
            values={}
            for item in (proc/'environ').read_bytes().split(b'\0'):
                key,sep,value=item.partition(b'=');name=key.decode(errors='replace')
                if sep and name in SELECTED:values[name]=value.decode(errors='replace')
            processes.append(dict(pid=int(proc.name),roles=roles,selected_environment=values))
        except OSError:continue
    for role in ROLES:
        ps=[p for p in processes if role in p['roles']]
        if not ps:errors.append('Missing worker: '+role)
        for p in ps:
            if role in ('supervisor.py','live_strategy_runner.py'):
                if p['selected_environment'].get('LIVE_ORDER_PLACEMENT_ENABLED')!='0':errors.append(role+' real-order placement not explicitly disabled')
                if p['selected_environment'].get('LIVE_STRATEGY_ID','').upper().removesuffix('BA') in RETIRE:errors.append('Retirement overlaps configured live strategy')
    revision_path=repo/('G8_BUILD_REVISION' if (repo/'G8_BUILD_REVISION').exists() else 'G7_BUILD_REVISION')
    revision=revision_path.read_text().strip().replace('\\n','') if revision_path.exists() else None
    if revision not in str(expected_revision).split(','):errors.append('Deployed revision differs from expected baseline/build')
    usage=shutil.disk_usage(root)
    if usage.free<3*1024**3:errors.append('Less than 3GiB preservation/deployment headroom')
    memory={}
    for line in Path('/proc/meminfo').read_text().splitlines():
        key,_,rest=line.partition(':')
        if key in ('MemTotal','MemAvailable'):memory[key]=int(rest.split()[0])
    free_fraction=memory.get('MemAvailable',0)/max(1,memory.get('MemTotal',1))
    load=float(Path('/proc/loadavg').read_text().split()[0]);cpus=os.cpu_count() or 1
    if free_fraction<.20:errors.append('Less than 20% available memory headroom')
    if load/cpus>.80:errors.append('Load pressure exceeds 80% of logical CPU count')
    switches={};path=root/'strategy_output_switches.json'
    if path.exists():
        switches=json.loads(path.read_text())
        if not isinstance(switches,dict):errors.append('Invalid output switches')
    health=json.loads((root/'all_engine_performance_health.json').read_text()) if (root/'all_engine_performance_health.json').exists() else {}
    if health.get('status')!='OK':errors.append('Performance reporter health is not OK')
    if health.get('timestamp'):
        age=(datetime.now(timezone.utc)-datetime.fromisoformat(health['timestamp'])).total_seconds()
        if age>1800:errors.append('Performance reporter heartbeat older than 30 minutes')
    return dict(checked_utc=datetime.now(timezone.utc).isoformat(),build_revision=revision,errors=errors,
                processes=processes,output_switches=switches,reporter_status=health.get('status'),
                reporter_timestamp=health.get('timestamp'),free_gib=round(usage.free/1024**3,2),
                available_memory_pct=round(free_fraction*100,1),logical_cpus=cpus,load_1m=load)

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--expected-revision',default=BASELINE);a=parser.parse_args()
    r=inspect(expected_revision=a.expected_revision);print(json.dumps(r,indent=2));raise SystemExit(bool(r['errors']))
