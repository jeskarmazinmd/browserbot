"""Install isolated prospective Futures Curve6 into the current repository."""
from pathlib import Path
import shutil
ROOT=Path.cwd();HERE=Path(__file__).resolve().parent
def file(name):
 src,dst=HERE/name,ROOT/name
 if src.resolve()!=dst.resolve():shutil.copy2(src,dst)
def tree(name):
 src,dst=HERE/name,ROOT/name
 if src.resolve()==dst.resolve():return
 if dst.exists():shutil.rmtree(dst)
 shutil.copytree(src,dst)
for name in ("futures_curve_shadow_worker.py","futures_curve_paper_tracker.py"):file(name)
tree("futures_curve_strategies");(ROOT/"tests").mkdir(exist_ok=True)
for name in ("test_futures_curve6.py","test_futures_curve_wiring.py"):
 src,dst=HERE/"tests"/name,ROOT/"tests"/name
 if src.resolve()!=dst.resolve():shutil.copy2(src,dst)
docker=ROOT/"Dockerfile";d=docker.read_text();lines="COPY futures_curve_shadow_worker.py .\nCOPY futures_curve_paper_tracker.py .\nCOPY futures_curve_strategies /app/futures_curve_strategies\n"
if "COPY futures_curve_shadow_worker.py ." not in d:
 anchor="COPY swing_strategies /app/swing_strategies\n"
 if anchor not in d:raise SystemExit("Dockerfile Swing6 anchor missing")
 docker.write_text(d.replace(anchor,anchor+lines,1))
supervisor=ROOT/"supervisor.py";s=supervisor.read_text();line='    "futures_curve_shadow": [sys.executable, "-u", "futures_curve_shadow_worker.py"],\n'
if '"futures_curve_shadow"' not in s:
 anchor='    "swing_shadow": [sys.executable, "-u", "swing_shadow_worker.py"],\n'
 if anchor not in s:raise SystemExit("supervisor Swing6 anchor missing")
 supervisor.write_text(s.replace(anchor,anchor+line,1))
print("INSTALLED Futures Curve6 prospective calendar-spread family")
