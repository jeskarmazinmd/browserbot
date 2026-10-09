"""Optional reviewed leaf retirement. No source files or histories are removed."""
from functools import lru_cache
import json
import os
from pathlib import Path
from .pruning import DEPENDENCY_PROTECTED_STRATEGY_IDS
from .generation_six_retirement import entry_retired, evaluation_retired_ids

@lru_cache(maxsize=4)
def _read_plan(path):
    if not path:return frozenset()
    plan=json.loads(Path(path).read_text())
    if plan.get('schema')!='G3_RETIREMENT_V1':raise ValueError('Invalid G3 retirement schema')
    ids=plan.get('entry_and_evaluation_ids')
    if not isinstance(ids,list) or not all(isinstance(s,str) and s and s==s.upper() for s in ids):raise ValueError('Invalid G3 retirement IDs')
    ids=frozenset(ids)
    if ids & (DEPENDENCY_PROTECTED_STRATEGY_IDS | {'PMID'}):raise ValueError('Retirement proposal includes protected source/control')
    return ids

def retired_ids():
    # Default absent: zero changes. A reviewed path takes effect on restart.
    ids=_read_plan(os.environ.get('G3_RETIREMENT_PLAN_PATH',''))
    live=os.environ.get('LIVE_STRATEGY_ID','').upper()
    if live and live in ids:raise ValueError('Retirement proposal includes configured live strategy')
    return ids | evaluation_retired_ids()

def output_retired(sid):
    sid=str(sid or '').upper();ids=retired_ids()
    return entry_retired(sid) or sid in ids or (sid.endswith('BA') and sid[:-2] in ids)
