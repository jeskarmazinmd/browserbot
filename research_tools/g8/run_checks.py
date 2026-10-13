"""Deterministic local gate used before deployment; no production writes."""
import json,os,subprocess,sys
from pathlib import Path

SUITES=('tests.test_generation_one','tests.test_generation_two','tests.test_generation_three','tests.test_generation_four',
        'tests.test_generation_five','tests.test_generation_six','tests.test_generation_seven','tests.test_generation_eight',
        'tests.test_capital_performance','tests.test_all_engine_performance','tests.test_capital_performance_worker',
        'tests.test_capital_intraday_report','tests.test_executable_paper_engine','tests.test_independent_bidask_tracker',
        'tests.test_bidask_paper_outcome_tracker','tests.test_bidask_multi_leg_paper_tracker','tests.test_independent_multi_leg_bidask',
        'tests.test_minute_strategy_pool')

def run():
    root=Path(__file__).resolve().parents[2]
    # Old generation controls run with G8 opt-in disabled; G8 tests exercise
    # exact new gates explicitly. Production-population checks use all flags.
    env={**os.environ,'ENABLE_G8_PAPER':'0','ENABLE_G8_RETIREMENTS':'0'}
    for n in range(3,8):env['ENABLE_G'+str(n)+'_PAPER']='0'
    env.pop('G3_RETIREMENT_PLAN_PATH',None)
    subprocess.run([sys.executable,'-m','unittest',*SUITES,'-q'],cwd=root,env=env,check=True)
    production={**env,**{'ENABLE_G'+str(n)+'_PAPER':'1' for n in range(3,9)},
                'ENABLE_G8_RETIREMENTS':'1','G3_RETIREMENT_PLAN_PATH':str(root/'GENERATION_THREE_RETIREMENT_PROPOSAL.json')}
    result=subprocess.run([sys.executable,'-m','benchmarks.benchmark_generation_eight'],cwd=root,env=production,capture_output=True,text=True,check=True)
    benchmark=json.loads(result.stdout);print(json.dumps(benchmark,indent=2))
    ipc=subprocess.run([sys.executable,'-m','benchmarks.benchmark_generation_eight','--ipc-only'],cwd=root,env=production,capture_output=True,text=True,check=True)
    benchmark['ipc']=json.loads(ipc.stdout);print(json.dumps(benchmark['ipc'],indent=2))
    # Verify local source matches the exact runtime manifest before packaging.
    import hashlib
    for manifest in ['GENERATION_SIX_RUNTIME_HASHES.json','GENERATION_SEVEN_RUNTIME_HASHES.json','GENERATION_EIGHT_RUNTIME_HASHES.json']:
        for name,digest in json.loads((root/manifest).read_text()).items():
            if hashlib.sha256((root/name).read_bytes()).hexdigest()!=digest:raise ValueError('Source manifest mismatch: '+name)
    return benchmark

if __name__=='__main__':run()
