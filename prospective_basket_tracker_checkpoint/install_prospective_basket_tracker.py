from pathlib import Path
import shutil
HERE=Path(__file__).resolve().parent;ROOT=Path.cwd().resolve()
for relative in (Path("research_lab/prospective_basket_tracker.py"),Path("tests/test_prospective_basket_tracker.py")):
    source=HERE/relative;target=ROOT/relative;target.parent.mkdir(parents=True,exist_ok=True)
    if source.resolve()!=target.resolve():shutil.copy2(source,target)
print("INSTALLED advisory prospective shared-capital basket tracker")
