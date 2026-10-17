"""Relevant legacy suites plus G10 gates; verify all runtime provenance chains."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

SUITES=['generation_one','generation_two','generation_three','generation_four','generation_five',
    'generation_six','generation_seven','generation_eight','generation_nine','generation_nine_sizing','generation_ten',
    'all_engine_performance','capital_performance','executable_paper_engine','output_switches',
    'capital_performance_worker','performance_pruning_dependencies','pruned_runtime_inventory',
    'options_rv_cash_flow','options_rv_wiring','statarb2','statarb_shadow_wiring','g3_native_audit']


def run():
    root=Path(__file__).resolve().parents[2]
    env={**os.environ,'ENABLE_G10_PAPER':'0','ENABLE_G9_PAPER':'0','ENABLE_G9_RETIREMENTS':'0','ENABLE_G8_RETIREMENTS':'0'}
    subprocess.run([sys.executable,'-m','unittest',*['tests.test_'+s for s in SUITES],'-q'],cwd=root,env=env,check=True)
    for name in ['SIX','SEVEN','EIGHT','NINE','TEN']:
        for p,digest in json.loads((root/('GENERATION_'+name+'_RUNTIME_HASHES.json')).read_text()).items():
            if hashlib.sha256((root/p).read_bytes()).hexdigest()!=digest:raise ValueError('Runtime hash mismatch: '+p)
    print('G10 and legacy checks; runtime provenance chains passed')

if __name__=='__main__':run()
