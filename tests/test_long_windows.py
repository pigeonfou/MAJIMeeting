import json
import wave
from dataclasses import replace
from types import SimpleNamespace

import pytest
from test_transcription import local_options

from majimeeting.storage import FragmentWriter, MeetingStore
from majimeeting.transcription import audio_batches, transcribe_meeting


def make_track(store, meeting, name, start=0, seconds=1250):
    track = store.root / meeting / name
    writer = FragmentWriter(track, 10, 1, {})
    # Small sample rate keeps long-timeline regression fixtures compact.
    writer.write(b'\x01\x00' * 10 * seconds, start)
    writer.close()
    return track


def test_long_window_removes_artificial_boundaries_without_changing_pcm(tmp_path):
    store = MeetingStore(tmp_path / 'data')
    meeting = store.create('Longue réunion')
    track = make_track(store, meeting, 'track-00', start=13.5)
    destination = tmp_path / 'window.wav'
    outputs = []
    for limit in (600, 1800):
        bounds, pcm = [], b''
        for offset, duration in audio_batches(track, destination, max_seconds=limit):
            bounds.append((offset, duration))
            with wave.open(str(destination), 'rb') as audio:
                pcm += audio.readframes(audio.getnframes())
        outputs.append((bounds, pcm))
    assert outputs[0][0] == [(13.5, 600), (613.5, 600), (1213.5, 50)]
    assert outputs[1][0] == [(13.5, 1250)]
    assert outputs[0][1] == outputs[1][1] == b'\x01\x00' * 12500


@pytest.mark.parametrize('workers', [1, 2])
@pytest.mark.parametrize('window_seconds', [900, 1200, 1500, 1800])
def test_long_windows_keep_tracks_gaps_absolute_times_and_execution(tmp_path, workers, window_seconds):
    store = MeetingStore(tmp_path / 'data')
    meeting = store.create('Pistes séparées')
    track = make_track(store, meeting, 'track-00', start=13.5, seconds=10)
    sidecars = sorted(track.glob('*.json'))
    fragments = [p for p in sidecars if p.name != 'track.json']
    # A recovered-track gap must never be filled by joining the PCM.
    for fragment in fragments[5:]:
        timing = json.loads(fragment.read_text())
        timing['start_seconds'] += 7
        fragment.write_text(json.dumps(timing))
    make_track(store, meeting, 'track-01', start=2, seconds=5)
    store.finish(meeting, 'completed')

    class Pipeline:
        def __init__(self, model):
            pass

        def transcribe(self, path, **kwargs):
            with wave.open(path, 'rb') as audio:
                assert audio.getnframes() == 50
            return iter([SimpleNamespace(start=0, end=1, text='Source')]), None

    options = replace(local_options(tmp_path), device='cuda', compute_type='float16',
                      batched=True, batch_size=32, gpu_workers=workers, window_seconds=window_seconds)
    job = transcribe_meeting(store, meeting, options, model_factory=lambda *a, **k: object(),
                            pipeline_factory=Pipeline, cuda_prepare=lambda _: None)
    actual = sorted((r['track'], r['start'], r['end']) for r in store.segments(job))
    assert actual == [('track-00', 13.5, 14.5), ('track-00', 25.5, 26.5),
                      ('track-01', 2, 3)]
    details = json.loads(store.transcription_jobs(meeting)[0]['options'])
    assert details['execution']['window_seconds'] == window_seconds
    assert details['metrics']['attempts'][0]['completed_audio_seconds'] == 15
