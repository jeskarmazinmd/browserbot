"""Idempotently wire the Microstructure10 checkpoint into the current repo."""
from pathlib import Path


def insert_after(path, anchor, addition):
    p = Path(path); text = p.read_text()
    if addition.strip() in text:
        return False
    if anchor not in text:
        raise SystemExit(f"{path}: wiring anchor not found: {anchor!r}")
    p.write_text(text.replace(anchor, anchor + addition, 1))
    return True


changed = []
if insert_after(
    "Dockerfile",
    "COPY short_paper_tracker.py .\n",
    "COPY microstructure_shadow_worker.py .\nCOPY microstructure_paper_tracker.py .\n",
): changed.append("Dockerfile worker copies")
if insert_after(
    "Dockerfile",
    "COPY short_strategies /app/short_strategies\n",
    "COPY microstructure_strategies /app/microstructure_strategies\n",
): changed.append("Dockerfile strategy package")
if insert_after(
    "supervisor.py",
    '    "short_shadow": [sys.executable, "-u", "short_shadow_worker.py"],\n',
    '    "microstructure_shadow": [sys.executable, "-u", "microstructure_shadow_worker.py"],\n',
): changed.append("supervisor optional worker")

print("MICROSTRUCTURE10 WIRED" if changed else "MICROSTRUCTURE10 ALREADY WIRED")
for item in changed:
    print("-", item)
