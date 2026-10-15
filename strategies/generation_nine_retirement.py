"""Exact October 15 retirement. Producer dependencies and residual exits survive."""
import json
import os
from functools import lru_cache
from pathlib import Path


def enabled():
    return os.environ.get('ENABLE_G9_RETIREMENTS', '0') == '1'


@lru_cache(maxsize=1)
def plan():
    p = json.loads((Path(__file__).resolve().parents[1] / 'GENERATION_NINE_RETIREMENT.json').read_text())
    rows = p['ranking']
    keep, retire = p['retained_report_ids'], p['retired_report_ids']
    if (p['schema'] != 'G9_RETIREMENT_V1' or len(rows) != 596 or len(set(keep)) != 130
            or len(set(retire)) != 466 or set(keep) & set(retire)
            or [r['rank'] for r in rows] != list(range(1, 597))
            or [r['module_id'] for r in rows[:130]] != keep
            or [r['module_id'] for r in rows[130:]] != retire):
        raise ValueError('Invalid frozen G9 retirement boundary')
    return p


def entry_retired(sid):
    if not enabled():
        return False
    sid = str(sid or '').upper()
    ids = plan()['retired_report_ids']
    # A BA retirement suppresses its paper output without disabling source evaluation.
    # This function is used only by paper entry/output paths, never broker routing.
    return sid in ids or sid + 'BA' in ids
