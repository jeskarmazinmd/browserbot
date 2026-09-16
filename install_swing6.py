"""Install the isolated prospective Swing6 research family into this repository."""
from pathlib import Path
import shutil


ROOT = Path.cwd()
HERE = Path(__file__).resolve().parent


def copy_file(name):
    src, dst = HERE / name, ROOT / name
    if src.resolve() != dst.resolve():
        shutil.copy2(src, dst)


def copy_tree(name):
    dst = ROOT / name
    if (HERE / name).resolve() == dst.resolve():
        return
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(HERE / name, dst)


for filename in ("swing_shadow_worker.py", "swing_paper_tracker.py"):
    copy_file(filename)
copy_tree("swing_strategies")
(ROOT / "tests").mkdir(exist_ok=True)
for test in ("test_swing6.py", "test_swing_shadow_wiring.py"):
    src, dst = HERE / "tests" / test, ROOT / "tests" / test
    if src.resolve() != dst.resolve():
        shutil.copy2(src, dst)

docker = ROOT / "Dockerfile"
d = docker.read_text()
docker_lines = "COPY swing_shadow_worker.py .\nCOPY swing_paper_tracker.py .\nCOPY swing_strategies /app/swing_strategies\n"
if "COPY swing_shadow_worker.py ." not in d:
    anchor = "COPY statarb_strategies /app/statarb_strategies\n"
    if anchor not in d:
        raise SystemExit("Dockerfile statarb anchor missing; no wiring changed")
    docker.write_text(d.replace(anchor, anchor + docker_lines, 1))

supervisor = ROOT / "supervisor.py"
s = supervisor.read_text()
worker_line = '    "swing_shadow": [sys.executable, "-u", "swing_shadow_worker.py"],\n'
if '"swing_shadow"' not in s:
    anchor = '    "statarb_shadow": [sys.executable, "-u", "statarb_shadow_worker.py"],\n'
    if anchor not in s:
        raise SystemExit("supervisor statarb anchor missing; worker files installed but no supervisor wiring changed")
    supervisor.write_text(s.replace(anchor, anchor + worker_line, 1))

print("INSTALLED Swing6 prospective multi-session research family")
