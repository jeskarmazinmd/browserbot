from pathlib import Path
import shutil
HERE=Path(__file__).resolve().parent;ROOT=HERE.parent
for name in ("event_shadow_worker.py","event_paper_tracker.py"):
    shutil.copy2(HERE/name,ROOT/name)
target=ROOT/"event_strategies"
if target.exists():shutil.rmtree(target)
shutil.copytree(HERE/"event_strategies",target)
(ROOT/"tests").mkdir(exist_ok=True);shutil.copy2(HERE/"tests/test_event8.py",ROOT/"tests/test_event8.py")
docker=ROOT/"Dockerfile";s=docker.read_text();anchor="COPY supervisor.py ."
block="COPY event_shadow_worker.py .\nCOPY event_paper_tracker.py .\nCOPY event_strategies /app/event_strategies\n"
if block not in s:s=s.replace(anchor,anchor+"\n"+block)
docker.write_text(s)
sup=ROOT/"supervisor.py";s=sup.read_text();anchor='    "xs_shadow": [sys.executable, "-u", "xs_shadow_worker.py"],'
line='    "event_shadow": [sys.executable, "-u", "event_shadow_worker.py"],'
if line not in s:
    if anchor not in s:raise SystemExit("supervisor worker anchor missing")
    s=s.replace(anchor,anchor+"\n"+line)
sup.write_text(s)
print("INSTALLED prospective Event8 family")
