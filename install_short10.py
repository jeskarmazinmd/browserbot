"""Install the isolated SHORT10 prospective short-equity checkpoint."""
from __future__ import annotations

import shutil
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC = HERE / "short10_checkpoint"
DEST = Path.cwd()


def copy_tree_contents(source, destination):
    destination.mkdir(parents=True, exist_ok=True)
    for path in source.iterdir():
        if path.name == "__pycache__": continue
        target = destination / path.name
        if path.is_dir(): shutil.copytree(path, target, dirs_exist_ok=True)
        else: shutil.copy2(path, target)


def insert_after_once(text, anchor, addition, label):
    if addition.strip() in text: return text
    if anchor not in text: raise SystemExit(f"{label} anchor missing; refusing partial install")
    return text.replace(anchor, anchor + addition, 1)


def main():
    required = [SRC / "short_shadow_worker.py", SRC / "short_paper_tracker.py", SRC / "short_strategies", SRC / "tests"]
    if not all(x.exists() for x in required): raise SystemExit("short checkpoint is incomplete")
    docker_path = DEST / "Dockerfile"; supervisor_path = DEST / "supervisor.py"
    if not docker_path.exists() or not supervisor_path.exists(): raise SystemExit("Run this from the browserbot repository root")
    docker = docker_path.read_text(); supervisor = supervisor_path.read_text()
    if "COPY short_shadow_worker.py ." not in docker and "COPY forex_paper_tracker.py .\n" not in docker: raise SystemExit("Docker worker anchor missing; refusing partial install")
    if "COPY short_strategies /app/short_strategies" not in docker and "COPY forex_strategies /app/forex_strategies\n" not in docker: raise SystemExit("Docker package anchor missing; refusing partial install")
    entry = '    "short_shadow": [sys.executable, "-u", "short_shadow_worker.py"],\n'
    if entry.strip() not in supervisor and '    "forex_shadow": [sys.executable, "-u", "forex_shadow_worker.py"],\n' not in supervisor: raise SystemExit("Supervisor worker anchor missing; refusing partial install")

    docker = insert_after_once(docker, "COPY forex_paper_tracker.py .\n", "COPY short_shadow_worker.py .\nCOPY short_paper_tracker.py .\n", "Docker worker")
    docker = insert_after_once(docker, "COPY forex_strategies /app/forex_strategies\n", "COPY short_strategies /app/short_strategies\n", "Docker package")
    supervisor = insert_after_once(supervisor, '    "forex_shadow": [sys.executable, "-u", "forex_shadow_worker.py"],\n', entry, "Supervisor worker")

    shutil.copy2(SRC / "short_shadow_worker.py", DEST / "short_shadow_worker.py")
    shutil.copy2(SRC / "short_paper_tracker.py", DEST / "short_paper_tracker.py")
    copy_tree_contents(SRC / "short_strategies", DEST / "short_strategies")
    copy_tree_contents(SRC / "tests", DEST / "tests")
    docker_path.write_text(docker); supervisor_path.write_text(supervisor)
    print("INSTALLED SHORT10: 10 self-contained, paper-only short-equity experiments")
    print("Added isolated optional worker: short_shadow")
    print("Existing equity PaperOutcomeTracker and strategy registry were not changed")


if __name__ == "__main__": main()

