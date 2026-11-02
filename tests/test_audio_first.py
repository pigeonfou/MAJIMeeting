"""Stage invalidation, source timing and audio-first orchestration, without GPU doubles claims."""
import json
import threading
import wave
from concurrent.futures import CancelledError
from dataclasses import replace
from types import SimpleNamespace

import numpy as np
import pytest
from test_transcription import local_options, recorded

from majimeeting.analysis_cache import cached_stage
from majimeeting.audio_first_pipeline import process_audio_first
from majimeeting.audio_preparation import (
    PreparationOptions,
    PreparedBatches,
    detect_speech,
    prepare_meeting,
    transcription_windows,
)
from majimeeting.diarization import diarize
from majimeeting.diarization_options import DiarizationOptions
from majimeeting.speakers import history
from majimeeting.storage import FragmentWriter, MeetingStore


@pytest.fixture
def setup(tmp_path):
    store = MeetingStore(tmp_path / 'data')
    meeting = recorded(store, seconds=3, offset=.4)
    whisper = local_options(tmp_path)
    community = tmp_path / 'community'
    community.mkdir()
    (community / 'config.yaml').write_text('local model double')
    python = tmp_path / 'python.exe'
    python.write_text('isolated runtime double')
    calls = []
    def detector(samples):
        calls.append('vad')
        return [dict(start=0, end=len(samples))]
    def worker(*args):
        calls.append('voices')
        return dict(turns=[dict(start=0, end=.6, label='A'), dict(start=.6, end=3.1, label='B')],
                    exclusive_turns=[dict(start=0, end=.6, label='A'), dict(start=.6, end=3, label='B')],
                    effective=dict(devices={'segmentation': 'cpu', 'embedding': 'cpu'}))
    class Model:
        def __init__(self, *args, **kwargs):
            calls.append('whisper')
        def transcribe(self, path, **kwargs):
            assert kwargs['word_timestamps']
            return iter([SimpleNamespace(start=.2, end=1., text='Bonjour Alice', words=[
                dict(start=.2, end=.6, word='Bonjour', probability=.95),
                dict(start=.6, end=1., word=' Alice', probability=.95)])]), None
    def run(preparation=None, tuning=None, **extra):
        return process_audio_first(store, meeting, whisper, python, community, 'cpu', 0,
            tuning or DiarizationOptions(), preparation or PreparationOptions(),
            detector=detector, worker=worker, model_factory=Model, **extra)
    return SimpleNamespace(store=store, meeting=meeting, whisper=whisper, community=community,
                           python=python, calls=calls, detector=detector, worker=worker,
                           Model=Model, run=run)


def test_audio_first_order_absolute_words_and_cache_reuse(setup):
    first = setup.run()
    assert setup.calls == ['vad', 'voices', 'whisper']
    rows = setup.store.segments(first)
    assert [r['speaker_group'] for r in rows] == ['track-00:A', 'track-00:B']
    assert [r['start'] for r in rows] == pytest.approx([.6, 1.])
    assert ''.join(r['text'] for r in rows) == 'Bonjour Alice'
    analysis = history(setup.store, first)[0]
    assert json.loads(analysis['options'])['exclusive_turns'][0]['start'] == pytest.approx(.4)
    second = setup.run()
    assert first != second and setup.calls == ['vad', 'voices', 'whisper', 'whisper']
    with setup.store.connect() as db:
        details = json.loads(db.execute('SELECT options FROM transcription_jobs WHERE id=?', (second,)).fetchone()[0])
    assert details['pipeline']['stages'][0]['audio_reused']
    assert details['pipeline']['stages'][0]['vad_reused']
    assert details['pipeline']['voices'][0]['reused']


def test_threshold_only_invalidates_vad_and_grouping_only_invalidates_voices(setup):
    setup.run()
    setup.run(preparation=PreparationOptions(vad_threshold=.6))
    assert setup.calls.count('vad') == 2 and setup.calls.count('voices') == 1
    setup.run(tuning=DiarizationOptions(threshold=.7))
    assert setup.calls.count('vad') == 2 and setup.calls.count('voices') == 2
    (setup.community / 'config.yaml').write_text('another local model revision')
    setup.run(tuning=DiarizationOptions(threshold=.7))
    assert setup.calls.count('voices') == 3


def test_reanalysis_reuses_pcm_vad_and_text_and_preserves_manual_edits(setup):
    job = setup.run()
    piece = setup.store.segments(job)[0]['piece_id']
    from majimeeting.speaker_pieces import edit_piece
    edit_piece(setup.store, piece, 'Bonjour corrigé', 'Alice')
    diarize(setup.store, job, setup.python, setup.community, worker=setup.worker,
            tuning=DiarizationOptions(threshold=.7))
    assert setup.calls == ['vad', 'voices', 'whisper', 'voices']
    assert len(history(setup.store, job)) == 2
    assert setup.store.segments(job)[0]['corrected_text'] == 'Bonjour corrigé'
    assert setup.store.segments(job)[0]['speaker'] == 'Alice'


def test_source_change_invalidates_pcm_without_touching_old_result(setup):
    job = setup.run()
    path = next((setup.store.root / setup.meeting / 'track-00').glob('*.wav'))
    raw = path.read_bytes()
    path.write_bytes(raw[:-2] + b'\x01\x00')
    setup.run()
    assert setup.calls.count('vad') == setup.calls.count('voices') == 2
    assert setup.store.segments(job)[0]['text'] == 'Bonjour'


def test_corrupt_cache_artifact_and_manifest_are_not_reused(setup):
    prepared = prepare_meeting(setup.store, setup.meeting, PreparationOptions(), detector=setup.detector)
    stage = prepared[0]['audio']['path']
    (stage / 'audio.wav').write_bytes(b'corrupt')
    repaired = prepare_meeting(setup.store, setup.meeting, PreparationOptions(), detector=setup.detector)
    assert not repaired[0]['audio']['reused']
    with wave.open(str(stage / 'audio.wav'), 'rb') as audio:
        assert audio.getnframes() == 3 * 16000
    vad_stage = repaired[0]['speech']['path']
    (vad_stage / 'stage.json').write_text('{}')
    assert not prepare_meeting(setup.store, setup.meeting, PreparationOptions(), detector=setup.detector)[0]['speech']['reused']


def test_cancel_does_not_publish_stage_and_resume_reuses_completed_work(setup):
    cancel = threading.Event()
    def interrupted(samples):
        cancel.set()
        raise CancelledError('VAD interrompu')
    with pytest.raises(CancelledError):
        prepare_meeting(setup.store, setup.meeting, PreparationOptions(), cancel, detector=interrupted)
    root = setup.store.root / setup.meeting / 'analysis-cache/v1'
    assert not list(root.rglob('.stage-*'))
    assert len(list((root / 'audio').glob('*/stage.json'))) == 1
    assert not list((root / 'vad').glob('*/stage.json'))
    result = prepare_meeting(setup.store, setup.meeting, PreparationOptions(), detector=setup.detector)
    assert result[0]['audio']['reused'] and not result[0]['speech']['reused']


def test_worker_failure_is_not_cached_and_does_not_create_transcription(setup):
    def fail(*args):
        raise RuntimeError('interrupted Community-1')
    with pytest.raises(RuntimeError, match='Community-1'):
        process_audio_first(setup.store, setup.meeting, setup.whisper, setup.python,
            setup.community, 'cpu', 0, DiarizationOptions(), PreparationOptions(),
            detector=setup.detector, worker=fail)
    assert not setup.store.transcription_jobs(setup.meeting)
    assert not list((setup.store.root / setup.meeting / 'analysis-cache/v1/voices').glob('*/stage.json'))
    setup.run()
    assert setup.calls.count('vad') == 1


def test_silent_track_uses_real_offline_vad_and_loads_no_ai_models(setup, monkeypatch):
    import socket
    monkeypatch.setattr(socket.socket, 'connect', lambda *a: (_ for _ in ()).throw(AssertionError('network')))
    job = process_audio_first(setup.store, setup.meeting, setup.whisper, setup.python,
        setup.community, 'cpu', 0, DiarizationOptions(), PreparationOptions(),
        worker=setup.worker, model_factory=setup.Model)
    assert setup.calls == []
    assert not setup.store.segments(job)
    with setup.store.connect() as db:
        metadata = json.loads(db.execute('SELECT options FROM transcription_jobs WHERE id=?', (job,)).fetchone()[0])
    assert metadata['pipeline']['no_speech']
    assert metadata['metrics']['attempts'][0]['skipped_no_speech']


def test_moderate_normalization_preserves_originals_and_gap_positions(tmp_path):
    store = MeetingStore(tmp_path / 'data')
    meeting = store.create('Gaps')
    track = store.root / meeting / 'track-00'
    writer = FragmentWriter(track, 16000, 1, {})
    writer.write(np.full(16000, 1000, dtype='<i2').tobytes(), 2.)
    writer.write(np.full(16000, -1000, dtype='<i2').tobytes(), 5.)
    writer.close()
    (track / '00000001.json').write_text(json.dumps(dict(start_seconds=5., frames=16000)))
    store.finish(meeting, 'completed')
    original = {p.name: p.read_bytes() for p in track.iterdir()}
    p = prepare_meeting(store, meeting, PreparationOptions(normalize=True), detector=lambda _: [])[0]
    assert original == {p.name: p.read_bytes() for p in track.iterdir()}
    assert p['audio']['result']['origin'] == 2
    assert p['audio']['result']['duration'] == 4
    assert p['audio']['result']['levels']['gain'] == 2
    with wave.open(str(p['audio']['path'] / 'audio.wav'), 'rb') as audio:
        pcm = np.frombuffer(audio.readframes(audio.getnframes()), dtype='<i2')
    assert pcm[0] == 2000 and pcm[-1] == -2000
    assert not pcm[16000:48000].any()


def test_vad_block_boundaries_do_not_shift_or_duplicate_speech(tmp_path):
    path = tmp_path / 'audio.wav'
    with wave.open(str(path), 'wb') as audio:
        audio.setparams((1, 2, 16000, 0, 'NONE', 'not compressed'))
        audio.writeframes(b'\0\0' * 602 * 16000)
    regions = detect_speech(path, PreparationOptions(),
                            detector=lambda samples: [dict(start=0, end=len(samples))])
    assert regions == [[0., 602.]]
    assert transcription_windows(regions, 602, [dict(end=298)], 300) == [(0, 298.), (298., 598.), (598., 602)]
    assert transcription_windows([[5, 6], [8, 9], [100, 102]], 110) == [(4.25, 9.75), (99.25, 102.75)]


@pytest.mark.parametrize('workers', [1, 2])
def test_prepared_batch_adapter_is_used_by_both_inference_paths(setup, workers):
    from majimeeting.transcription import transcribe_meeting
    prepared = prepare_meeting(setup.store, setup.meeting, PreparationOptions(),
                                detector=lambda _: [dict(start=16000, end=32000)])
    voices = [dict(track='track-00', stage=dict(result=dict(exclusive_turns=[])))]
    batches = PreparedBatches(prepared, voices)
    class Model(setup.Model):
        def transcribe(self, path, **kwargs):
            with wave.open(str(path), 'rb') as audio:
                assert audio.getnframes() == 40000  # 0.25 .. 2.75 seconds of original track
            return super().transcribe(path, **kwargs)
    options = replace(setup.whisper, batched=True, gpu_workers=workers)
    job = transcribe_meeting(setup.store, setup.meeting, options, model_factory=Model,
                             pipeline_factory=lambda model: model, batch_source=batches)
    with setup.store.connect() as db:
        row = db.execute('SELECT start FROM transcript_segments WHERE job_id=?', (job,)).fetchone()
    assert row['start'] == pytest.approx(.4 + .25 + .2)


def test_cancelled_cache_validation_propagates_without_quarantining_good_result(tmp_path):
    def build(stage):
        (stage / 'audio').write_bytes(b'original')
        return {'done': True}
    first = cached_stage(tmp_path, 'audio', {}, build)
    cancel = threading.Event()
    cancel.set()
    with pytest.raises(CancelledError):
        cached_stage(tmp_path, 'audio', {}, build, cancel)
    assert (first['path'] / 'stage.json').is_file()
    assert not list(tmp_path.rglob('*.invalid-*'))


def test_reanalysis_refuses_changed_original_timing_and_retains_previous_analysis(setup):
    job = setup.run()
    track = setup.store.root / setup.meeting / 'track-00'
    for metadata in track.glob('*.json'):
        if metadata.name == 'track.json':
            continue
        data = json.loads(metadata.read_text())
        data['start_seconds'] += .1
        metadata.write_text(json.dumps(data))
    with pytest.raises(ValueError, match='originales ont changé'):
        diarize(setup.store, job, setup.python, setup.community, worker=setup.worker)
    assert len(history(setup.store, job)) == 1
    assert setup.store.segments(job)[0]['start'] == pytest.approx(.6)


def test_invalid_vad_output_does_not_publish_result(setup):
    with pytest.raises(ValueError, match='Bornes VAD'):
        prepare_meeting(setup.store, setup.meeting, PreparationOptions(),
                        detector=lambda _: [dict(start=-1, end=100)])
    root = setup.store.root / setup.meeting / 'analysis-cache/v1/vad'
    assert not list(root.glob('*/stage.json'))


def test_ui_routes_new_option_and_disables_preparation_during_work(tmp_path, monkeypatch, qt_application):
    from PySide6.QtCore import QSettings
    from PySide6.QtWidgets import QDialog

    import majimeeting.audio_first_pipeline as pipeline
    import majimeeting.processing_ui as ui
    from majimeeting.__main__ import MainWindow
    from majimeeting.diarization_ui import DiarizationDialog
    from majimeeting.pipeline_controls import PipelineControls
    store = MeetingStore(tmp_path / 'data')
    meeting = recorded(store)
    settings = QSettings(str(tmp_path / 'settings.ini'), QSettings.Format.IniFormat)
    monkeypatch.setattr(ui, 'application_settings', lambda: settings)
    window = MainWindow(store, scan=False)
    window.meetings.setCurrentRow(0)
    controls = window.processing.pipeline_controls
    assert controls.mode.currentData() == 'legacy'
    assert not controls.normalize.isEnabled()
    controls.mode.setCurrentIndex(1)
    assert controls.normalize.isEnabled()
    controls.normalize.setChecked(True)
    controls.threshold.setValue(.6)
    calls = []
    monkeypatch.setattr(DiarizationDialog, 'exec', lambda _: QDialog.DialogCode.Accepted)
    monkeypatch.setattr(DiarizationDialog, 'values', lambda _: ('python', 'community', 'cpu', 0, {}))
    def process(*args):
        calls.append(args)
        store.start_transcription('ui-result', meeting, args[2])
        store.finish_transcription('ui-result', 'completed')
        return 'ui-result'
    monkeypatch.setattr(pipeline, 'process_audio_first', process)
    monkeypatch.setattr(window.processing, 'open_speakers', lambda: calls.append('naming'))
    window.processing.transcribe(complete=True)
    assert not controls.isEnabled()
    window.task[1].result(timeout=5)
    window.poll()
    qt_application.processEvents()
    assert calls[0][8] == PreparationOptions(True, .6, 500)
    assert calls[-1] == 'naming'
    assert controls.isEnabled()
    remembered = PipelineControls(settings)
    assert remembered.mode.currentData() == 'audio_first_v1'
    assert remembered.normalize.isChecked() and remembered.threshold.value() == .6
    window.close()
    remembered.close()


def test_exclusive_output_never_hides_simultaneous_voices(setup):
    def worker(*args):
        return dict(turns=[dict(start=0, end=3, label='A'), dict(start=.5, end=2, label='B')],
                    exclusive_turns=[dict(start=0, end=1, label='A'), dict(start=1, end=3, label='B')])
    job = process_audio_first(setup.store, setup.meeting, setup.whisper, setup.python,
        setup.community, 'cpu', 0, DiarizationOptions(), PreparationOptions(),
        detector=setup.detector, worker=worker, model_factory=setup.Model)
    rows = setup.store.segments(job)
    assert ''.join(r['text'] for r in rows) == 'Bonjour Alice'
    assert any(r['speaker_reason'] == 'overlap' and not r['speaker_group'] for r in rows)
    assert len(history(setup.store, job)[0]['turns']) == 2


def test_runtime_revision_invalidates_voice_cache(setup):
    setup.run()
    setup.python.write_text('updated isolated runtime')
    setup.run()
    assert setup.calls == ['vad', 'voices', 'whisper', 'voices', 'whisper']


def test_precomputed_decode_clips_are_bounded_and_keep_original_offsets(setup):
    from majimeeting.audio_preparation import PreparedBatches
    prepared = prepare_meeting(setup.store, setup.meeting, PreparationOptions(), detector=setup.detector)
    prepared[0]['audio']['result']['duration'] = 95.
    prepared[0]['speech']['result']['regions'] = [[0., 95.]]
    batches = PreparedBatches(prepared, [dict(track='track-00', stage=dict(result={'exclusive_turns': []}))])
    decoded = batches.decode_options('track-00', .4, 95, True)
    assert decoded['vad_filter'] is False
    assert len(decoded['clip_timestamps']) == 4
    assert all(0 <= c['start'] < c['end'] <= 95 and c['end'] - c['start'] <= 30
               for c in decoded['clip_timestamps'])
    assert sum(c['end'] - c['start'] for c in decoded['clip_timestamps']) == 95
    serial = batches.decode_options('track-00', .4, 95, False)
    assert serial['clip_timestamps'] == [0., 29.5, 29.5, 59., 59., 88.5, 88.5, 95.]



def test_cache_uses_short_windows_paths_but_checks_full_key(tmp_path):
    from majimeeting.analysis_cache import file_digest
    result = cached_stage(tmp_path, 'audio', {}, lambda _: dict(ok=True))
    assert len(result['path'].name) == 24 and len(result['key']) == 64
    manifest_path = result['path'] / 'stage.json'
    manifest = json.loads(manifest_path.read_text())
    manifest['key'] = result['key'][:24] + 'f' * 40
    manifest_path.write_text(json.dumps(manifest))
    (result['path'] / 'ready.sha256').write_text(file_digest(manifest_path))
    with pytest.raises(RuntimeError, match='Collision'):
        cached_stage(tmp_path, 'audio', {}, lambda _: pytest.fail('must retain existing stage'))
    assert manifest_path.exists()
