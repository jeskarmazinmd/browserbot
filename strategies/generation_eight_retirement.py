"""Approved output-only G8 retirement; definitions and producers remain intact."""
import json
import os
from functools import lru_cache
from pathlib import Path

@lru_cache(maxsize=1)
def plan():
    value = json.loads((Path(__file__).resolve().parents[1] / 'GENERATION_EIGHT_RETIREMENT.json').read_text())
    permanent, paused = value['permanent_report_ids'], value['paused_report_ids']
    if value.get('schema') != 'G8_RETIREMENT_V1' or len(set(permanent)) != 24 or len(set(paused)) != 2 or set(permanent) & set(paused):
        raise ValueError('Invalid approved G8 retirement population')
    return value

def report_ids():
    if os.environ.get('ENABLE_G8_RETIREMENTS', '0') != '1':
        return frozenset()
    p = plan()
    ids = frozenset(p['permanent_report_ids'] + p['paused_report_ids'])
    live = os.environ.get('LIVE_STRATEGY_ID', '').upper()
    if live and (live in ids or live + 'BA' in ids):
        raise ValueError('G8 retirement conflicts with configured live strategy')
    return ids

def entry_retired(sid):
    sid = str(sid or '').upper()
    ids = report_ids()
    return sid in ids or sid + 'BA' in ids
