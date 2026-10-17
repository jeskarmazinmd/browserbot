"""Read-only G9 execution-version and status inspection. Never opens a tracker."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from generation_nine_paper_tracker import FILE_STEM, EXECUTION_VERSION, source_hashes
from strategies import generation_nine as g


def inspect(root, now=None):
    root=Path(root)
    status=json.loads((root/(FILE_STEM+'_status.json')).read_text())
    execution=json.loads((root/(FILE_STEM+'_execution_v2.json')).read_text())
    births=json.loads((root/(FILE_STEM+'_births.json')).read_text())
    age=((now or datetime.now(timezone.utc))-g.utc(status['updated_at'])).total_seconds()
    checks=dict(execution_version=status.get('execution_version')==EXECUTION_VERSION,
                source_hashes=execution['policy']['sources']==source_hashes(),
                population=status.get('population_hash')==g.POPULATION_HASH and set(births)==g.IDS,
                paper_only=status.get('paper_only') is True,
                broker_disabled=status.get('broker_execution_enabled') is False,
                broker_margin_unverified=status.get('broker_margin_verified') is False,
                broker_buying_power_unverified=status.get('broker_buying_power_verified') is False,
                locate_unverified=status.get('short_locate_verified') is False,
                fresh_status=0<=age<=180)
    return dict(checks=checks,status_age_seconds=age,status=status,
                interpretation='OPEN events prove hypothetical paper admissions only; broker eligibility remains unverified')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',default='/data')
    args=parser.parse_args()
    result=inspect(args.root)
    print(json.dumps(result,indent=2,sort_keys=True))
    return 0 if all(result['checks'].values()) else 1


if __name__=='__main__':raise SystemExit(main())
