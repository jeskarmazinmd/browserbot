from pathlib import Path
import shutil
HERE=Path(__file__).resolve().parent;ROOT=Path.cwd().resolve()
source=HERE/"statarb2_strategies";target=ROOT/"statarb2_strategies"
if source.resolve()!=target.resolve():
 if target.exists():shutil.rmtree(target)
 shutil.copytree(source,target)
for name in ("test_statarb2.py",):
 test_source=HERE/"tests"/name;test_target=ROOT/"tests"/name;test_target.parent.mkdir(parents=True,exist_ok=True)
 if test_source.resolve()!=test_target.resolve():shutil.copy2(test_source,test_target)
worker=ROOT/"statarb_shadow_worker.py";text=worker.read_text()
if "STRATEGIES2=" not in text:
 text=text.replace('STRATEGIES=("STBETA1","STPAIR1","STLEAD1","STSECTOR1","STBREAK1","STRESMOM1")','STRATEGIES=("STBETA1","STPAIR1","STLEAD1","STSECTOR1","STBREAK1","STRESMOM1")\nSTRATEGIES2=("STCINT2","STHALF2","STHEDGE2","STLEAD2")',1)
 old='for sid in STRATEGIES:\n  m=importlib.import_module(f"statarb_strategies.strategy_{sid.lower()}");assert m.PAPER_ONLY is True and m.LIVE_ORDER_PLACEMENT is False;out.append(m.Strategy())'
 new='for package,ids in (("statarb_strategies",STRATEGIES),("statarb2_strategies",STRATEGIES2)):\n  for sid in ids:\n   m=importlib.import_module(f"{package}.strategy_{sid.lower()}");assert m.PAPER_ONLY is True and m.LIVE_ORDER_PLACEMENT is False;out.append(m.Strategy())'
 if old not in text:raise SystemExit("statarb loader anchor missing")
 text=text.replace(old,new,1)
 worker.write_text(text)
docker=ROOT/"Dockerfile";text=docker.read_text();anchor="COPY statarb_strategies /app/statarb_strategies\n"
if "COPY statarb2_strategies" not in text:text=text.replace(anchor,anchor+"COPY statarb2_strategies /app/statarb2_strategies\n",1)
docker.write_text(text)
print("INSTALLED independent StatArb2 experiments")
