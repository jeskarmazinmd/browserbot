"""Export G11 research evidence without editing source or original data.

JSONL files are captured as hashed prefixes while writers continue. This is
an inspection checkpoint, NOT a cross-file transactional restore image.
"""
import hashlib
import json
import os
from pathlib import Path
import shutil
import zipfile
from datetime import datetime, timezone


def selected(path):
    name = path.name.lower()
    return (path.is_file() and not path.is_symlink()
            and path.suffix in {'.json', '.jsonl', '.txt'}
            and not any(x in name for x in ('token', 'secret', 'credential', 'cookie'))
            and (name.startswith(('all_engine_', 'paper_generation_'))
                 or 'outcomes' in name or 'retirement' in name
                 or name == 'strategy_output_switches.json'))


def preserve(root='/data', repo='/app'):
    root, repo = Path(root), Path(repo)
    required = ['all_engine_bidask_daily_history.json',
                'all_engine_performance_live.json', 'all_engine_performance_health.json']
    for name in required:
        if not (root / name).is_file():
            raise ValueError('Missing required production evidence: ' + name)
    files = sorted(p for p in root.iterdir() if selected(p))
    needed = sum(p.stat().st_size for p in files)
    # Stored ZIP has a predictable upper bound and avoids compression CPU load.
    if shutil.disk_usage(root).free < needed + 200 * 1024**2:
        raise ValueError('Insufficient space for export plus 200 MiB headroom')
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    dest = root / 'g11_preservation' / stamp
    dest.mkdir(parents=True, exist_ok=False)
    archive = dest / 'evidence.zip'
    manifest = dict(schema='G11_INSPECTION_CHECKPOINT_V1', created_utc=stamp,
                    consistency='per-file captured prefixes; not transactional',
                    data_files={}, source_files={}, incomplete_configuration_export=True)
    snapshots = {}
    try:
        with zipfile.ZipFile(archive, 'x', zipfile.ZIP_STORED) as z:
            for p in files:
                digest = hashlib.sha256()
                captured = bytearray() if p.name in required else None
                with p.open('rb') as src, z.open('data/' + p.name, 'w', force_zip64=True) as out:
                    before = os.fstat(src.fileno())
                    left = before.st_size
                    while left:
                        chunk = src.read(min(left, 1024**2))
                        if not chunk:
                            raise ValueError('Evidence truncated: ' + p.name)
                        out.write(chunk)
                        digest.update(chunk)
                        if captured is not None:
                            captured.extend(chunk)
                        left -= len(chunk)
                    after = os.fstat(src.fileno())
                if p.suffix != '.jsonl' and (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                    raise ValueError('Snapshot changed during export; retry: ' + p.name)
                manifest['data_files'][p.name] = dict(bytes=before.st_size, sha256=digest.hexdigest(),
                    capture_started_utc=datetime.fromtimestamp(before.st_mtime, timezone.utc).isoformat(),
                    append_only_prefix=p.suffix == '.jsonl')
                if captured is not None:
                    snapshots[p.name] = json.loads(captured)
            # Source and checked-in plans establish the actual deployed baseline.
            sources = list((repo / 'strategies').glob('*.py')) + list((repo / 'reporting').glob('*.py'))
            sources += list(repo.glob('*paper*tracker.py'))
            sources += list(repo.glob('GENERATION_*')) + list(repo.glob('*BUILD_REVISION'))
            sources += [repo / n for n in ('fly.toml', 'live_strategy_runner.py', 'statarb_shadow_worker.py', 'executable_paper_engine.py')]
            for p in sorted(set(sources)):
                if not p.is_file() or p.is_symlink():
                    continue
                data = p.read_bytes()
                name = p.relative_to(repo).as_posix()
                z.writestr('app/' + name, data)
                manifest['source_files'][name] = dict(bytes=len(data), sha256=hashlib.sha256(data).hexdigest())
            live = snapshots['all_engine_performance_live.json']
            manifest.update(as_of=live.get('as_of'), reported_module_count=len(live.get('modules', {})),
                            reported_module_ids=sorted(live.get('modules', {})))
            z.writestr('preservation_manifest.json', json.dumps(manifest, indent=2))
        with zipfile.ZipFile(archive) as z:
            if z.testzip() is not None:
                raise ValueError('Archive CRC verification failed')
        locator = root / 'g11_preservation_latest.json'
        temporary = locator.with_suffix('.tmp')
        temporary.write_text(json.dumps(dict(archive=str(archive), **manifest), indent=2) + '\n')
        temporary.replace(locator)
        return dict(archive=str(archive), bytes=archive.stat().st_size,
                    files=len(manifest['data_files']), reported_module_count=manifest['reported_module_count'],
                    as_of=manifest['as_of'], production_modified=False,
                    limitation=manifest['consistency'])
    except BaseException:
        archive.unlink(missing_ok=True)
        raise


if __name__ == '__main__':
    print(json.dumps(preserve(), indent=2))
