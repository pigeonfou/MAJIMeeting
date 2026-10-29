import importlib.util
import io
import sys
import zipfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import dev_channel as channel  # noqa: E402


def bundle(commit='a' * 40, extra=None):
    files = {p: b'test source' for p in ['scripts/dev_channel.py', 'scripts/dev_launch.py',
        'scripts/run_source.py', 'src/majimeeting/__main__.py']}
    files['requirements-dev-runtime.txt'] = b'PySide6==6.12.0\n'
    if extra:
        files.update(extra)
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w') as archive:
        for name, data in files.items():
            archive.writestr(name, data)
    data = stream.getvalue()
    pins = ['PySide6==6.12.0']
    manifest = dict(format=1, repository=channel.REPOSITORY, commit=commit,
        python='3.11', platform='win_amd64', data_schema=1, requirements=pins,
        runtime=channel.digest(b'PySide6==6.12.0\n'), archive_sha256=channel.digest(data),
        files={p: dict(size=len(d), sha256=channel.digest(d)) for p, d in files.items()})
    return manifest, data


def test_verified_activation_and_failed_candidate_preserve_previous_version(tmp_path):
    first, data = bundle()
    calls = []
    def prepare(*args):
        calls.append('runtime')
    def check(*args):
        calls.append('smoke')
    channel.activate(tmp_path, first, data, prepare, check)
    previous = channel.read_state(tmp_path)
    assert previous['current']['commit'] == 'a' * 40
    second, data2 = bundle('b' * 40)
    def broken(*args):
        raise RuntimeError('candidate startup failed')
    with pytest.raises(RuntimeError):
        channel.activate(tmp_path, second, data2, prepare, broken)
    assert channel.read_state(tmp_path) == previous
    channel.activate(tmp_path, second, data2, prepare, check)
    assert channel.read_state(tmp_path)['previous'] == previous['current']
    assert first['runtime'] == second['runtime']


@pytest.mark.parametrize('kind', ['corrupt', 'traversal', 'unlisted', 'bad_pin'])
def test_corrupt_or_escaping_archive_never_changes_active_version(tmp_path, kind):
    manifest, data = bundle()
    if kind == 'corrupt':
        data += b'x'
    elif kind == 'traversal':
        manifest, data = bundle(extra={'../escape.py': b'bad'})
    elif kind == 'unlisted':
        del manifest['files']['scripts/run_source.py']
    else:
        manifest['requirements'] = ['https://untrusted.invalid/package.whl']
    with pytest.raises(ValueError):
        channel.activate(tmp_path, manifest, data, lambda *a: None, lambda *a: None)
    assert not (tmp_path / 'state.json').exists()
    assert not (tmp_path.parent / 'escape.py').exists()


def test_guard_excludes_concurrent_update_and_releases_after_exception(tmp_path):
    with channel.guard(tmp_path), pytest.raises(RuntimeError, match='déjà ouvert'):
        with channel.guard(tmp_path):
            pytest.fail('Two managers must never overlap')
    with channel.guard(tmp_path):
        pass


def test_rollback_uses_verified_offline_version(tmp_path, monkeypatch):
    for commit in ['a' * 40, 'b' * 40]:
        m, data = bundle(commit)
        channel.activate(tmp_path, m, data, lambda *a: None, lambda *a: None)
    monkeypatch.setattr(channel, 'smoke', lambda *a: None)
    channel.rollback(tmp_path)
    assert channel.read_state(tmp_path)['current']['commit'] == 'a' * 40
    (tmp_path / 'versions' / ('b' * 40) / 'scripts/run_source.py').write_text('modified')
    with pytest.raises(ValueError, match='modifiée'):
        channel.rollback(tmp_path)
    assert channel.read_state(tmp_path)['current']['commit'] == 'a' * 40


def test_unchanged_runtime_never_reinstalls_dependencies(tmp_path, monkeypatch):
    manifest, _ = bundle()
    python = channel.runtime_python(tmp_path, manifest['runtime'])
    python.parent.mkdir(parents=True)
    python.touch()
    channel.atomic_json(python.parent.parent / 'runtime-ready.json', {'runtime': manifest['runtime']})
    monkeypatch.setattr(channel.subprocess, 'run', lambda *a, **kw: pytest.fail('Unexpected installation'))
    channel.prepare_runtime(tmp_path, manifest, tmp_path)


def test_catalogue_copy_is_independent_and_live_catalogue_is_refused(tmp_path):
    from test_editor import prepared
    store, meeting = prepared(tmp_path / 'ordinary')
    dev = tmp_path / 'dev'
    dev.mkdir()
    channel.atomic_json(dev / 'state.json', {'current': {'commit': 'a' * 40}, 'data': str(dev / 'data')})
    with channel.closed_catalogue(store.root), pytest.raises(RuntimeError, match='Fermez'):
        with channel.closed_catalogue(store.root):
            pytest.fail('Must refuse an active catalogue')
    clone = channel.copy_catalogue(dev, store.root)
    from majimeeting.storage import MeetingStore
    copied = MeetingStore(clone)
    copied.edit_segment(copied.segments('job')[0]['id'], 'DEV correction', 'DEV')
    assert store.segments('job')[0]['corrected_text'] == 'Original'
    assert copied.segments('job')[0]['corrected_text'] == 'DEV correction'
    assert (clone / meeting / 'track-00/00000000.wav').is_file()
    assert (store.root / meeting / 'track-00/00000000.wav').is_file()


def test_dev_settings_data_and_title_are_isolated(tmp_path, monkeypatch):
    import majimeeting.runtime_context as context
    data = {'MAJIMeeting': {'model': 'shared-model', 'device': 'cuda', 'last_transcription': 'private-job'}}
    class Settings:
        def __init__(self, organization, name):
            self.data = data.setdefault(name, {})
        def value(self, key, default=None, **kwargs):
            return self.data.get(key, default)
        def contains(self, key):
            return key in self.data
        def setValue(self, key, value):
            self.data[key] = value
    monkeypatch.setattr(context, 'QSettings', Settings)
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path))
    monkeypatch.setenv('MAJIMEETING_CHANNEL', 'dev')
    monkeypatch.setenv('MAJIMEETING_SOURCE_COMMIT', 'a' * 40)
    settings = context.application_settings()
    assert settings.value('model') == 'shared-model'
    assert settings.value('last_transcription') is None
    settings.setValue('device', 'cpu')
    assert data['MAJIMeeting']['device'] == 'cuda'
    assert context.data_root() == tmp_path / 'MAJIMeeting-DEV/data'
    assert 'aaaaaaaaaaaa' in context.window_title()
    monkeypatch.delenv('MAJIMEETING_CHANNEL')
    assert context.data_root() == tmp_path / 'MAJIMeeting/data'


def test_source_builder_excludes_untracked_files_and_packages_bootstrap(tmp_path):
    spec = importlib.util.spec_from_file_location('dev_builder', Path(__file__).parents[1] /
        '.github/scripts/build_dev_bundle.py')
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    # A miniature real Git tree establishes exactly which source files are eligible.
    import subprocess
    subprocess.run(['git', 'init', str(tmp_path)], check=True, capture_output=True)
    m, _ = bundle()
    for name in m['files']:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('PySide6==6.12.0\n' if name.endswith('.txt') else 'source')
    for name in ['Installer-DEV.cmd', 'install-dev.ps1']:
        (tmp_path / 'scripts' / name).write_text('installer')
    subprocess.run(['git', 'add', '.'], cwd=tmp_path, check=True)
    (tmp_path / 'scripts/untracked-secret.txt').write_text('not included')
    output = tmp_path / 'out'
    manifest = builder.build(tmp_path, output, 'a' * 40)
    assert 'scripts/untracked-secret.txt' not in manifest['files']
    with zipfile.ZipFile(output / 'MAJIMeeting-DEV-Setup.zip') as archive:
        assert set(archive.namelist()) == {'Installer-DEV.cmd', 'install-dev.ps1', 'dev_channel.py'}
