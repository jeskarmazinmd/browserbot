#!/usr/bin/env python3
from pathlib import Path
import subprocess, sys
root=Path(__file__).resolve().parent
commands=[
    [sys.executable, str(root/'run_acceptance.py')],
    [sys.executable, str(root/'run_e2e_acceptance.py')],
]
for command in commands:
    print("\n===", " ".join(command), "===", flush=True)
    result=subprocess.run(command,cwd=root)
    if result.returncode:
        raise SystemExit(result.returncode)
print("\nMONDAY_READINESS_PASS: module and runner end-to-end suites passed")
