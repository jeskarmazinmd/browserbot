"""Read-only baseline inspection, also executable as an in-memory SSH payload."""
import json
import shutil
from datetime import datetime,timezone
from pathlib import Path


def inspect(root='/data'):
    root=Path(root);errors=[];summary={}
    for name in ['all_engine_performance_live.json','all_engine_bidask_daily_history.json','statarb_shadow_status.json']:
        path=root/name
        if not path.exists():errors.append('Missing '+name);continue
        value=json.loads(path.read_text())
        if name=='all_engine_performance_live.json':summary.update(reported_modules=len(value['modules']),as_of=value.get('as_of'),day=value.get('day'))
        if name=='all_engine_bidask_daily_history.json':summary['recent_reported_dates']=sorted(value['days'])[-5:]
        if name=='statarb_shadow_status.json':summary['statarb_worker']=value
    if not (root/'statarb_paper_outcomes.jsonl').exists():errors.append('Missing parent ledger')
    usage=shutil.disk_usage(root);summary['free_mb']=round(usage.free/1024**2,1)
    if usage.free<100*1024**2:errors.append('Less than 100 MiB disk headroom')
    # Only allowlisted process settings; no credentials or general environment dump.
    processes=[]
    for p in Path('/proc').glob('[0-9]*'):
        try:
            cmd=(p/'cmdline').read_bytes().split(b'\0')
            if not any(x.endswith(b'statarb_shadow_worker.py') for x in cmd):continue
            env={}
            for field in (p/'environ').read_bytes().split(b'\0'):
                k,sep,v=field.partition(b'=')
                if sep and k.decode(errors='replace') in {'ENABLE_G9_PAPER','ENABLE_G9_RETIREMENTS','LIVE_STRATEGY_ID'}:env[k.decode()]=v.decode()
            processes.append(dict(pid=int(p.name),settings=env))
        except OSError:continue
    if not processes:errors.append('Statarb worker process absent')
    summary.update(errors=errors,processes=processes,checked_at=datetime.now(timezone.utc).isoformat())
    return summary

if __name__=='__main__':
    r=inspect();print(json.dumps(r,indent=2));raise SystemExit(bool(r['errors']))
