import subprocess,sys,tempfile,unittest
from pathlib import Path
class InstallerTests(unittest.TestCase):
    def test_installs(self):
        checkpoint=Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as root:
            repo=Path(root);(repo/"tests").mkdir();(repo/"Dockerfile").write_text("COPY system_load_test.py .\n")
            subprocess.run([sys.executable,str(checkpoint/"install_full_system_load_test.py")],cwd=repo,check=True)
            self.assertTrue((repo/"full_system_load_test.py").exists());self.assertIn("full_system_load_test.py",(repo/"Dockerfile").read_text())
if __name__=="__main__":unittest.main()
