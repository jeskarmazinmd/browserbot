import json,sys
from pathlib import Path
text=Path(sys.argv[1]).read_text();decoder=json.JSONDecoder()
for i,char in enumerate(text):
    if char!='{':continue
    try:r,_=decoder.raw_decode(text[i:])
    except ValueError:continue
    if isinstance(r,dict) and r.get('build_revision')==sys.argv[2]:raise SystemExit(0)
raise SystemExit(1)
