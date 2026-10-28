from PySide6.QtWidgets import QApplication

from majimeeting.__main__ import MainWindow
from majimeeting.storage import MeetingStore


def test_ui_recovers_catalogue_and_switches_theme(tmp_path):
    app = QApplication.instance() or QApplication([])
    store = MeetingStore(tmp_path)
    store.create('Interruption simulée')
    window = MainWindow(store, scan=False)
    assert window.meetings.count() == 1
    assert 'interrupted' in window.meetings.item(0).text()
    assert not window.stop_button.isEnabled()
    window.dark.setChecked(True)
    assert '#202530' in window.styleSheet()
    window.dark.setChecked(False)
    assert not window.styleSheet()
    window.close()
    app.processEvents()


def test_transcription_panel_selection_history_and_export(tmp_path):
    import json

    from majimeeting.transcription import TranscriptionOptions
    app = QApplication.instance() or QApplication([])
    store = MeetingStore(tmp_path / 'data')
    meeting = store.create('Réunion transcrite')
    store.finish(meeting, 'completed')
    store.start_transcription('job', meeting, TranscriptionOptions('local-model'))
    store.add_segment('job', 'track-01', 61.25, 63.5, 'Décision technique.')
    store.finish_transcription('job', 'completed')
    window = MainWindow(store, scan=False)
    window.meetings.setCurrentRow(0)
    panel = window.processing
    assert panel.current_meeting == meeting
    assert '00:01:01.250' in panel.text.toPlainText()
    assert 'track-01' in panel.text.toPlainText()
    panel.write_export('job', tmp_path / 'transcript.json')
    assert json.loads((tmp_path / 'transcript.json').read_text(encoding='utf-8'))['segments'][0]['text'] == 'Décision technique.'
    window.busy(True)
    assert not window.start_button.isEnabled()
    assert not panel.transcribe_button.isEnabled()
    window.busy(False)
    window.close()
    app.processEvents()
