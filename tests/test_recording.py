import json
import threading
import wave

import pytest

from majimeeting.capture import Device, RecordingSession
from majimeeting.storage import FragmentWriter, MeetingStore, export_track


def test_fragments_roundtrip_and_partial_recovery(tmp_path):
    folder = tmp_path / 'track'
    writer = FragmentWriter(folder, 10, 2, {'name': 'test'})
    pcm = b'\x01\x00\x02\x00' * 25
    writer.write(pcm[:52], 0.25)
    # Already committed data survives even without close; uncommitted tail is excluded.
    export_track(folder, tmp_path / 'recovered.wav')
    with wave.open(str(tmp_path / 'recovered.wav')) as audio:
        assert audio.getnframes() == 10
    writer.write(pcm[52:], 1.55)
    writer.close()
    writer.close()
    assert len(list(folder.glob('*.wav'))) == 3
    assert json.loads((folder / '00000002.json').read_text())['start_seconds'] == 2.25
    export_track(folder, tmp_path / 'all.wav')
    with wave.open(str(tmp_path / 'all.wav')) as audio:
        assert (audio.getnchannels(), audio.getframerate(), audio.getnframes()) == (2, 10, 25)
        assert audio.readframes(25) == pcm


def test_catalogue_recovery(tmp_path):
    store = MeetingStore(tmp_path)
    with pytest.raises(ValueError):
        store.create(' ')
    interrupted = store.create('Réunion technique')
    completed = store.create('Terminée')
    store.finish(completed, 'completed')
    assert store.recover() == 1
    states = {r['id']: r['status'] for r in store.list()}
    assert states == {interrupted: 'interrupted', completed: 'completed'}
    assert store.recover() == 0


class FakeStream:
    def __init__(self, callback, fault=0):
        self.callback = callback
        self.fault = fault
        self.closed = False

    def start_stream(self):
        self.callback(b'\x01\x00' * 12, 12, self.fault)

    def is_active(self):
        return True

    def stop_stream(self):
        pass

    def close(self):
        self.closed = True


class FakeBackend:
    def __init__(self, fail_open=False, fault=0):
        self.streams = []
        self.closed = False
        self.fail_open = fail_open
        self.fault = fault
        self.opened = threading.Event()

    def open(self, device, callback):
        if self.fail_open and self.streams:
            raise OSError('device disconnected')
        stream = FakeStream(callback, self.fault)
        self.streams.append(stream)
        self.opened.set()
        return stream

    def close(self):
        self.closed = True


def run_session(tmp_path, backend):
    store = MeetingStore(tmp_path)
    devices = [Device(i, f'source {i}', 10, 1, bool(i)) for i in range(2)]
    session = RecordingSession(store, 'Test', devices, lambda: backend)
    session.start()
    assert backend.opened.wait(3)
    session.stop()
    assert session.done.wait(3)
    session.thread.join()
    return store, session


def test_two_sources_stop_and_flush(tmp_path):
    backend = FakeBackend()
    store, session = run_session(tmp_path, backend)
    assert not session.error
    assert store.list()[0]['status'] == 'completed'
    assert backend.closed and all(s.closed for s in backend.streams)
    for i in range(2):
        fragments = list((tmp_path / session.meeting_id / f'track-{i:02d}').glob('*.wav'))
        assert len(fragments) == 2


def test_partial_start_failure_cleans_up(tmp_path):
    backend = FakeBackend(fail_open=True)
    store, session = run_session(tmp_path, backend)
    assert 'disconnected' in session.error
    assert store.list()[0]['status'] == 'failed'
    assert backend.closed and backend.streams[0].closed


def test_overflow_is_visible(tmp_path):
    store, session = run_session(tmp_path, FakeBackend(fault=2))
    assert 'Incident audio' in session.error
    assert store.list()[0]['status'] == 'failed'


def test_bad_pcm_and_empty_export(tmp_path):
    writer = FragmentWriter(tmp_path / 'track', 10, 2, {})
    with pytest.raises(ValueError, match='PCM'):
        writer.write(b'1', 0)
    with pytest.raises(ValueError, match='fragment'):
        export_track(tmp_path / 'track', tmp_path / 'empty.wav')


def test_failed_export_preserves_destination(tmp_path):
    writer = FragmentWriter(tmp_path / 'track', 10, 1, {})
    writer.write(b'\0\0' * 10, 0)
    (tmp_path / 'track' / '00000000.wav').write_bytes(b'bad wav')
    target = tmp_path / 'out.wav'
    target.write_bytes(b'previous export')
    with pytest.raises((wave.Error, EOFError)):
        export_track(tmp_path / 'track', target)
    assert target.read_bytes() == b'previous export'
    assert not target.with_suffix('.wav.part').exists()


def test_queue_saturation_fails_instead_of_silent_loss(tmp_path):
    class BurstStream(FakeStream):
        def start_stream(self):
            for _ in range(120):
                self.callback(b'\0\0' * 10, 10, 0)

    class BurstBackend(FakeBackend):
        def open(self, device, callback):
            stream = BurstStream(callback)
            self.streams.append(stream)
            self.opened.set()
            return stream

    store, session = run_session(tmp_path, BurstBackend())
    assert 'saturée' in session.error
    assert store.list()[0]['status'] == 'failed'


def test_disk_failure_stops_and_releases_sources(tmp_path, monkeypatch):
    def disk_full(*args):
        raise OSError('disk full')

    monkeypatch.setattr(FragmentWriter, 'write', disk_full)
    backend = FakeBackend()
    store, session = run_session(tmp_path, backend)
    assert 'disk full' in session.error
    assert store.list()[0]['status'] == 'failed'
    assert backend.closed and all(stream.closed for stream in backend.streams)


def test_native_audio_dependency_loads_on_windows():
    import sys
    if sys.platform == 'win32':
        import pyaudiowpatch
        assert pyaudiowpatch.paWASAPI is not None
