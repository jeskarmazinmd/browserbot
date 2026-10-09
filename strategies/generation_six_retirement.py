"""Exact reviewed paper-output retirement, reversible through G6 opt-in.

BA outputs of protected signal producers are retired without disabling the
producer or changing broker execution. Residual paper exits remain serviced.
"""
from functools import lru_cache
import json,os
from pathlib import Path

def enabled():return os.environ.get('ENABLE_G6_PAPER','0')=='1'
@lru_cache(maxsize=1)
def plan():
 p=json.loads((Path(__file__).resolve().parents[1]/'GENERATION_SIX_RETIREMENT.json').read_text())
 rows=p['ranking'];ret=p['retired_report_ids'];keep=p['retained_report_ids']
 if p.get('schema')!='G6_RETIREMENT_V1' or len(rows)!=498 or len(set(ret))!=400 or len(set(keep))!=98:
  raise ValueError('Invalid G6 frozen retirement population')
 if [r['rank'] for r in rows]!=list(range(1,499)) or [r['module_id'] for r in rows[98:]]!=ret or [r['module_id'] for r in rows[:98]]!=keep or set(ret)&set(keep):
  raise ValueError('Invalid G6 retirement boundary')
 return p

@lru_cache(maxsize=1)
def _sets():
 reports=frozenset(plan()['retired_report_ids'])
 return reports,frozenset(s[:-2] if s.endswith('BA') else s for s in reports)
def report_retired_ids():return _sets()[0] if enabled() else frozenset()
def entry_retired_ids():return _sets()[1] if enabled() else frozenset()
def entry_retired(sid):
 sid=str(sid or '').upper()
 return sid in report_retired_ids() or sid in entry_retired_ids()
def evaluation_retired_ids():
 from .pruning import DEPENDENCY_PROTECTED_STRATEGY_IDS
 return entry_retired_ids()-DEPENDENCY_PROTECTED_STRATEGY_IDS-{'PMID'}
