"""Read-only G6 research export. Run on Fly; never imports the trading runner.

Copies bounded file prefixes, hashes the copied bytes, and verifies the agreed
ranking before producing an archive. Open ledgers can grow after capture; this
is a per-file snapshot, not a transaction across all writers.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import tarfile
import tempfile

DAYS = ('2026-10-07', '2026-10-08', '2026-10-09')
REASON = 'G6_SELECTION_RETIREMENT_2026_10_09_RANK_099_498'


def ranking(history, expected):
    days = history['days']
    names = set().union(*(days[d]['modules'] for d in DAYS))
    if len(names) != 498:
        raise ValueError(f'Expected 498 historical modules; found {len(names)}')
    rows = []
    for sid in names:
        factor = 1.0
        returns, counts = {}, {}
        for day in DAYS:
            record = days[day]['modules'].get(sid)
            if record is None:
                returns[day] = None
                counts[day] = None
                continue
            value = record.get('return_pct')
            if isinstance(value, bool) or value is None:
                raise ValueError(f'Missing/invalid return for {sid} on {day}')
            value = float(value)
            if not math.isfinite(value) or value < -100:
                raise ValueError(f'Invalid return for {sid} on {day}')
            returns[day] = value
            counts[day] = {k: record[k] for k in ('taken', 'trades', 'completed', 'signals') if k in record}
            factor *= 1 + value / 100
        rows.append(dict(module_id=sid, daily_returns=returns,
                         reported_counts=counts, compounded_return_pct=100 * (factor - 1),
                         days_with_records=sum(v is not None for v in returns.values())))
    rows.sort(key=lambda r: (-r['compounded_return_pct'], r['module_id']))
    actual = [r['module_id'] for r in rows]
    if actual != expected:
        first = next(i for i, (a, b) in enumerate(zip(actual, expected)) if a != b)
        raise ValueError(f'Frozen ranking mismatch at rank {first + 1}: persisted={actual[first]}, agreed={expected[first]}. No retirement authorized by this export.')
    for rank, row in enumerate(rows, 1):
        row.update(rank=rank, decision='retain' if rank <= 98 else 'retire', retirement_reason=REASON if rank > 98 else None)
    return rows


def capture_file(source, destination):
    if source.is_symlink() or not source.is_file():
        raise ValueError(f'Refusing nonregular evidence file: {source.name}')
    digest = hashlib.sha256()
    with source.open('rb') as incoming, destination.open('xb') as outgoing:
        before = os.fstat(incoming.fileno())
        remaining = before.st_size
        while remaining:
            chunk = incoming.read(min(1024 * 1024, remaining))
            if not chunk:
                raise ValueError(f'Evidence file shrank during capture: {source.name}')
            outgoing.write(chunk)
            digest.update(chunk)
            remaining -= len(chunk)
        after = os.fstat(incoming.fileno())
    if after.st_size < before.st_size or (after.st_size == before.st_size and after.st_mtime_ns != before.st_mtime_ns):
        raise ValueError(f'Evidence file changed during capture: {source.name}; retry export')
    return dict(source_path=str(source), captured_bytes=before.st_size,
                sha256=digest.hexdigest(), source_mtime_ns=before.st_mtime_ns,
                grew_during_capture=after.st_size > before.st_size)


def git_revision(repo):
    try:
        result = subprocess.run(['git', '-C', str(repo), 'rev-parse', 'HEAD'], capture_output=True, text=True)
    except FileNotFoundError:
        return None
    return result.stdout.strip() if result.returncode == 0 else None


def export(data_root, repo, output):
    data_root, repo, output = Path(data_root), Path(repo), Path(output)
    expected = json.loads((Path(__file__).with_name('agreed_ranking_ids.json')).read_text())
    if len(expected) != 498 or len(set(expected)) != 498:
        raise ValueError('Invalid agreed ranking identity list')
    with tempfile.TemporaryDirectory(prefix='g6_evidence_') as temp:
        stage = Path(temp)
        (stage / 'data').mkdir()
        provenance = {}
        history_name = 'all_engine_bidask_daily_history.json'
        provenance[history_name] = capture_file(data_root / history_name, stage / 'data' / history_name)
        rows = ranking(json.loads((stage / 'data' / history_name).read_text()), expected)
        exact_names = {'all_engine_performance_live.json', 'live_l1_snapshot.json'}
        files = set(data_root.glob('paper*_outcomes.jsonl'))
        files.update(data_root.glob('*paper*_outcomes.jsonl'))
        for suffix in ('births', 'manifest', 'status', 'observations'):
            files.update(data_root.glob('paper_generation_*_' + suffix + '.json'))
        files.update(data_root / name for name in exact_names if (data_root / name).exists())
        for source in sorted(files):
            if source.name != history_name:
                provenance[source.name] = capture_file(source, stage / 'data' / source.name)
        # Only explicit noncredential operational fields; never dump the environment.
        fields = ('ENABLE_G3_PAPER', 'ENABLE_G4_PAPER', 'ENABLE_G5_PAPER',
                  'LIVE_ORDER_PLACEMENT_ENABLED', 'LIVE_STRATEGY_ID', 'RUN_MODE')
        environment = {name: os.environ.get(name) for name in fields}
        retirement = os.environ.get('G3_RETIREMENT_PLAN_PATH')
        if retirement:
            source = Path(retirement)
            provenance['current_retirement_plan.json'] = capture_file(source, stage / 'data' / 'current_retirement_plan.json')
        # SSH environment may differ from a running service's environment.
        # Inspect only the same selected fields for recognized bot processes.
        processes = []
        for entry in Path('/proc').glob('[0-9]*'):
            try:
                command = (entry / 'cmdline').read_bytes().split(b'\0')
                roles = [name for name in ('live_strategy_runner.py', 'supervisor.py',
                         'live_quote_collector.py', 'all_engine_performance.py')
                         if any(Path(arg.decode(errors='replace')).name == name for arg in command)]
                if not roles:
                    continue
                env = {}
                for item in (entry / 'environ').read_bytes().split(b'\0'):
                    key, separator, value = item.partition(b'=')
                    if separator and key.decode(errors='replace') in fields:
                        env[key.decode()] = value.decode(errors='replace')
                processes.append(dict(pid=int(entry.name), roles=roles, selected_environment=env))
            except (OSError, ValueError):
                continue
        source_hashes = {str(p.relative_to(repo)): hashlib.sha256(p.read_bytes()).hexdigest()
                         for pattern in ('strategies/*.py', 'reporting/*.py', '*paper_tracker.py', 'live_strategy_runner.py', 'supervisor.py')
                         for p in repo.glob(pattern) if p.is_file() and not p.is_symlink()}
        manifest = dict(schema='G6_EVIDENCE_V1', captured_utc=datetime.now(timezone.utc).isoformat(),
                        days=DAYS, ranked_count=498, proposed_retirements=400,
                        registry_modified=False, git_revision=git_revision(repo),
                        selected_environment=environment, recognized_processes=processes,
                        sources=provenance, source_hashes=source_hashes,
                        limitations=['Per-file bounded snapshots; no cross-file transaction',
                                     'Reported counts retain original field names; not assumed completed trades',
                                     'Registry counts and running process configuration require separate verification'])
        (stage / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
        (stage / 'frozen_ranking.json').write_text(json.dumps(rows, indent=2) + '\n')
        # Exclusive destination prevents overwriting an earlier evidence snapshot.
        try:
            with output.open('xb') as handle:
                with tarfile.open(fileobj=handle, mode='w:gz') as archive:
                    for path in sorted(stage.rglob('*')):
                        if path.is_file():
                            archive.add(path, arcname=str(path.relative_to(stage)), recursive=False)
        except FileExistsError:
            raise
        except BaseException:
            output.unlink(missing_ok=True)
            raise
    print(json.dumps(dict(archive=str(output), bytes=output.stat().st_size,
                          ranked=498, proposed_retirements=400, changed_trading_configuration=False)))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-root', default='/data')
    parser.add_argument('--repo', default='/app')
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    export(args.data_root, args.repo, args.output)
