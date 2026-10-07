"""Run inside Fly SSH after deployment. Read-only checks; never activates trades."""
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import time
from strategies import registry,generation_one,generation_one_minute,generation_two,generation_three,generation_four,generation_five as g5
from generation_five_paper_tracker import FILE_STEM
from strategies.manifest import build_manifest

def main():
    root=Path('/data');now=datetime.now(timezone.utc)
    assert os.getenv('ENABLE_G5_PAPER')=='1','G5 activation flag absent'
    assert not registry.FAILED_STRATEGIES,registry.FAILED_STRATEGIES
    assert sum(s.name in g5.ALL_IDS for s in registry.MINUTE_STRATEGIES)==96
    assert sum(s.name in generation_three.MINUTE_IDS for s in registry.MINUTE_STRATEGIES)==84
    assert sum(s.name in generation_four.MINUTE_IDS for s in registry.MINUTE_STRATEGIES)==36
    manifest=build_manifest();assert len(g5.ALL_IDS & manifest.keys())==96
    births=json.loads((root/(FILE_STEM+'_births.json')).read_text())
    assert set(births)==g5.ALL_IDS
    assert all(datetime.fromisoformat(t)<=now for t in births.values())
    status=json.loads((root/(FILE_STEM+'_status.json')).read_text())
    assert status['population']==96 and status['broker_execution_enabled'] is False
    assert status['paper_only'] and status['quote_freshness_enforced'] and status['displayed_liquidity_enforced']
    assert status['population_hash']==g5.POPULATION_HASH
    assert (now-datetime.fromisoformat(status['updated_at'])).total_seconds()<600,'G5 tracker status stale'
    frozen=json.loads((root/(FILE_STEM+'_manifest.json')).read_text());assert frozen['population_hash']==g5.POPULATION_HASH
    assert frozen['rule_source_sha256']==g5.RULE_SOURCE_SHA256
    assert (root/(FILE_STEM+'_observations.json')).exists()
    # Broker flag is observed, never changed by this script.
    assert os.getenv('LIVE_ORDER_PLACEMENT_ENABLED','0')!='1','Unexpected armed live-order flag; inspect before proceeding'
    from live_strategy_runner import live_order_placement_enabled
    assert live_order_placement_enabled() is False
    def counters():
        a=list(map(int,Path('/proc/stat').read_text().splitlines()[0].split()[1:9]))
        return sum(a),a[3]+a[4]
    total,idle=counters();time.sleep(1);total2,idle2=counters()
    cpu_busy_pct=100*(1-(idle2-idle)/(total2-total)) if total2>total else None
    mem={l.split(':')[0]:int(l.split()[1]) for l in Path('/proc/meminfo').read_text().splitlines() if l.startswith(('MemTotal:','MemAvailable:'))}
    processes=[]
    for p in Path('/proc').iterdir():
        if not p.name.isdigit():continue
        try:
            command=(p/'cmdline').read_bytes().replace(b'\0',b' ').decode(errors='replace')
            if any(x in command for x in ['supervisor.py','live_strategy_runner.py','live_quote_collector.py','all_engine_performance_worker.py']):processes.append({'pid':int(p.name),'command':command})
        except OSError:pass
    assert any('live_strategy_runner.py' in r['command'] for r in processes),'Strategy process missing'
    versions={}
    for n in ['generation_five_paper_tracker.py','strategies/generation_five.py','live_strategy_runner.py']:
        versions[n]=hashlib.sha256(Path('/app',n).read_bytes()).hexdigest()
    log=root/'bot_output.txt';recent=[]
    if log.exists():
        with log.open('rb') as f:
            f.seek(max(0,log.stat().st_size-262144));text=f.read().decode(errors='replace')
        recent=[line for line in text.splitlines() if any(x in line for x in ['Traceback','STRATEGY_EVALUATION_ERROR','GENERATION_FIVE','G5 frozen'])][-30:]
    result={'checked_at':now.isoformat(),'population':96,'birth_min':min(births.values()),'birth_max':max(births.values()),
        'status':status,'source_sha256':versions,'g1_population':len(generation_one.IDS|generation_one_minute.IDS),
        'g2_population':len(generation_two.IDS),'g3_population':len(generation_three.ALL_IDS),'g4_population':len(generation_four.ALL_IDS),
        'cpu_busy_sample_pct':cpu_busy_pct,'memory_available_mib':mem['MemAvailable']/1024,
        'disk':dict(zip(('total','used','free'),shutil.disk_usage('/data'))),'processes':processes,'recent_relevant_log_lines':recent}
    print(json.dumps(result,indent=2))
if __name__=='__main__':main()
