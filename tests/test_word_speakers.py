import json

import pytest
from test_editor import prepared
from test_speakers import turn

from majimeeting.speaker_overview import SpeakerOverview, samples, speaker_display
from majimeeting.speaker_pieces import edit_piece
from majimeeting.speakers import complete_run, history, name_group, select_run, start_run
from majimeeting.word_alignment import align_existing, save_words


def timed_transcript(tmp_path):
    store, _ = prepared(tmp_path)
    with store.connect() as db:
        db.execute('DELETE FROM transcript_segments')
    sid = store.add_segment('job', 'track-00', 1.5, 3.5, 'Bonjour Alice bonjour Bob', [
        dict(start=1.5, end=1.9, word='Bonjour', probability=.9),
        dict(start=1.9, end=2.4, word=' Alice', probability=.9),
        dict(start=2.5, end=2.9, word=' bonjour', probability=.9),
        dict(start=2.9, end=3.5, word=' Bob', probability=.9)])
    return store, sid


def test_sequential_voices_split_text_without_loss_and_names_apply_to_every_piece(tmp_path):
    store, sid = timed_transcript(tmp_path)
    run = start_run(store, 'job', {})
    complete_run(store, run, [turn(1.5, 2.45, 'A'), turn(2.45, 3.5, 'B')])
    rows = store.segments('job')
    assert len(rows) == 2 and not any(r['speaker_ambiguous'] for r in rows)
    assert [r['speaker_group'] for r in rows] == ['track-00:A', 'track-00:B']
    assert ''.join(r['original_text'] for r in rows) == 'Bonjour Alice bonjour Bob'
    name_group(store, 'job', 'track-00:A', 'Alice')
    assert store.segments('job')[0]['speaker'] == 'Alice'
    with store.connect() as db:
        assert db.execute('SELECT text FROM transcript_segments WHERE id=?', (sid,)).fetchone()[0] == 'Bonjour Alice bonjour Bob'


def test_simultaneous_words_stay_explicit_and_are_never_duplicated(tmp_path):
    store, _ = timed_transcript(tmp_path)
    run = start_run(store, 'job', {})
    complete_run(store, run, [turn(1.5, 3.5, 'A'), turn(2.5, 3.5, 'B')])
    rows = store.segments('job')
    assert ''.join(r['text'] for r in rows) == 'Bonjour Alice bonjour Bob'
    overlap = [r for r in rows if r['speaker_reason'] == 'overlap']
    assert overlap and overlap[0]['speaker'] == ''
    assert overlap[0]['speaker_candidates'] == ['track-00:A', 'track-00:B']
    assert 'Paroles simultanées' in speaker_display(overlap[0])
    assert not samples(store, 'job')[1]['samples']  # no invented isolated sample for B


def test_word_boundary_does_not_make_entire_sentence_ambiguous(tmp_path):
    store, _ = timed_transcript(tmp_path)
    run = start_run(store, 'job', {})
    complete_run(store, run, [turn(1.5, 2.6, 'A'), turn(2.6, 3.5, 'B')])
    rows = store.segments('job')
    assert rows[-1]['speaker_group'] == 'track-00:B'
    assert not any(r['speaker_ambiguous'] for r in rows)  # majority duration of boundary word


def test_original_manual_correction_is_not_redistributed_across_voices(tmp_path):
    store, sid = timed_transcript(tmp_path)
    store.edit_segment(sid, 'Texte corrigé humain', 'Alice')
    run = start_run(store, 'job', {})
    complete_run(store, run, [turn(1.5, 2.45, 'A'), turn(2.45, 3.5, 'B')])
    rows = store.segments('job')
    assert len(rows) == 1 and rows[0]['corrected_text'] == 'Texte corrigé humain'
    assert rows[0]['speaker'] == 'Alice'
    assert rows[0]['speaker_reason'] == 'manual_source_correction'


def test_piece_edits_survive_matching_reanalysis_and_previous_result_is_reusable(tmp_path):
    store, _ = timed_transcript(tmp_path)
    turns = [turn(1.5, 2.45, 'A'), turn(2.45, 3.5, 'B')]
    first = start_run(store, 'job', {})
    complete_run(store, first, turns)
    piece = store.segments('job')[0]['piece_id']
    edit_piece(store, piece, 'Bonjour corrigé', 'Alice')
    second = start_run(store, 'job', {})
    complete_run(store, second, turns)
    assert store.segments('job')[0]['corrected_text'] == 'Bonjour corrigé'
    assert history(store, 'job')[1]['piece_edits'][0]['source_edit_id'] is not None
    select_run(store, 'job', first)
    assert store.segments('job')[0]['corrected_text'] == 'Bonjour corrigé'


def test_missing_or_invalid_words_never_fabricate_a_split(tmp_path):
    store, _ = prepared(tmp_path)
    with store.connect() as db:
        row = dict(db.execute('SELECT * FROM transcript_segments').fetchone())
        assert not save_words(db, row, [dict(start=1.75, end=2.25, word='Changed')])
        assert not save_words(db, row, [dict(start=float('nan'), end=2, word='Original')])
        assert not save_words(db, row, [dict(start=2, end=2, word='Original')])
    result = align_existing(store, 'job', [turn(1.5, 2, 'A'), turn(2, 3.5, 'B')])
    assert result['unresolved'] == 1
    run = start_run(store, 'job', {})
    complete_run(store, run, [turn(1.5, 2, 'A'), turn(2, 3.5, 'B')])
    assert store.segments('job')[0]['speaker_reason'] == 'word_alignment_missing'


def test_group_naming_overview_and_review_filter(tmp_path):
    from majimeeting.editor_ui import TranscriptEditor
    store, _ = timed_transcript(tmp_path)
    run = start_run(store, 'job', {})
    complete_run(store, run, [turn(1.5, 3.5, 'A'), turn(2.5, 3.5, 'B')])
    overview = SpeakerOverview(store, 'job')
    overview.names[0].setText('Alice')
    overview.apply_names()
    overview.close()
    assert store.segments('job')[0]['speaker'] == 'Alice'
    editor = TranscriptEditor(store, 'job')
    editor.only_uncertain.setChecked(True)
    assert len(editor.rows) == 1 and editor.rows[0]['speaker_reason'] == 'overlap'
    editor.close()


def test_pipeline_runs_whisper_then_diarization_and_keeps_completed_text_on_failure(tmp_path, monkeypatch):
    import majimeeting.meeting_pipeline as pipeline
    calls = []
    monkeypatch.setattr(pipeline, 'transcribe_meeting', lambda *a: calls.append('transcribe') or 'job')
    def diarize(*args, **kwargs):
        calls.append('diarize')
        assert args[1] == 'job'
    monkeypatch.setattr(pipeline, 'diarize', diarize)
    options = type('Options', (), {'model_path': 'local'})()
    assert pipeline.process_meeting(None, 'meeting', options, 'py', 'model', 'cuda', 2, None) == 'job'
    assert calls == ['transcribe', 'diarize']
    monkeypatch.setattr(pipeline, 'diarize', lambda *a, **kw: (_ for _ in ()).throw(ValueError('test')))
    with pytest.raises(RuntimeError, match='transcription est sauvegardée'):
        pipeline.process_meeting(None, 'meeting', options, 'py', 'model', 'cuda', 2, None)


def test_export_contains_word_evidence_original_text_and_piece_corrections(tmp_path):
    from majimeeting.__main__ import MainWindow
    store, _ = timed_transcript(tmp_path)
    run = start_run(store, 'job', {})
    complete_run(store, run, [turn(1.5, 2.45, 'A'), turn(2.45, 3.5, 'B')])
    window = MainWindow(store, scan=False)
    target = tmp_path / 'transcript.json'
    window.processing.write_export('job', target)
    data = json.loads(target.read_text())
    assert len(data['segments']) == 2 and len(data['source_segments']) == 1
    assert len(data['word_timestamps']) == 4
    assert len(data['diarization'][0]['pieces']) == 2
    window.close()


def test_existing_transcript_is_aligned_once_without_any_text_decoding(tmp_path, monkeypatch):
    import types

    import faster_whisper
    import faster_whisper.tokenizer
    from test_speakers import runtime

    import majimeeting.word_alignment as alignment
    from majimeeting.diarization import diarize
    store, _ = prepared(tmp_path)
    with store.connect() as db:
        db.execute("UPDATE transcript_segments SET text='Bonjour oui'")
    python, community = runtime(tmp_path)
    whisper = tmp_path / 'whisper'
    whisper.mkdir()
    (whisper / 'config.json').write_text('{}')
    loads = []
    class Model:
        def __init__(self, *args, **kwargs):
            loads.append(kwargs)
            self.model = types.SimpleNamespace(is_multilingual=True)
            self.hf_tokenizer = None

        def transcribe(self, *args, **kwargs):
            pytest.fail('An existing transcript must not be decoded again')
    monkeypatch.setattr(faster_whisper, 'WhisperModel', Model)
    monkeypatch.setattr(faster_whisper.tokenizer, 'Tokenizer', lambda *a, **kw:
                        types.SimpleNamespace(encode=lambda text: [1, 2]))
    def align(model, tokenizer, audio, text):
        assert text == 'Bonjour oui' and len(audio) == 8000  # prepared PCM slice, .5 s
        return [dict(start=0., end=.25, word='Bonjour', probability=.9),
                dict(start=.25, end=.5, word=' oui', probability=.9)]
    monkeypatch.setattr(alignment, 'align_text', align)
    def worker(*args):
        return [turn(0., .5, 'A'), turn(.5, 2., 'B')]
    for _ in range(2):
        diarize(store, 'job', python, community, worker=worker, whisper_model_path=str(whisper))
    assert len(loads) == 1 and loads[0]['local_files_only']
    assert len(store.segments('job')) == 2
    assert ''.join(r['text'] for r in store.segments('job')) == 'Bonjour oui'
    with store.connect() as db:
        assert db.execute('SELECT text FROM transcript_segments').fetchone()[0] == 'Bonjour oui'


def test_single_action_opens_naming_after_processing(tmp_path, monkeypatch, qt_application):
    from PySide6.QtWidgets import QDialog

    import majimeeting.meeting_pipeline as pipeline
    from majimeeting.__main__ import MainWindow
    from majimeeting.diarization_ui import DiarizationDialog
    store, _ = prepared(tmp_path)
    window = MainWindow(store, scan=False)
    window.processing.activate_job('job')
    calls = []
    monkeypatch.setattr(DiarizationDialog, 'exec', lambda _: QDialog.DialogCode.Accepted)
    monkeypatch.setattr(DiarizationDialog, 'values', lambda _: ('python', 'community', 'cuda', 2, {}))
    monkeypatch.setattr(pipeline, 'process_meeting', lambda *a: calls.append('process') or 'job')
    monkeypatch.setattr(window.processing, 'open_speakers', lambda: calls.append('name'))
    window.processing.transcribe(complete=True)
    window.task[1].result(timeout=5)
    window.poll()
    qt_application.processEvents()
    assert calls == ['process', 'name']
    assert window.processing.jobs.currentData() == 'job'
    window.close()
