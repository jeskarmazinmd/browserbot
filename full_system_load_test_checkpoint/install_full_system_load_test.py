from pathlib import Path
import shutil
HERE=Path(__file__).resolve().parent;ROOT=Path.cwd().resolve()
if not (ROOT/"Dockerfile").exists():raise SystemExit("Run from browserbot repository root")
for relative in ("full_system_load_test.py","tests/test_full_system_load_test.py","tests/test_full_system_load_installer.py"):
    source=HERE/relative;target=ROOT/relative
    if source.resolve()!=target.resolve():target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,target)
p=ROOT/"Dockerfile";s=p.read_text();line="COPY full_system_load_test.py .\n";anchor="COPY system_load_test.py .\n"
if line not in s:
    if anchor not in s:raise SystemExit("Dockerfile load-test anchor missing")
    p.write_text(s.replace(anchor,anchor+line,1))
print("INSTALLED full literal family load replay")
