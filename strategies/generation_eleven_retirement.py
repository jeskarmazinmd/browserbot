"""Durable G11 paper-output allowlist. No broker execution controls.

Rollback: disable ENABLE_G11_PAPER and restart; existing accounts retain their
births and ledgers. Existing exits remain serviced even while entries stop.
"""
from functools import lru_cache
import json
import os
from pathlib import Path


def requested():return os.environ.get('ENABLE_G11_PAPER', '0') == '1'


@lru_cache(maxsize=1)
def plan():
    p=json.loads((Path(__file__).resolve().parents[1]/'GENERATION_ELEVEN_RETIREMENT.json').read_text())
    rows=p['ranking'];parents=p['parents'];retired=p['retired_report_ids']
    if (p['schema']!='G11_RETIREMENT_V1' or len(rows)!=734 or len(set(parents))!=12
            or len(set(retired))!=722 or set(parents)&set(retired)
            or [r['module_id'] for r in rows[:12]]!=parents
            or [r['module_id'] for r in rows[12:]]!=retired
            or [r['rank'] for r in rows]!=list(range(1,735))
            or any(r['previous_configuration'] is None for r in p['retirements'])):
        raise ValueError('G11 invalid frozen retirement manifest')
    return p


def require_activation(root=None):
    path=Path(root)/'g11_activation.json' if root is not None else Path(os.environ.get('G11_ACTIVATION_PATH','/data/g11_activation.json'))
    p=json.loads(path.read_text())
    from .generation_eleven import POPULATION_HASH
    if (p.get('schema')!='G11_ACTIVATION_V1' or p.get('population_hash')!=POPULATION_HASH
            or p.get('evidence_manifest_sha256')!=plan()['evidence_manifest_sha256']
            or p.get('parents')!=plan()['parents'] or p.get('retired_count')!=722
            or p.get('historical_prefixes_verified') is not True):
        raise ValueError('G11 activation evidence mismatch')
    return p


@lru_cache(maxsize=4)
def _activation(path):return require_activation()


def enabled():
    if not requested():return False
    _activation(os.environ.get('G11_ACTIVATION_PATH','/data/g11_activation.json'))
    return True


def base(sid):return sid[:-2] if sid.endswith('BA') else sid


@lru_cache(maxsize=1)
def kept():return frozenset(base(s) for s in plan()['parents'])


def entry_retired(sid):
    if not enabled():return False
    from .generation_eleven import ALL_IDS
    return base(str(sid or '').upper()) not in kept() | ALL_IDS
