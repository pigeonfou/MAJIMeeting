import json
import sys
import threading
import wave
from concurrent.futures import CancelledError

import pytest
from test_editor import prepared

from majimeeting.diarization import diarize, prepare_track, run_worker
from majimeeting.speakers import complete_run, history, match_turns, name_group, start_run


def turn(start, end, label='SPEAKER_00', track='track-00'):
    return dict(start=start, end=end, label=label, track=track)


@pytest.mark.parametrize('turns,expected', [
    ([turn(0, 2)], ('SPEAKER_00', False)),
    ([turn(0, 1, 'A'), turn(1, 2, 'B')], ('', True)),
    ([turn(0, 2, 'A'), turn(.5, 1, 'B')], ('', True)),
    ([turn(0, .4), turn(0, .4)], ('', True)),  # duplicated evidence cannot boost coverage
    ([], ('', False)),
])
def test_conservative_assignment(turns, expected):
    assert match_turns(0, 2, turns) == expected


def test_group_names_and_manual_overrides_survive_reanalysis(tmp_path):
    store, _ = prepared(tmp_path)
    first = start_run(store, 'job', {'engine': 'test'})
    complete_run(store, first, [turn(1.5, 3.5)])
    original = store.segments('job')[0]
    assert original['speaker'] == 'track-00:SPEAKER_00'
    name_group(store, 'job', original['speaker_group'], 'Alice')
    assert store.segments('job')[0]['speaker'] == 'Alice'
    store.edit_segment(original['id'], 'Correction', 'Bob')
    name_group(store, 'job', original['speaker_group'], 'Carol')
    assert store.segments('job')[0]['speaker'] == 'Bob'
    second = start_run(store, 'job', {})
    complete_run(store, second, [turn(1.5, 3.5, 'NEW')])
    assert store.segments('job')[0]['speaker'] == 'Bob'
    assert store.segments('job')[0]['corrected_text'] == 'Correction'
    assert len(history(store, 'job')[0]['names']) == 2
    assert history(store, 'job')[0]['turns'][0]['label'] == 'SPEAKER_00'
    store.edit_segment(original['id'], 'Correction', '')
    assert store.segments('job')[0]['speaker'] == ''  # explicit human clearing wins


def test_failure_or_restart_never_replaces_previous_success(tmp_path):
    store, _ = prepared(tmp_path)
    first = start_run(store, 'job', {})
    complete_run(store, first, [turn(1.5, 3.5)])
    second = start_run(store, 'job', {})
    with pytest.raises(ValueError):
        complete_run(store, second, [turn(1, float('nan'))])
    store.recover()
    assert store.segments('job')[0]['speaker'] == 'track-00:SPEAKER_00'
    assert history(store, 'job')[1]['status'] == 'interrupted'
    with store.connect() as db:
        assert db.execute('SELECT COUNT(*) FROM speaker_turns WHERE run_id=?', (second,)).fetchone()[0] == 0


def test_prepare_audio_preserves_source_origin_and_silence_gap(tmp_path):
    store, meeting = prepared(tmp_path)
    track = store.root / meeting / 'track-00'
    path = track / '00000001.json'
    timing = json.loads(path.read_text())
    timing['start_seconds'] += 2
    path.write_text(json.dumps(timing))
    target = tmp_path / 'mono.wav'
    origin, duration = prepare_track(track, target)
    assert (origin, duration) == (1.5, 4)
    with wave.open(str(target)) as audio:
        assert (audio.getframerate(), audio.getnchannels(), audio.getsampwidth()) == (16000, 1, 2)
        audio.setpos(16000)
        assert audio.readframes(32000) == b'\0\0' * 32000


def runtime(tmp_path):
    model = tmp_path / 'community-1'
    model.mkdir()
    (model / 'config.yaml').write_text('local-model')
    return sys.executable, str(model)


def test_diarization_maps_offset_and_keeps_text(tmp_path):
    store, _ = prepared(tmp_path)
    python, model = runtime(tmp_path)
    def worker(*args):
        return [dict(start=.1, end=1.8, label='SPEAKER_00')]
    diarize(store, 'job', python, model, worker=worker)
    row = store.segments('job')[0]
    assert row['speaker'] == 'track-00:SPEAKER_00'
    assert row['corrected_text'] == 'Original'
    assert (row['start'], row['end']) == (1.75, 2.25)
    evidence = history(store, 'job')[0]['turns'][0]
    assert evidence['start'] == pytest.approx(1.6)


@pytest.mark.parametrize('cancelled', [False, True])
def test_worker_failure_or_cancel_publishes_no_partial_assignments(tmp_path, cancelled):
    store, _ = prepared(tmp_path)
    python, model = runtime(tmp_path)
    def worker(*args):
        raise CancelledError() if cancelled else RuntimeError('model unavailable')
    with pytest.raises(CancelledError if cancelled else RuntimeError):
        diarize(store, 'job', python, model, worker=worker)
    assert store.segments('job')[0]['speaker'] == ''
    assert history(store, 'job')[0]['status'] == ('cancelled' if cancelled else 'failed')


def test_cancel_terminates_external_runtime(tmp_path, monkeypatch):
    import majimeeting.diarization as module
    monkeypatch.setattr(module, 'WORKER', 'import time; time.sleep(60)')
    cancel = threading.Event()
    cancel.set()
    with pytest.raises(CancelledError):
        run_worker(sys.executable, tmp_path, tmp_path / 'audio.wav', tmp_path / 'result.json',
                   'cpu', 0, cancel, lambda _: None)


def test_editor_group_rename_and_json_export(tmp_path, monkeypatch):
    from PySide6.QtWidgets import QApplication

    from majimeeting.__main__ import MainWindow
    from majimeeting.editor_ui import TranscriptEditor
    app = QApplication.instance() or QApplication([])
    store, _ = prepared(tmp_path)
    run = start_run(store, 'job', {})
    complete_run(store, run, [turn(1.5, 3.5)])
    dialog = TranscriptEditor(store, 'job')
    monkeypatch.setattr('majimeeting.editor_ui.QInputDialog.getText', lambda *a: ('Alice', True))
    assert dialog.rename.isEnabled()
    dialog.rename_group()
    assert dialog.rows[0]['speaker'] == 'Alice'
    dialog.done(0)
    window = MainWindow(store, scan=False)
    destination = tmp_path / 'export.json'
    window.processing.write_export('job', destination)
    result = json.loads(destination.read_text())
    assert result['segments'][0]['speaker'] == 'Alice'
    assert result['diarization'][0]['names'][0]['name'] == 'Alice'
    window.close()
    app.processEvents()
