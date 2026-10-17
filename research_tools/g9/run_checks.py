"""Focused deterministic G9 gates, opt-in legacy retirement checks kept separate."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys


def run():
    root=Path(__file__).resolve().parents[2]
    env={**os.environ,'ENABLE_G9_PAPER':'0','ENABLE_G9_RETIREMENTS':'0'}
    suites=['tests.test_generation_nine','tests.test_generation_nine_sizing','tests.test_statarb2','tests.test_statarb_shadow_wiring',
            'tests.test_generation_one','tests.test_generation_two','tests.test_generation_three',
            'tests.test_generation_four','tests.test_generation_five','tests.test_generation_six',
            'tests.test_generation_seven','tests.test_generation_eight','tests.test_all_engine_performance',
            'tests.test_capital_performance','tests.test_executable_paper_engine',
            'tests.test_options_rv_cash_flow','tests.test_output_switches','tests.test_capital_performance_worker',
            'tests.test_performance_pruning_dependencies','tests.test_options_rv_wiring','tests.test_pruned_runtime_inventory']
    subprocess.run([sys.executable,'-m','unittest',*suites,'-q'],env=env,cwd=root,check=True)
    for name in ['GENERATION_SIX_RUNTIME_HASHES.json','GENERATION_SEVEN_RUNTIME_HASHES.json','GENERATION_EIGHT_RUNTIME_HASHES.json','GENERATION_NINE_RUNTIME_HASHES.json']:
        for path,digest in json.loads((root/name).read_text()).items():
            if hashlib.sha256((root/path).read_bytes()).hexdigest()!=digest:raise ValueError('Runtime hash mismatch: '+path)
    print('G9 local checks and runtime source hashes passed')

if __name__=='__main__':run()
