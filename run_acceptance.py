#!/usr/bin/env python3
from __future__ import annotations
import subprocess, sys
cmd=[sys.executable,'-m','unittest','discover','-s','tests/acceptance','-p','test_*.py','-v']
raise SystemExit(subprocess.call(cmd))
