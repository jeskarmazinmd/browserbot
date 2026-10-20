"""G11 execution/retirement regression gate plus relevant existing suites."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from research_tools.g10.run_checks import SUITES


def run():
    root=Path(__file__).resolve().parents[2]
    env={**os.environ,'ENABLE_G11_PAPER':'0','ENABLE_G10_PAPER':'0','ENABLE_G9_PAPER':'0',
         'ENABLE_G9_RETIREMENTS':'0','ENABLE_G8_RETIREMENTS':'0'}
    suites=['tests.test_'+s for s in SUITES]+['tests.test_generation_eleven','tests.test_g11_preservation','tests.test_g11_activation']
    subprocess.run([sys.executable,'-m','unittest',*suites,'-q'],cwd=root,env=env,check=True)
    for number in ['SIX','SEVEN','EIGHT','NINE','TEN','ELEVEN']:
        path=root/('GENERATION_'+number+'_RUNTIME_HASHES.json')
        for name,digest in json.loads(path.read_text()).items():
            if hashlib.sha256((root/name).read_bytes()).hexdigest()!=digest:
                raise ValueError('Runtime source mismatch: '+name)
    print('G11 and all relevant legacy suites passed; runtime provenance verified')


if __name__=='__main__':run()
