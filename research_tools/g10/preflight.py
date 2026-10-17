"""Stdlib-only production baseline, safe to send before deploying new code."""
import hashlib
import json
from pathlib import Path
import shutil


def inspect(root='/data'):
    root=Path(root);errors=[];files={}
    for name in ['all_engine_bidask_daily_history.json','all_engine_performance_live.json',
                 'paper_generation_three_bidask_independent_outcomes.jsonl']:
        p=root/name
        if not p.exists():errors.append('Missing '+name);continue
        files[name]=dict(bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest())
    free=shutil.disk_usage(root).free
    if free<200*1024**2:errors.append('Less than 200 MiB disk headroom; G10 snapshots need approximately 40 MiB/session in worst local benchmark')
    lp=root/'all_engine_performance_live.json';live=json.loads(lp.read_text()) if lp.exists() else {}
    return dict(errors=errors,files=files,free_mb=free/1024**2,reported_modules=len(live.get('modules',{})),
                parent=live.get('modules',{}).get('G3MPR150BA'),as_of=live.get('as_of'))

if __name__=='__main__':
    result=inspect();print(json.dumps(result,indent=2));raise SystemExit(bool(result['errors']))
