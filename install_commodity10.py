"""Install ten bounded prospective commodity/macro ETF experiments."""
from pathlib import Path
import shutil

ROOT=Path.cwd();SRC=Path(__file__).resolve().parent/"commodity10_checkpoint"
IDS=("CMDMETMR1","CMDMETTR1","CMDGDR1","CMDGDU1","CMDOIL1","CMDGAS1","CMDMIN1","CMDCOP1","CMDBRD1","CMDROT1")
registry=ROOT/"strategies"/"registry.py"
if not registry.exists():raise SystemExit("run from browserbot repository root")
text=registry.read_text();marker='    ("strategy_sectorh1", "SECTORH1Strategy"),\n'
if marker not in text and not all(f'    ("strategy_{x.lower()}", "Strategy"),\n' in text for x in IDS):raise SystemExit("registry anchor missing; nothing installed")
for sid in IDS:shutil.copy2(SRC/"strategies"/f"strategy_{sid.lower()}.py",ROOT/"strategies"/f"strategy_{sid.lower()}.py")
shutil.copy2(SRC/"tests"/"test_commodity10.py",ROOT/"tests"/"test_commodity10.py")
missing="".join(f'    ("strategy_{sid.lower()}", "Strategy"),\n' for sid in IDS if f'    ("strategy_{sid.lower()}", "Strategy"),\n' not in text)
if missing:registry.write_text(text.replace(marker,marker+missing,1))
print("INSTALLED 10 bounded paper-only commodity/macro ETF experiments")
print("Registry-only wiring; no collector, runner, tracker, auth, or execution changes")
