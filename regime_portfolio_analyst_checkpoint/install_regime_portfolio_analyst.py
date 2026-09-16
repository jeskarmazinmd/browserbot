from pathlib import Path
import shutil

HERE=Path(__file__).resolve().parent
ROOT=Path.cwd().resolve()
for relative in (Path("research_lab/regime_portfolio_analyst.py"),Path("tests/test_regime_portfolio_analyst.py")):
    source=HERE/relative;target=ROOT/relative;target.parent.mkdir(parents=True,exist_ok=True)
    if source.resolve()!=target.resolve():shutil.copy2(source,target)
print("INSTALLED human-controlled regime portfolio analyst")
