"""Approved pre-deploy checkpoint. Copy evidence, never modify original rows."""
import hashlib,json,zipfile,shutil,os
from datetime import datetime,timezone
from pathlib import Path

def prefix(path,size):
    h=hashlib.sha256();left=size
    with path.open('rb') as f:
        while left:
            b=f.read(min(left,1048576))
            if not b:raise ValueError('Evidence truncated during checkpoint: '+str(path))
            h.update(b);left-=len(b)
    return h.hexdigest()

def preserve(root='/data',repo='/app'):
    root=Path(root);repo=Path(repo);tag=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    dest=root/'g8_preservation'/tag;dest.mkdir(parents=True,exist_ok=False);ledger={};reports={}
    with zipfile.ZipFile(dest/'evidence.zip','w',zipfile.ZIP_DEFLATED,compresslevel=1) as z:
        for p in sorted(root.glob('*')):
            if not p.is_file() or p.is_symlink():continue
            name=p.name
            if not (('outcomes' in name and p.suffix=='.jsonl') or name.startswith(('all_engine_','paper_generation_')) or name=='strategy_output_switches.json'):continue
            if any(x in name.lower() for x in ('token','secret','credential','account','cookie')):continue
            h=hashlib.sha256()
            with p.open('rb') as src,z.open('data/'+name,'w',force_zip64=True) as out:
                before=os.fstat(src.fileno());left=before.st_size
                while left:
                    b=src.read(min(left,1048576))
                    if not b:raise ValueError('Evidence truncated during export')
                    out.write(b);h.update(b);left-=len(b)
            if p.suffix=='.jsonl':ledger[name]=dict(bytes=before.st_size,sha256=h.hexdigest())
            else:reports[name]=dict(bytes=before.st_size,sha256=h.hexdigest())
        for name in ('GENERATION_THREE_RETIREMENT_PROPOSAL.json','GENERATION_SIX_RETIREMENT.json','GENERATION_SIX_RUNTIME_HASHES.json','GENERATION_SEVEN_RUNTIME_HASHES.json','G7_BUILD_REVISION','fly.toml'):
            p=repo/name
            if p.exists():z.write(p,'app/'+name)
        history=json.loads((root/'all_engine_bidask_daily_history.json').read_text())
        days={d:hashlib.sha256(json.dumps(r,sort_keys=True,separators=(',',':')).encode()).hexdigest() for d,r in history['days'].items()}
        manifest=dict(schema='G8_PRESERVATION_V1',created_utc=tag,ledger_prefixes=ledger,report_files=reports,historical_day_hashes=days)
        z.writestr('preservation_manifest.json',json.dumps(manifest,indent=2))
    (dest/'preservation_manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    # Stable locator for the guarded download and subsequent verification.
    (root/'g8_preservation_latest.json').write_text(json.dumps(dict(directory=str(dest),archive=str(dest/'evidence.zip')))+'\n')
    shutil.copyfile(dest/'evidence.zip',root/'g8_preservation_latest.zip')
    return dict(directory=str(dest),archive=str(root/'g8_preservation_latest.zip'),files=len(ledger)+len(reports),bytes=(dest/'evidence.zip').stat().st_size)

if __name__=='__main__':print(json.dumps(preserve(),indent=2))
