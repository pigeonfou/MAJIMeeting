"""Bind the installed-and-tested executable to its exact source tree and Actions run."""
import hashlib
import json
import os
import re
import subprocess
import tomllib
from pathlib import Path


def git_value(expression):
    return subprocess.check_output(['git', 'rev-parse', expression], text=True).strip()


def main():
    version = tomllib.loads(Path('pyproject.toml').read_text())['project']['version'].split('.dev')[0]
    if not re.fullmatch(r'\d+\.\d+\.\d+', version):
        raise ValueError('Invalid release version')
    installer = Path('dist') / f'MAJIMeeting-{version}-preview-Setup.exe'
    digest = hashlib.sha256()
    with installer.open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(chunk)
    event = json.loads(Path(os.environ['GITHUB_EVENT_PATH']).read_text())
    manifest = {'schema': 1, 'repository': os.environ['GITHUB_REPOSITORY'],
                'source_commit': git_value('HEAD'), 'source_tree': git_value('HEAD^{tree}'),
                'run_id': int(os.environ['GITHUB_RUN_ID']),
                'run_number': int(os.environ['GITHUB_RUN_NUMBER']),
                'run_attempt': int(os.environ['GITHUB_RUN_ATTEMPT']),
                'pr_number': event.get('number') if os.environ['GITHUB_EVENT_NAME'] == 'pull_request'
                else None, 'version': version, 'installer': installer.name,
                'sha256': digest.hexdigest()}
    (installer.parent / 'build-manifest.json').write_text(
        json.dumps(manifest, sort_keys=True, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
