"""Install isolated paper-only prospective options research family."""
from pathlib import Path
import shutil

ROOT=Path.cwd();SRC=Path(__file__).resolve().parent/"options10_checkpoint"
for required in (ROOT/"supervisor.py",ROOT/"Dockerfile"):
    if not required.exists():raise SystemExit("run from browserbot repository root")

supervisor=ROOT/"supervisor.py";st=supervisor.read_text()
s_anchor='OPTIONAL_WORKERS = {\n    "xs_shadow": [sys.executable, "-u", "xs_shadow_worker.py"],\n}'
s_new='OPTIONAL_WORKERS = {\n    "xs_shadow": [sys.executable, "-u", "xs_shadow_worker.py"],\n    "options_shadow": [sys.executable, "-u", "options_shadow_worker.py"],\n}'
if '"options_shadow":' not in st and s_anchor not in st:raise SystemExit("supervisor optional-worker anchor missing; nothing installed")

docker=ROOT/"Dockerfile";dt=docker.read_text()
d_anchor='COPY xs_shadow_worker.py .\n'
if 'COPY options_shadow_worker.py .' not in dt and d_anchor not in dt:raise SystemExit("Dockerfile worker anchor missing; nothing installed")
strat_anchor='COPY strategies /app/strategies\n'
if 'COPY options_strategies /app/options_strategies' not in dt and strat_anchor not in dt:raise SystemExit("Dockerfile strategies anchor missing; nothing installed")

shutil.copy2(SRC/"options_shadow_worker.py",ROOT/"options_shadow_worker.py")
shutil.copy2(SRC/"options_paper_tracker.py",ROOT/"options_paper_tracker.py")
(ROOT/"options_strategies").mkdir(exist_ok=True)
for p in (SRC/"options_strategies").glob("*.py"):shutil.copy2(p,ROOT/"options_strategies"/p.name)
(ROOT/"tests").mkdir(exist_ok=True)
for p in (SRC/"tests").glob("test_*.py"):shutil.copy2(p,ROOT/"tests"/p.name)

if '"options_shadow":' not in st:supervisor.write_text(st.replace(s_anchor,s_new,1))
if 'COPY options_shadow_worker.py .' not in dt:dt=dt.replace(d_anchor,d_anchor+'COPY options_shadow_worker.py .\nCOPY options_paper_tracker.py .\n',1)
if 'COPY options_strategies /app/options_strategies' not in dt:dt=dt.replace(strat_anchor,strat_anchor+'COPY options_strategies /app/options_strategies\n',1)
docker.write_text(dt)
print("INSTALLED 10 isolated paper-only options experiments")
print("No trading client, option-order method, or equity strategy registry changes")
