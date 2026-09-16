import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class InstallerTests(unittest.TestCase):
    def test_installs_worker_docker_and_supervisor_wiring(self):
        checkpoint=Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as root:
            repo=Path(root)
            (repo/"tests").mkdir()
            (repo/"supervisor.py").write_text(
                'OPTIONAL_WORKERS = {\n'
                '    "futures_curve_shadow": [sys.executable, "-u", "futures_curve_shadow_worker.py"],\n'
                '}\n'
            )
            (repo/"Dockerfile").write_text(
                'COPY futures_curve_strategies /app/futures_curve_strategies\n'
                'CMD ["python", "-u", "supervisor.py"]\n'
            )
            subprocess.run([sys.executable,str(checkpoint/"install_options_rv6.py")],cwd=repo,check=True)
            self.assertTrue((repo/"options_rv_shadow_worker.py").exists())
            self.assertTrue((repo/"options_rv_strategies"/"strategy_rvcond1.py").exists())
            self.assertIn("options_rv_shadow",(repo/"supervisor.py").read_text())
            self.assertIn("options_rv_strategies",(repo/"Dockerfile").read_text())


if __name__=="__main__":
    unittest.main()
