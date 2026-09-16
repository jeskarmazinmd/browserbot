"""Idempotently wire StatArb6 into the current bot checkout."""
from pathlib import Path
def insert_after(path,anchor,addition):
 p=Path(path);text=p.read_text()
 if addition.strip() in text:return False
 if anchor not in text:raise SystemExit(f"{path}: wiring anchor not found: {anchor!r}")
 p.write_text(text.replace(anchor,anchor+addition,1));return True
changed=[]
if insert_after("Dockerfile","COPY crosssection_paper_tracker.py .\n","COPY statarb_shadow_worker.py .\nCOPY statarb_paper_tracker.py .\n"):changed.append("Dockerfile worker copies")
if insert_after("Dockerfile","COPY crosssection_strategies /app/crosssection_strategies\n","COPY statarb_strategies /app/statarb_strategies\n"):changed.append("Dockerfile strategy package")
if insert_after("supervisor.py",'    "crosssection_shadow": [sys.executable, "-u", "crosssection_shadow_worker.py"],\n','    "statarb_shadow": [sys.executable, "-u", "statarb_shadow_worker.py"],\n'):changed.append("supervisor optional worker")
print("STATARB6 WIRED" if changed else "STATARB6 ALREADY WIRED")
for x in changed:print("-",x)
