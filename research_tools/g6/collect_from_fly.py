"""Run the read-only evidence exporter on one Fly machine and download it.

No commit, deploy, restart, strategy import, secret dump, or broker request.
Only temporary export files are written remotely.
"""
import argparse
import base64
from datetime import datetime, timezone
from pathlib import Path
import shlex
import subprocess
import uuid


def commands(app, machine, output):
    folder = Path(__file__).resolve().parent
    token = uuid.uuid4().hex
    remote = '/tmp/g6_evidence_' + token + '.tar.gz'
    script = base64.b64encode((folder / 'export_evidence.py').read_bytes()).decode()
    ids = base64.b64encode((folder / 'agreed_ranking_ids.json').read_bytes()).decode()
    payload = (
        'import base64,pathlib,runpy,tempfile; '
        'd=tempfile.TemporaryDirectory(prefix="g6_export_source_"); '
        'p=pathlib.Path(d.name); '
        f'(p/"export_evidence.py").write_bytes(base64.b64decode({script!r})); '
        f'(p/"agreed_ranking_ids.json").write_bytes(base64.b64decode({ids!r})); '
        'g=runpy.run_path(str(p/"export_evidence.py")); '
        f'g["export"]("/data","/app",{remote!r}); d.cleanup()'
    )
    return [
        ['fly', 'ssh', 'console', '-a', app, '--machine', machine,
         '-C', 'python -c ' + shlex.quote(payload)],
        ['fly', 'ssh', 'sftp', 'get', '-a', app, '--machine', machine, remote, str(output)],
    ]


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--app', default='schwab')
    parser.add_argument('--machine', default='7813422f149398')
    parser.add_argument('--output', type=Path, default=Path.home() / 'Downloads' /
                        ('g6_evidence_' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '.tar.gz'))
    args = parser.parse_args()
    if args.output.exists():
        parser.error('Output already exists; choose a new filename')
    if not args.output.parent.is_dir():
        parser.error('Output directory does not exist')
    for command in commands(args.app, args.machine, args.output):
        subprocess.run(command, check=True)
    print('Upload this evidence archive to the chat: ' + str(args.output))
