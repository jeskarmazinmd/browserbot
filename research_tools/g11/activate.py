"""Stdlib-only predeploy data gate; sent over SSH, never installed as source.

Check preserved ledger prefixes and baseline sources; create only the durable
data activation marker. No trades, configurations, births or histories reset.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import zipfile

PARENTS='G7ROTPROTECTBA G3CGLB30BA G6R05TARGETBA G6R05CTLBA G3MPR150BA G6R05ROOMBA G9LONG15 G9LONG16 G9LONG17 G6R07CTLBA G6R06PATIENTBA G3MT50BA'.split()


def prefix(path, size):
    h=hashlib.sha256()
    with path.open('rb') as f:
        while size:
            b=f.read(min(size,1024**2))
            if not b:raise ValueError('Historical ledger truncated: '+str(path))
            h.update(b);size-=len(b)
    return h.hexdigest()


def activate(population_hash, manifest_sha, root='/data', repo='/app'):
    root=Path(root);repo=Path(repo)
    locator=json.loads((root/'g11_preservation_latest.json').read_text())
    archive=Path(locator['archive'])
    with zipfile.ZipFile(archive) as z:
        raw=z.read('preservation_manifest.json')
        if hashlib.sha256(raw).hexdigest()!=manifest_sha:raise ValueError('Wrong inspection checkpoint')
        m=json.loads(raw)
        if z.testzip() is not None:raise ValueError('Production backup archive CRC failure')
        history=json.loads(z.read('data/all_engine_bidask_daily_history.json'))['days']
    historical_days={day:hashlib.sha256(json.dumps(row,sort_keys=True,separators=(',',':')).encode()).hexdigest()
                     for day,row in history.items()}
    marker=root/'g11_activation.json'
    if marker.exists():
        old=json.loads(marker.read_text())
        if old.get('population_hash')!=population_hash:raise ValueError('An alternate G11 population is already activated')
        return dict(already_activated=True,**old)
    live=json.loads((root/'all_engine_performance_live.json').read_text())
    if len(live['modules'])!=734 or set(live['modules'])!=set(m['reported_module_ids']):
        raise ValueError('Production population drifted since reviewed snapshot')
    if not set(PARENTS)<=set(live['modules']):raise ValueError('Selected parents missing')
    current_history=json.loads((root/'all_engine_bidask_daily_history.json').read_text())['days']
    for day,digest in historical_days.items():
        if day not in current_history or hashlib.sha256(json.dumps(current_history[day],sort_keys=True,separators=(',',':')).encode()).hexdigest()!=digest:
            raise ValueError('Finalized historical day changed: '+day)
    if shutil.disk_usage(root).free<512*1024**2:raise ValueError('Less than 512 MiB free; archive or expand storage before G11')
    checked={}
    for name,r in m['data_files'].items():
        if not name.endswith('.jsonl'):continue
        path=root/name
        if not path.is_file() or prefix(path,r['bytes'])!=r['sha256']:
            raise ValueError('Historical prefix changed: '+name)
        checked[name]=r
    for name,r in m['source_files'].items():
        path=repo/name
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=r['sha256']:
            raise ValueError('Deployed source drifted before activation: '+name)
    result=dict(schema='G11_ACTIVATION_V1',population_hash=population_hash,
                evidence_manifest_sha256=manifest_sha,parents=PARENTS,retired_count=722,
                historical_prefixes_verified=True,verified_prefix_count=len(checked),
                verified_historical_days=historical_days,
                verified_prefixes=checked,created_utc=datetime.now(timezone.utc).isoformat(),
                archive=str(archive),retirement_policy='stop new entries; service residual exits',
                checkpoint_consistency=m['consistency'])
    tmp=marker.with_suffix('.tmp')
    with tmp.open('x') as f:
        f.write(json.dumps(result,sort_keys=True)+'\n');f.flush();os.fsync(f.fileno())
    tmp.replace(marker)
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--population-hash',required=True);p.add_argument('--manifest-sha',required=True)
    a=p.parse_args();r=activate(a.population_hash,a.manifest_sha)
    print(json.dumps({k:v for k,v in r.items() if k!='verified_prefixes'},indent=2))
