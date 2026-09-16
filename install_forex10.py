"""Install the isolated FOREX10 prospective research checkpoint."""
from __future__ import annotations

import shutil
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC = HERE / "forex10_checkpoint"
DEST = Path.cwd()


def copy_tree_contents(source, destination):
    destination.mkdir(parents=True, exist_ok=True)
    for path in source.iterdir():
        if path.name == "__pycache__":
            continue
        target = destination / path.name
        if path.is_dir():
            shutil.copytree(path, target, dirs_exist_ok=True)
        else:
            shutil.copy2(path, target)


def insert_after_once(text, anchor, addition, label):
    if addition.strip() in text:
        return text
    if anchor not in text:
        raise SystemExit(f"{label} anchor missing; refusing partial install")
    return text.replace(anchor, anchor + addition, 1)


def main():
    required = [SRC / "forex_shadow_worker.py", SRC / "forex_paper_tracker.py", SRC / "forex_strategies", SRC / "tests"]
    if not all(x.exists() for x in required):
        raise SystemExit("forex checkpoint is incomplete")
    docker_path = DEST / "Dockerfile"
    supervisor_path = DEST / "supervisor.py"
    if not docker_path.exists() or not supervisor_path.exists():
        raise SystemExit("Run this from the browserbot repository root")
    docker = docker_path.read_text()
    supervisor = supervisor_path.read_text()

    if "COPY forex_shadow_worker.py ." not in docker and "COPY futures_paper_tracker.py .\n" not in docker:
        raise SystemExit("Docker worker anchor missing; refusing partial install")
    if "COPY forex_strategies /app/forex_strategies" not in docker and "COPY futures_strategies /app/futures_strategies\n" not in docker:
        raise SystemExit("Docker package anchor missing; refusing partial install")
    optional_entry = '    "forex_shadow": [sys.executable, "-u", "forex_shadow_worker.py"],\n'
    if optional_entry.strip() not in supervisor and '    "futures_shadow": [sys.executable, "-u", "futures_shadow_worker.py"],\n' not in supervisor:
        raise SystemExit("Supervisor optional-worker anchor missing; refusing partial install")

    docker = insert_after_once(docker, "COPY futures_paper_tracker.py .\n", "COPY forex_shadow_worker.py .\nCOPY forex_paper_tracker.py .\n", "Docker worker")
    docker = insert_after_once(docker, "COPY futures_strategies /app/futures_strategies\n", "COPY forex_strategies /app/forex_strategies\n", "Docker package")
    supervisor = insert_after_once(supervisor, '    "futures_shadow": [sys.executable, "-u", "futures_shadow_worker.py"],\n', optional_entry, "Supervisor worker")

    shutil.copy2(SRC / "forex_shadow_worker.py", DEST / "forex_shadow_worker.py")
    shutil.copy2(SRC / "forex_paper_tracker.py", DEST / "forex_paper_tracker.py")
    copy_tree_contents(SRC / "forex_strategies", DEST / "forex_strategies")
    copy_tree_contents(SRC / "tests", DEST / "tests")
    docker_path.write_text(docker)
    supervisor_path.write_text(supervisor)
    print("INSTALLED FOREX10: 10 self-contained, paper-only spot-FX experiments")
    print("Added isolated optional worker: forex_shadow")
    print("No equity registry or broker-order path was changed")


if __name__ == "__main__":
    main()

