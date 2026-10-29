"""Create a small source package and pinned manifest, without PyInstaller."""
import hashlib
import json
import os
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
from dev_channel import REPOSITORY, validate_manifest  # noqa: E402


def build(root, output, commit):
    pins = [line.strip() for line in (root / 'requirements-dev-runtime.txt').read_text().splitlines()
            if line.strip() and not line.startswith('#')]
    tracked = subprocess.check_output(['git', 'ls-files', '-z'], cwd=root).decode().split('\0')
    names = sorted(p for p in tracked if p and (p.startswith(('src/', 'scripts/', 'docs/', 'tests/')) or
                   p in {'pyproject.toml', 'README.md', 'requirements-dev-runtime.txt'}))
    output.mkdir(parents=True, exist_ok=True)
    archive = output / 'MAJIMeeting-DEV.zip'
    files = {}
    with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED) as bundle:
        for name in names:
            path = root / name
            if path.is_symlink():
                raise ValueError('Source links not supported')
            data = path.read_bytes()
            files[name] = dict(size=len(data), sha256=hashlib.sha256(data).hexdigest())
            bundle.writestr(name, data)
    manifest = dict(format=1, repository=REPOSITORY, commit=commit, platform='win_amd64',
                    python='3.11', data_schema=1, requirements=pins,
                    runtime=hashlib.sha256(('\n'.join(pins) + '\n').encode()).hexdigest(),
                    archive_sha256=hashlib.sha256(archive.read_bytes()).hexdigest(), files=files,
                    validated_run=os.environ.get('GITHUB_RUN_ID', 'local'))
    validate_manifest(manifest)
    (output / 'dev-manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    # Bootstrap is extracted once by the user; the code bundle is verified again during setup.
    with zipfile.ZipFile(output / 'MAJIMeeting-DEV-Setup.zip', 'w', compression=zipfile.ZIP_DEFLATED) as setup:
        for name in ['Installer-DEV.cmd', 'install-dev.ps1', 'dev_channel.py']:
            setup.write(root / 'scripts' / name, name)
    return manifest


if __name__ == '__main__':
    build(ROOT, ROOT / 'dev-dist', os.environ.get('GITHUB_SHA') or
          subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT).decode().strip())
