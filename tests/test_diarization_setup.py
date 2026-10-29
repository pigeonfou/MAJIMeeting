import hashlib
import json
import sys
import threading
import time
from concurrent.futures import CancelledError

import pytest
import requests
from test_model_download import Response

from majimeeting.diarization_setup import install_dependencies, stream_process
from majimeeting.model_download import download_model

FILES = {'config.yaml': b'local config', 'embedding/pytorch_model.bin': b'embedding',
         'segmentation/pytorch_model.bin': b'segmentation', 'plda/plda.npz': b'plda',
         'plda/xvec_transform.npz': b'transform'}


class CommunitySession:
    def __init__(self, denied=False):
        self.headers = {}
        self.calls = []
        self.denied = denied

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def get(self, url, **kwargs):
        assert self.headers['Authorization'] == 'Bearer ephemeral-test-token'
        self.calls.append(url)
        if self.denied:
            raise requests.HTTPError('forbidden', response=requests.Response())
        if '/api/' in url:
            return Response(metadata={'sha': 'b' * 40, 'siblings': [
                {'rfilename': name, 'size': len(data),
                 'lfs': {'sha256': hashlib.sha256(data).hexdigest()}}
                for name, data in FILES.items()]})
        name = url.split('/' + 'b' * 40 + '/')[1]
        return Response(data=FILES[name])


def test_community_verified_paths_resume_and_no_token_on_disk(tmp_path):
    session = CommunitySession()
    download_model(tmp_path, model_name='community-1', token='ephemeral-test-token',
                   session_factory=lambda: session)
    for name, data in FILES.items():
        assert (tmp_path / name).read_bytes() == data
    manifest = json.loads((tmp_path / 'download-manifest.json').read_text())
    assert manifest['repository'] == 'pyannote/speaker-diarization-community-1'
    assert all(b'ephemeral-test-token' not in path.read_bytes() for path in tmp_path.rglob('*') if path.is_file())
    second = CommunitySession()
    download_model(tmp_path, model_name='community-1', token='ephemeral-test-token',
                   session_factory=lambda: second)
    assert len(second.calls) == 1


def test_gated_access_error_does_not_expose_token(tmp_path):
    class Denied(CommunitySession):
        def get(self, url, **kwargs):
            response = requests.Response()
            response.status_code = 403
            raise requests.HTTPError('ephemeral-test-token', response=response)
    with pytest.raises(RuntimeError, match='Acceptez les conditions') as error:
        download_model(tmp_path, model_name='community-1', token='ephemeral-test-token',
                       session_factory=Denied)
    assert 'ephemeral-test-token' not in str(error.value)
    assert 'ephemeral-test-token' not in (tmp_path / 'download.log').read_text()


def test_dependency_installer_uses_managed_root_and_never_downloads_model(tmp_path, monkeypatch):
    import majimeeting.diarization_setup as setup
    script = tmp_path / 'app with spaces/setup.ps1'
    script.parent.mkdir()
    script.touch()
    monkeypatch.setattr(setup, 'setup_script', lambda: script)
    calls = []
    def execute(command, *args):
        calls.append(command)
        python = tmp_path / 'managed runtime/Scripts/python.exe'
        python.parent.mkdir(parents=True)
        python.touch()
    monkeypatch.setattr(setup, 'stream_process', execute)
    root = tmp_path / 'managed runtime'
    assert install_dependencies('cpu', runtime_root=root) == str(root / 'Scripts/python.exe')
    assert calls[0][-1] == '-SkipModel'
    assert calls[0][calls[0].index('-File') + 1] == str(script)
    assert calls[0][calls[0].index('-RuntimeRoot') + 1] == str(root)


def test_installer_output_stream_and_cancel(tmp_path):
    messages = []
    stream_process([sys.executable, '-u', '-c', 'print("dependency stage")'],
                   progress=lambda message, percent: messages.append(message))
    assert messages == ['dependency stage']
    cancel = threading.Event()
    timer = threading.Timer(.3, cancel.set)
    timer.start()
    before = time.monotonic()
    try:
        with pytest.raises(CancelledError):
            stream_process([sys.executable, '-c', 'import time; time.sleep(60)'], cancel)
    finally:
        timer.cancel()
    assert time.monotonic() - before < 10


def wait_dialog(app, dialog):
    deadline = time.monotonic() + 5
    while dialog.future is not None and time.monotonic() < deadline:
        app.processEvents()
        dialog.poll()
        time.sleep(.01)
    assert dialog.future is None


def test_setup_buttons_async_independent_and_paths_updated(tmp_path, monkeypatch):
    from PySide6.QtWidgets import QApplication

    import majimeeting.diarization_ui as ui
    app = QApplication.instance() or QApplication([])
    events = []
    def install(device, cancel, progress):
        events.append(('dependencies', device))
        progress('Installation vérifiée', 100)
        return str(tmp_path / 'runtime/python.exe')
    def download(path, token, cancel, progress):
        events.append(('model', path, token))
        return str(tmp_path / 'community-1')
    monkeypatch.setattr(ui, 'install_dependencies', install)
    monkeypatch.setattr(ui, 'download_community', download)
    monkeypatch.setattr(ui.QInputDialog, 'getText', lambda *args: ('private-token', True))
    dialog = ui.DiarizationDialog()
    dialog.device.setCurrentText('cpu')
    dialog.install_runtime()
    assert not dialog.download.isEnabled()
    wait_dialog(app, dialog)
    assert dialog.python.text() == str(tmp_path / 'runtime/python.exe')
    dialog.download_model()
    wait_dialog(app, dialog)
    assert dialog.model.text() == str(tmp_path / 'community-1')
    assert [e[0] for e in events] == ['dependencies', 'model']
    assert 'private-token' not in dialog.log.toPlainText()
    assert not any('token' in key.lower() for key in dialog.settings.allKeys())
    dialog.reject()


def test_close_during_setup_cancels_before_releasing_dialog(monkeypatch):
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication

    import majimeeting.diarization_ui as ui
    app = QApplication.instance() or QApplication([])
    def blocked(device, cancel, progress):
        assert cancel.wait(timeout=5)
        raise CancelledError()
    monkeypatch.setattr(ui, 'install_dependencies', blocked)
    dialog = ui.DiarizationDialog()
    dialog.show()
    dialog.install_runtime()
    ticks = []
    QTimer.singleShot(0, lambda: ticks.append(True))
    app.processEvents()
    assert ticks and dialog.future is not None  # UI still processes events during installation
    dialog.reject()
    assert dialog.cancel.is_set()
    wait_dialog(app, dialog)
    assert not dialog.timer.isActive()
    assert not dialog.isVisible()
