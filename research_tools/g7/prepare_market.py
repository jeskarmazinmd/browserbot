"""Reduce archived rich books to frozen bounded research symbols, retaining clocks."""
import csv,gzip,json,argparse,hashlib
from pathlib import Path
SYMBOLS={'GLD','SLV','GDX','GDXJ','USO','UNG','XLE','OIH','XME','COPX','DBA','TLT','UUP','SPY','MNDR','YMAT'}
def prepare(root,out):
 root=Path(root);out=Path(out);out.mkdir(parents=True,exist_ok=True);manifest={}
 for p in sorted(root.glob('research_market/*.csv.gz')):
  dest=out/(p.name.replace('.csv.gz','.jsonl'));count=0;minute=None;quotes={};observed=None
  with gzip.open(p,'rt') as f,dest.open('w') as w:
   def flush():
    if quotes:w.write(json.dumps(dict(minute=minute,observed_at=observed,quotes=quotes),separators=(',',':'))+'\n')
   for r in csv.DictReader(f):
    if r['symbol'] not in SYMBOLS:continue
    if r['market_minute_utc']!=minute:
     flush();quotes={};minute=r['market_minute_utc']
    observed=r['observed_at_utc'];q={}
    for k,v in r.items():
     if k in ('symbol','market_minute_utc','observed_at_utc'):continue
     if k=='realtime':q[k]=v.lower()=='true'
     elif k.endswith('_mic'):q[k]=v
     else:
      try:q[k]=float(v)
      except ValueError:q[k]=None
    q['collector_observed_at']=r['observed_at_utc'];quotes[r['symbol']]=q;count+=1
   flush()
  manifest[p.name]=dict(sha256=hashlib.sha256(p.read_bytes()).hexdigest(),rows=count)
  print(p.name,count,flush=True)
 (out/'manifest.json').write_text(json.dumps(manifest,indent=2))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('root');p.add_argument('out');a=p.parse_args();prepare(a.root,a.out)
