import json
import struct
import wave

import pytest
from PySide6.QtWidgets import QApplication

from majimeeting.editor_ui import TranscriptEditor
from majimeeting.playback import make_excerpt
from majimeeting.storage import FragmentWriter, MeetingStore
from majimeeting.transcription import TranscriptionOptions


def prepared(tmp_path):
    store = MeetingStore(tmp_path / 'data')
    meeting = store.create('Corrections')
    writer = FragmentWriter(store.root / meeting / 'track-00', 100, 1, {})
    writer.write(struct.pack('<h', 1200) * 200, 1.5)
    writer.close()
    store.finish(meeting, 'completed')
    store.start_transcription('job', meeting, TranscriptionOptions('unused'))
    store.add_segment('job', 'track-00', 1.75, 2.25, 'Original')
    store.finish_transcription('job', 'completed')
    return store, meeting


def test_corrections_persist_without_changing_original_times_or_previous_jobs(tmp_path):
    store, meeting = prepared(tmp_path)
    row = store.segments('job')[0]
    store.edit_segment(row['id'], 'Texte corrigé', 'Alice')
    store.edit_segment(row['id'], 'Version relue', 'Bob')
    store.start_transcription('new-job', meeting, TranscriptionOptions('unused'))
    store.add_segment('new-job', 'track-00', 1.75, 2.25, 'Autre tentative')
    store.finish_transcription('new-job', 'completed')
    reopened = MeetingStore(store.root)
    corrected = reopened.segments('job')[0]
    assert corrected['text'] == corrected['original_text'] == 'Original'
    assert corrected['corrected_text'] == 'Version relue'
    assert corrected['speaker'] == 'Bob'
    assert (corrected['start'], corrected['end']) == (1.75, 2.25)
    assert len(reopened.segment_history(row['id'])) == 2
    assert reopened.segments('new-job')[0]['speaker'] == ''
    assert reopened.segments('new-job')[0]['corrected_text'] == 'Autre tentative'
    with pytest.raises(ValueError):
        store.edit_segment(row['id'], ' ', 'Alice')
    with pytest.raises(ValueError):
        store.edit_segment(-1, 'Correction', 'Alice')
    store.start_transcription('running', meeting, TranscriptionOptions('unused'))
    store.add_segment('running', 'track-00', 0, 1, 'En cours')
    with pytest.raises(ValueError, match='fin du traitement'):
        store.edit_segment(store.segments('running')[0]['id'], 'Ne pas modifier', 'Alice')


def test_excerpt_preserves_offsets_gaps_and_exact_samples(tmp_path):
    store, meeting = prepared(tmp_path)
    track = store.root / meeting / 'track-00'
    # Gap from 2.5 to 3.5 seconds: remove second fragment; preserve third at 3.5.
    (track / '00000001.wav').unlink()
    timing = {'start_seconds': 3.5, 'frames': 100}
    (track / '00000002.json').write_text(json.dumps(timing))
    with wave.open(str(track / '00000002.wav'), 'wb') as out:
        out.setparams((1, 2, 100, 0, 'NONE', 'not compressed'))
        out.writeframes(struct.pack('<h', -600) * 100)
    target = tmp_path / 'passage.wav'
    assert make_excerpt(track, 2, 4, target) == 2
    with wave.open(str(target), 'rb') as audio:
        values = struct.unpack('<200h', audio.readframes(200))
    assert values == (1200,) * 50 + (0,) * 100 + (-600,) * 50
    assert make_excerpt(track, 1.75, 1000, target) == 60
    with wave.open(str(target), 'rb') as audio:
        assert audio.getnframes() == 6000
    with pytest.raises(ValueError, match='Aucun fragment'):
        make_excerpt(track, 70, 71, target)
    with pytest.raises(ValueError):
        make_excerpt(track, float('nan'), 2, target)
    with pytest.raises(ValueError):
        make_excerpt(track, 3, 2, target)


def test_excerpt_rejects_corrupt_fragment(tmp_path):
    store, meeting = prepared(tmp_path)
    track = store.root / meeting / 'track-00'
    timing = track / '00000000.json'
    data = json.loads(timing.read_text())
    data['frames'] = 101
    timing.write_text(json.dumps(data))
    with pytest.raises(ValueError, match='incomplet'):
        make_excerpt(track, 1.5, 2, tmp_path / 'broken.wav')


def test_editor_save_restore_export_and_background_excerpt(tmp_path):
    from majimeeting.__main__ import MainWindow
    app = QApplication.instance() or QApplication([])
    store, _ = prepared(tmp_path)
    store.add_segment('job', 'track-00', 2.3, 2.4, 'Deuxième passage')
    window = MainWindow(store, scan=False)
    window.meetings.setCurrentRow(0)
    editor = TranscriptEditor(store, 'job', window)
    editor.text.setPlainText('Décision corrigée')
    editor.speaker.setText('François')
    editor.save.click()
    assert editor.table.item(0, 2).text() == 'François'
    assert 'Original' in editor.history.toPlainText()
    window.processing.show_transcript()
    assert 'Décision corrigée' in window.processing.text.toPlainText()
    window.processing.write_export('job', tmp_path / 'corrected.json')
    row = json.loads((tmp_path / 'corrected.json').read_text(encoding='utf-8'))['segments'][0]
    assert row['text'] == 'Décision corrigée'
    assert row['original_text'] == 'Original'
    assert row['speaker'] == 'François'
    window.processing.write_export('job', tmp_path / 'corrected.txt')
    assert 'François (track-00) : Décision corrigée' in (tmp_path / 'corrected.txt').read_text(encoding='utf-8')
    editor.play()
    assert not editor.listen.isEnabled()
    editor.table.setCurrentCell(1, 0)  # Selecting elsewhere cancels delayed playback.
    assert editor.future.result(timeout=5) == .5
    editor.poll()
    assert editor.status.text() == 'Lecture arrêtée.'
    editor.table.setCurrentCell(0, 0)
    editor.restore.click()
    assert store.segments('job')[0]['corrected_text'] == 'Original'
    assert store.segments('job')[0]['speaker'] == ''
    assert len(store.segment_history(store.segments('job')[0]['id'])) == 2
    editor.accept()
    window.close()
    app.processEvents()
