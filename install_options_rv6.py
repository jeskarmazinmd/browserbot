"""Install the isolated Options Relative Value6 checkpoint into browserbot."""
from pathlib import Path
import shutil

HERE=Path(__file__).resolve().parent
ROOT=Path.cwd().resolve()
if not (ROOT/"supervisor.py").exists() or not (ROOT/"Dockerfile").exists():
    raise SystemExit("Run this installer from the browserbot repository root")

for name in ("options_rv_shadow_worker.py","options_rv_paper_tracker.py"):
    source = HERE / name
    target_file = ROOT / name
    if source.resolve() != target_file.resolve():
        shutil.copy2(source, target_file)

source_dir = HERE / "options_rv_strategies"
target = ROOT / "options_rv_strategies"
if source_dir.resolve() != target.resolve():
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(source_dir, target)
for name in ("test_options_rv6.py","test_options_rv_wiring.py","test_options_rv_installer.py"):
    source = HERE / "tests" / name
    target_file = ROOT / "tests" / name
    if source.resolve() != target_file.resolve():
        shutil.copy2(source, target_file)

p=ROOT/"supervisor.py";s=p.read_text()
line='    "options_rv_shadow": [sys.executable, "-u", "options_rv_shadow_worker.py"],\n'
if line not in s:
    anchor='    "futures_curve_shadow": [sys.executable, "-u", "futures_curve_shadow_worker.py"],\n'
    if anchor not in s:raise SystemExit("supervisor optional-worker anchor missing")
    s=s.replace(anchor,anchor+line,1);p.write_text(s)

p=ROOT/"Dockerfile";s=p.read_text()
block='COPY options_rv_shadow_worker.py .\nCOPY options_rv_paper_tracker.py .\nCOPY options_rv_strategies /app/options_rv_strategies\n'
if block not in s:
    anchor='COPY futures_curve_strategies /app/futures_curve_strategies\n'
    if anchor not in s:raise SystemExit("Dockerfile futures-curve anchor missing")
    s=s.replace(anchor,anchor+block,1);p.write_text(s)

print("INSTALLED Options Relative Value6")
