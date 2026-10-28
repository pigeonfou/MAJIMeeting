import hashlib
import json
import threading
from concurrent.futures import CancelledError

import pytest
import requests

from majimeeting.model_download import TIMEOUT, download_model

PAYLOADS = {'config.json': b'{"test":true}', 'tokenizer.json': b'{"tokens":[]}',
            'model.bin': b'model weights for downloader test'}


def manifest():
    files = []
    for name, data in PAYLOADS.items():
        item = {'rfilename': name, 'size': len(data),
                'blobId': hashlib.sha1(f'blob {len(data)}\0'.encode() + data).hexdigest()}
        if name == 'model.bin':
            item['lfs'] = {'sha256': hashlib.sha256(data).hexdigest(), 'size': len(data)}
        files.append(item)
    return {'sha': 'a' * 40, 'siblings': files}


class Response:
    def __init__(self, data=b'', status=200, headers=None, metadata=None, callback=None):
        self.data, self.status_code = data, status
        self.headers, self.metadata = headers or {}, metadata
        self.callback = callback

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def raise_for_status(self):
        pass

    def json(self):
        return self.metadata

    def iter_content(self, chunk_size):
        for i in range(0, len(self.data), 3):
            yield self.data[i:i + 3]
            if self.callback:
                self.callback()


class Session:
    def __init__(self, cancel=None, corrupt=False, ignore_range=False, wrong_range=False):
        self.headers = {}
        self.calls = []
        self.cancel = cancel
        self.corrupt = corrupt
        self.ignore_range = ignore_range
        self.wrong_range = wrong_range

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def get(self, url, **kwargs):
        assert kwargs['timeout'] == TIMEOUT
        self.calls.append((url, kwargs))
        if '/api/' in url:
            return Response(metadata=manifest())
        name = url.rsplit('/', 1)[-1]
        data = PAYLOADS[name]
        if self.corrupt and name == 'model.bin':
            data = b'x' * len(data)
        range_header = kwargs.get('headers', {}).get('Range')
        offset = int(range_header[6:-1]) if range_header and not self.ignore_range else 0
        status = 206 if offset else 200
        start = 0 if self.wrong_range else offset
        headers = {'Content-Range': f'bytes {start}-{len(data)-1}/{len(data)}'}
        callback = self.cancel.set if self.cancel and name == 'model.bin' else None
        return Response(data[offset:], status, headers, callback=callback)


def test_download_checks_hashes_and_skips_verified_files(tmp_path):
    session = Session()
    progress = []
    assert download_model(tmp_path, progress=lambda *args: progress.append(args),
                          session_factory=lambda: session) == str(tmp_path)
    for name, data in PAYLOADS.items():
        assert (tmp_path / name).read_bytes() == data
    assert progress[-1][1] == 100
    assert not list(tmp_path.glob('*.part'))
    second = Session()
    download_model(tmp_path, session_factory=lambda: second)
    assert len(second.calls) == 1  # Metadata only; no repeated model transfer.
    assert json.loads((tmp_path / 'download-manifest.json').read_text())['revision'] == 'a' * 40


def test_cancel_retains_partial_and_resumes_with_range(tmp_path):
    cancel = threading.Event()
    with pytest.raises(CancelledError):
        download_model(tmp_path, cancel, session_factory=lambda: Session(cancel))
    part = tmp_path / 'model.bin.part'
    offset = part.stat().st_size
    assert 0 < offset < len(PAYLOADS['model.bin'])
    cancel.clear()
    session = Session()
    download_model(tmp_path, cancel, session_factory=lambda: session)
    assert (tmp_path / 'model.bin').read_bytes() == PAYLOADS['model.bin']
    model_call = next(c for c in session.calls if c[0].endswith('/model.bin'))
    assert model_call[1]['headers'] == {'Range': f'bytes={offset}-'}


def test_server_ignoring_range_restarts_without_duplicate_bytes(tmp_path):
    cancel = threading.Event()
    with pytest.raises(CancelledError):
        download_model(tmp_path, cancel, session_factory=lambda: Session(cancel))
    download_model(tmp_path, session_factory=lambda: Session(ignore_range=True))
    assert (tmp_path / 'model.bin').read_bytes() == PAYLOADS['model.bin']


def test_corrupt_transfer_does_not_replace_completed_file(tmp_path):
    original = b'existing previous model'
    (tmp_path / 'model.bin').write_bytes(original)
    with pytest.raises(ValueError, match='intégrité'):
        download_model(tmp_path, session_factory=lambda: Session(corrupt=True))
    assert (tmp_path / 'model.bin').read_bytes() == original
    assert not (tmp_path / 'model.bin.part.json').exists()
    download_model(tmp_path, session_factory=Session)
    assert (tmp_path / 'model.bin').read_bytes() == PAYLOADS['model.bin']


def test_bad_range_is_rejected_before_appending(tmp_path):
    cancel = threading.Event()
    with pytest.raises(CancelledError):
        download_model(tmp_path, cancel, session_factory=lambda: Session(cancel))
    before = (tmp_path / 'model.bin.part').read_bytes()
    with pytest.raises(ValueError, match='Reprise HTTP'):
        download_model(tmp_path, session_factory=lambda: Session(wrong_range=True))
    assert (tmp_path / 'model.bin.part').read_bytes() == before


def test_timeout_is_visible_and_logged(tmp_path):
    class TimeoutSession(Session):
        def get(self, *args, **kwargs):
            raise requests.Timeout('network stalled')

    with pytest.raises(RuntimeError, match='délai prévu'):
        download_model(tmp_path, session_factory=TimeoutSession)
    assert 'Timeout' in (tmp_path / 'download.log').read_text(encoding='utf-8')


def test_cancel_before_network_does_not_start_request(tmp_path):
    cancel = threading.Event()
    cancel.set()
    with pytest.raises(CancelledError):
        download_model(tmp_path / 'unused', cancel, session_factory=lambda: pytest.fail('Network'))
    assert not (tmp_path / 'unused').exists()
