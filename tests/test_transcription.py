import json
import threading
import wave
from concurrent.futures import CancelledError
from types import SimpleNamespace

import pytest

from majimeeting.storage import FragmentWriter, MeetingStore
from majimeeting.transcription import (
    TranscriptionOptions,
    audio_batches,
    import_audio,
    transcribe_meeting,
)


def local_options(tmp_path):
    folder = tmp_path / 'model'
    folder.mkdir()
    for name in ('model.bin', 'config.json', 'tokenizer.json'):
        (folder / name).write_bytes(b'test double, no actual model')
    return TranscriptionOptions(str(folder))


def recorded(store, seconds=3, offset=.4):
    meeting = store.create('Test transcription')
    writer = FragmentWriter(store.root / meeting / 'track-00', 16000, 1, {})
    writer.write(b'\0\0' * 16000 * seconds, offset)
    writer.close()
    store.finish(meeting, 'completed')
    return meeting


def test_streaming_import_preserves_original_and_pcm(tmp_path):
    source = tmp_path / 'réunion.wav'
    pcm = b'\x20\x00' * 36000
    with wave.open(str(source), 'wb') as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(16000)
        audio.writeframes(pcm)
    store = MeetingStore(tmp_path / 'data')
    meeting = import_audio(store, source)
    folder = store.root / meeting
    assert (folder / 'original.wav').read_bytes() == source.read_bytes()
    chunks = sorted((folder / 'track-00').glob('*.wav'))
    actual = bytearray()
    for chunk in chunks:
        with wave.open(str(chunk)) as audio:
            actual.extend(audio.readframes(audio.getnframes()))
    assert actual == pcm
    assert store.list()[0]['status'] == 'completed'


def test_invalid_import_and_cancel_are_persistent(tmp_path):
    store = MeetingStore(tmp_path / 'data')
    bad = tmp_path / 'bad.mp3'
    bad.write_bytes(b'not audio')
    with pytest.raises(Exception):
        import_audio(store, bad)
    assert store.list()[0]['status'] == 'failed'
    cancel = threading.Event()
    cancel.set()
    with pytest.raises(CancelledError):
        import_audio(store, bad, cancel)
    assert store.list()[0]['status'] == 'interrupted'
    assert not list(store.root.rglob('*.part'))


def test_batches_bound_duration_and_preserve_offsets(tmp_path):
    store = MeetingStore(tmp_path / 'data')
    meeting = recorded(store, 5, 1.2)
    batches = list(audio_batches(store.root / meeting / 'track-00', tmp_path / 'batch.wav',
                                 max_seconds=2))
    assert batches == [(1.2, 2), (3.2, 2), (5.2, 1)]


def test_batches_preserve_discontinuities(tmp_path):
    store = MeetingStore(tmp_path / 'data')
    meeting = recorded(store)
    track = store.root / meeting / 'track-00'
    (track / '00000002.json').write_text(json.dumps({'start_seconds': 10, 'frames': 16000}))
    assert list(audio_batches(track, tmp_path / 'batch.wav')) == [(0.4, 2), (10, 1)]


def test_transcription_uses_local_model_and_persists_timestamped_text(tmp_path):
    store = MeetingStore(tmp_path / 'data')
    meeting = recorded(store)
    calls = []

    class Model:
        def __init__(self, path, **kwargs):
            calls.append(kwargs)

        def transcribe(self, path, **kwargs):
            calls.append(kwargs)
            return iter([SimpleNamespace(start=.2, end=1.2, text=' Bonjour. ')]), None

    job = transcribe_meeting(store, meeting, local_options(tmp_path), model_factory=Model)
    assert calls[0] == {'device': 'cpu', 'compute_type': 'int8', 'local_files_only': True}
    assert calls[1]['language'] == 'fr'
    segment = store.segments(job)[0]
    assert segment['text'] == 'Bonjour.'
    assert segment['start'] == pytest.approx(.6)
    assert segment['end'] == pytest.approx(1.6)
    assert store.transcription_jobs(meeting)[0]['status'] == 'completed'


def test_failed_retranscription_keeps_previous_result(tmp_path):
    store = MeetingStore(tmp_path / 'data')
    meeting = recorded(store)
    options = local_options(tmp_path)
    store.start_transcription('previous', meeting, options)
    store.add_segment('previous', 'track-00', 0, 1, 'Texte conservé')
    store.finish_transcription('previous', 'completed')

    def failure(*args, **kwargs):
        raise RuntimeError('CUDA unavailable')

    with pytest.raises(RuntimeError, match='CUDA unavailable'):
        transcribe_meeting(store, meeting, options, model_factory=failure)
    assert store.segments('previous')[0]['text'] == 'Texte conservé'
    assert store.transcription_jobs(meeting)[0]['status'] == 'failed'


def test_cancel_preserves_completed_segments(tmp_path):
    store = MeetingStore(tmp_path / 'data')
    meeting = recorded(store)
    cancel = threading.Event()

    class Model:
        def __init__(self, *args, **kwargs):
            pass

        def transcribe(self, *args, **kwargs):
            def segments():
                yield SimpleNamespace(start=0, end=1, text='Conservé')
                cancel.set()
                yield SimpleNamespace(start=1, end=2, text='Annulé')
            return segments(), None

    with pytest.raises(CancelledError):
        transcribe_meeting(store, meeting, local_options(tmp_path), cancel, model_factory=Model)
    job = store.transcription_jobs(meeting)[0]
    assert job['status'] == 'cancelled'
    assert len(store.segments(job['id'])) == 1


def test_running_jobs_recover_after_interruption(tmp_path):
    store = MeetingStore(tmp_path / 'data')
    meeting = recorded(store)
    store.start_transcription('interrupted', meeting, local_options(tmp_path))
    assert store.recover() == 0
    assert store.transcription_jobs(meeting)[0]['status'] == 'interrupted'


def test_missing_model_does_not_start_job_or_download(tmp_path):
    store = MeetingStore(tmp_path / 'data')
    meeting = recorded(store)
    with pytest.raises(ValueError, match='modèle'):
        transcribe_meeting(store, meeting, TranscriptionOptions(str(tmp_path / 'missing')))
    assert not store.transcription_jobs(meeting)


@pytest.mark.parametrize(('suffix', 'codec', 'container_format'), [
    ('.mp3', 'libmp3lame', 'mp3'), ('.flac', 'flac', 'flac'), ('.m4a', 'aac', 'mp4'),
])
def test_compressed_import_resamples_stereo_to_16khz_mono(tmp_path, suffix, codec,
                                                        container_format):
    import av
    import numpy as np
    source = tmp_path / ('compressed' + suffix)
    with av.open(str(source), 'w', format=container_format) as output:
        stream = output.add_stream(codec, rate=48000)
        stream.layout = 'stereo'
        frame = av.AudioFrame.from_ndarray(np.zeros((1, 96000), dtype=np.int16),
                                           format='s16', layout='stereo')
        frame.sample_rate = 48000
        for packet in stream.encode(frame):
            output.mux(packet)
        for packet in stream.encode(None):
            output.mux(packet)
    store = MeetingStore(tmp_path / 'data')
    meeting = import_audio(store, source)
    folder = store.root / meeting / 'track-00'
    duration = 0
    for chunk in folder.glob('*.wav'):
        with wave.open(str(chunk)) as audio:
            assert audio.getnchannels() == 1
            assert audio.getframerate() == 16000
            duration += audio.getnframes() / audio.getframerate()
    assert duration == pytest.approx(1, abs=.1)
