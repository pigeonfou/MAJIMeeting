"""Verify provenance comes from the checked-out tree and the exact tested file."""
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path


def test_manifest_records_git_tree_and_installer_digest(tmp_path):
    script = Path(__file__).resolve().parents[1] / '.github' / 'scripts' / 'build_manifest.py'
    (tmp_path / 'pyproject.toml').write_text('[project]\nversion="0.2.6.dev0"\n', encoding='utf-8')
    subprocess.run(['git', 'init', '-q'], cwd=tmp_path, check=True)
    subprocess.run(['git', 'add', 'pyproject.toml'], cwd=tmp_path, check=True)
    subprocess.run(['git', '-c', 'user.name=CI', '-c', 'user.email=ci@example.invalid',
                    'commit', '-qm', 'fixture'], cwd=tmp_path, check=True)
    dist = tmp_path / 'dist'
    dist.mkdir()
    installer = dist / 'MAJIMeeting-0.2.6-preview-Setup.exe'
    installer.write_bytes(b'tested executable fixture')
    event = tmp_path / 'event.json'
    event.write_text(json.dumps({'number': 9, 'title': 'Vérification “testée”'}, ensure_ascii=False),
                     encoding='utf-8')
    environment = dict(os.environ, GITHUB_EVENT_PATH=str(event), GITHUB_REPOSITORY='owner/repo',
                       GITHUB_EVENT_NAME='pull_request', GITHUB_RUN_ID='100',
                       GITHUB_RUN_NUMBER='41', GITHUB_RUN_ATTEMPT='2')
    subprocess.run([sys.executable, str(script)], cwd=tmp_path, env=environment, check=True)
    manifest = json.loads((dist / 'build-manifest.json').read_text(encoding='utf-8'))
    assert manifest['sha256'] == hashlib.sha256(installer.read_bytes()).hexdigest()
    assert manifest['source_tree'] == subprocess.check_output(
        ['git', 'rev-parse', 'HEAD^{tree}'], cwd=tmp_path, text=True).strip()
    assert manifest['source_commit'] == subprocess.check_output(
        ['git', 'rev-parse', 'HEAD'], cwd=tmp_path, text=True).strip()
    assert (manifest['run_id'], manifest['run_number'], manifest['run_attempt']) == (100, 41, 2)
    assert manifest['pr_number'] == 9 and manifest['version'] == '0.2.6'
