"""Install the isolated FUTURES10 prospective research checkpoint."""
from __future__ import annotations

import shutil
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC = HERE / "futures10_checkpoint"
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
    required = [SRC / "futures_shadow_worker.py", SRC / "futures_paper_tracker.py", SRC / "futures_strategies", SRC / "tests"]
    if not all(x.exists() for x in required):
        raise SystemExit("futures checkpoint is incomplete")

    docker_path = DEST / "Dockerfile"
    supervisor_path = DEST / "supervisor.py"
    if not docker_path.exists() or not supervisor_path.exists():
        raise SystemExit("Run this from the browserbot repository root")

    docker = docker_path.read_text()
    supervisor = supervisor_path.read_text()

    # Validate every mutation anchor before changing any repository file.
    if "COPY futures_shadow_worker.py ." not in docker and "COPY options_paper_tracker.py .\n" not in docker:
        raise SystemExit("Docker worker anchor missing; refusing partial install")
    if "COPY futures_strategies /app/futures_strategies" not in docker and "COPY options_strategies /app/options_strategies\n" not in docker:
        raise SystemExit("Docker package anchor missing; refusing partial install")
    optional_entry = '    "futures_shadow": [sys.executable, "-u", "futures_shadow_worker.py"],\n'
    if optional_entry.strip() not in supervisor and '    "options_shadow": [sys.executable, "-u", "options_shadow_worker.py"],\n' not in supervisor:
        raise SystemExit("Supervisor optional-worker anchor missing; refusing partial install")

    new_docker = insert_after_once(
        docker,
        "COPY options_paper_tracker.py .\n",
        "COPY futures_shadow_worker.py .\nCOPY futures_paper_tracker.py .\n",
        "Docker worker",
    )
    new_docker = insert_after_once(
        new_docker,
        "COPY options_strategies /app/options_strategies\n",
        "COPY futures_strategies /app/futures_strategies\n",
        "Docker futures package",
    )
    new_supervisor = insert_after_once(
        supervisor,
        '    "options_shadow": [sys.executable, "-u", "options_shadow_worker.py"],\n',
        optional_entry,
        "Supervisor futures worker",
    )

    # Copy only after all anchors have validated.
    shutil.copy2(SRC / "futures_shadow_worker.py", DEST / "futures_shadow_worker.py")
    shutil.copy2(SRC / "futures_paper_tracker.py", DEST / "futures_paper_tracker.py")
    copy_tree_contents(SRC / "futures_strategies", DEST / "futures_strategies")
    copy_tree_contents(SRC / "tests", DEST / "tests")
    docker_path.write_text(new_docker)
    supervisor_path.write_text(new_supervisor)
    print("INSTALLED FUTURES10: 10 self-contained, paper-only micro-futures experiments")
    print("Added isolated optional worker: futures_shadow")
    print("No equity registry or broker-order path was changed")


if __name__ == "__main__":
    main()
