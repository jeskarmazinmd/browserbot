"""Idempotently wire CrossSection8 into the current bot checkout."""
from pathlib import Path

def insert_after(path,anchor,addition):
    p=Path(path);text=p.read_text()
    if addition.strip() in text:return False
    if anchor not in text:raise SystemExit(f"{path}: wiring anchor not found: {anchor!r}")
    p.write_text(text.replace(anchor,anchor+addition,1));return True

changed=[]
if insert_after("Dockerfile","COPY microstructure_paper_tracker.py .\n","COPY crosssection_shadow_worker.py .\nCOPY crosssection_paper_tracker.py .\n"):changed.append("Dockerfile worker copies")
if insert_after("Dockerfile","COPY microstructure_strategies /app/microstructure_strategies\n","COPY crosssection_strategies /app/crosssection_strategies\n"):changed.append("Dockerfile strategy package")
if insert_after("supervisor.py",'    "microstructure_shadow": [sys.executable, "-u", "microstructure_shadow_worker.py"],\n','    "crosssection_shadow": [sys.executable, "-u", "crosssection_shadow_worker.py"],\n'):changed.append("supervisor optional worker")
print("CROSSSECTION8 WIRED" if changed else "CROSSSECTION8 ALREADY WIRED")
for item in changed:print("-",item)
