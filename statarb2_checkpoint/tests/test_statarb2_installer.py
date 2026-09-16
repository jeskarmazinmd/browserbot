import os,runpy,shutil,tempfile,unittest
from pathlib import Path
class StatArb2InstallerTests(unittest.TestCase):
 def test_installer_wires_second_family_without_replacing_first(self):
  source=Path(__file__).resolve().parents[1]
  with tempfile.TemporaryDirectory() as root:
   root=Path(root);shutil.copy2(source/"install_statarb2.py",root/"install_statarb2.py");shutil.copytree(source/"statarb2_strategies",root/"statarb2_strategies");(root/"tests").mkdir();shutil.copy2(source/"tests/test_statarb2.py",root/"tests/test_statarb2.py")
   (root/"statarb_shadow_worker.py").write_text('import importlib\nSTRATEGIES=("STBETA1","STPAIR1","STLEAD1","STSECTOR1","STBREAK1","STRESMOM1")\ndef load_strategies():\n out=[]\n for sid in STRATEGIES:\n  m=importlib.import_module(f"statarb_strategies.strategy_{sid.lower()}");assert m.PAPER_ONLY is True and m.LIVE_ORDER_PLACEMENT is False;out.append(m.Strategy())\n return out\n')
   (root/"Dockerfile").write_text("COPY statarb_strategies /app/statarb_strategies\n")
   old=os.getcwd();os.chdir(root)
   try:runpy.run_path(str(root/"install_statarb2.py"),run_name="__main__")
   finally:os.chdir(old)
   worker=(root/"statarb_shadow_worker.py").read_text();self.assertIn("STRATEGIES2=",worker);self.assertIn("statarb2_strategies",worker);compile(worker,"statarb_shadow_worker.py","exec");self.assertIn("COPY statarb2_strategies",(root/"Dockerfile").read_text())
if __name__=="__main__":unittest.main()
