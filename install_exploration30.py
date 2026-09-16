"""Install the bounded Explore30 prospective strategy cohort into browserbot."""
from pathlib import Path
import shutil


ROOT = Path.cwd()
SOURCE = Path(__file__).resolve().parent / "exploration30_checkpoint"

IDS = (
    "SHOCKR1", "SHOCKR2", "PREVR1", "PREVR2", "VOLR1", "VOLR2",
    "TRENDX1", "TRENDX2", "ACCEL1", "ACCEL2", "PULLCONT1", "PULLCONT2",
    "BRK20", "BRK30", "COMPX1", "COMPX2", "BREADTH1", "BREADTH2",
    "OPENMOM1", "MIDREV1", "CLOSEMOM1", "ENTROPY1",
    "PAIRMR2", "PAIRTR1", "INVPAIR1", "LEADBASK2", "PEERBASK1",
    "MKTNEUT1", "SECTORROT1", "XASSETPAIR1",
)

registry = ROOT / "strategies" / "registry.py"
if not registry.exists():
    raise SystemExit("run this installer from the browserbot repository root")

# Validate the only integration point before copying any files.
text = registry.read_text()
marker = '    ("strategy_sectorh1", "SECTORH1Strategy"),\n'
if marker not in text and not all(
    f'    ("strategy_{strategy_id.lower()}", "Strategy"),\n' in text
    for strategy_id in IDS
):
    raise SystemExit("registry anchor missing; nothing was installed")

for strategy_id in IDS:
    name = f"strategy_{strategy_id.lower()}.py"
    shutil.copy2(SOURCE / "strategies" / name, ROOT / "strategies" / name)

shutil.copy2(
    SOURCE / "tests" / "test_exploration30.py",
    ROOT / "tests" / "test_exploration30.py",
)

missing_entries = "".join(
    f'    ("strategy_{strategy_id.lower()}", "Strategy"),\n'
    for strategy_id in IDS
    if f'    ("strategy_{strategy_id.lower()}", "Strategy"),\n' not in text
)
if missing_entries:
    text = text.replace(marker, marker + missing_entries, 1)
    registry.write_text(text)

print(f"INSTALLED {len(IDS)} bounded prospective paper strategies")
print("registry-only wiring; runner, tracker, collector, and execution code unchanged")
