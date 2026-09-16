"""Install the offline browserbot capacity harness."""
from pathlib import Path
import shutil

HERE=Path(__file__).resolve().parent;ROOT=Path.cwd().resolve()
if not (ROOT/"Dockerfile").exists():raise SystemExit("Run from browserbot repository root")
for relative in ("system_load_test.py","tests/test_system_load_test.py","tests/test_system_load_installer.py"):
    source=HERE/relative;target=ROOT/relative
    if source.resolve()!=target.resolve():target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,target)
p=ROOT/"Dockerfile";s=p.read_text();line="COPY system_load_test.py .\n"
if line not in s:
    anchor="COPY data_maintenance.py .\n"
    if anchor not in s:raise SystemExit("Dockerfile anchor missing")
    p.write_text(s.replace(anchor,anchor+line,1))
print("INSTALLED offline system load test")
