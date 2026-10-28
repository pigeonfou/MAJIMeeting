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


def test_model_download_button_reports_progress_and_can_cancel(tmp_path, monkeypatch):
    import threading
    from concurrent.futures import CancelledError

    import pytest

    import majimeeting.processing_ui as processing_ui
    app = QApplication.instance() or QApplication([])
    started = threading.Event()

    def fake_download(destination, cancel, progress):
        progress('model.bin : 42 / 100 Mo', 42)
        started.set()
        assert cancel.wait(3)
        raise CancelledError('Cancelled by test')

    monkeypatch.setattr(processing_ui, 'download_model', fake_download)
    window = MainWindow(MeetingStore(tmp_path / 'data'), scan=False)
    panel = window.processing
    panel.model.setText(str(tmp_path / 'model'))
    panel.download.click()
    assert started.wait(3)
    app.processEvents()
    panel.poll_progress()
    assert panel.progress_bar.value() == 42
    assert '42 / 100' in panel.download_status.text()
    assert panel.cancel_button.isEnabled()
    assert not window.start_button.isEnabled()
    future = window.task[1]
    panel.cancel_button.click()
    with pytest.raises(CancelledError):
        future.result(timeout=3)
    window.poll()
    assert 'annulé' in window.status.text()
    assert panel.download_status.text() == window.status.text()
    assert panel.download.isEnabled()
    window.close()
    app.processEvents()


def test_history_shows_cpu_fallback_reason(tmp_path):
    from majimeeting.transcription import TranscriptionOptions
    app = QApplication.instance() or QApplication([])
    store = MeetingStore(tmp_path / 'data')
    meeting = store.create('Repli CPU')
    store.finish(meeting, 'completed')
    store.start_transcription('fallback', meeting, TranscriptionOptions('local'))
    store.set_execution('fallback', 'cpu', 'int8', 'cublas64_12.dll absente')
    store.finish_transcription('fallback', 'completed')
    window = MainWindow(store, scan=False)
    window.meetings.setCurrentRow(0)
    assert 'cpu/int8' in window.processing.execution.text()
    assert 'cublas64_12.dll' in window.processing.execution.text()
    window.close()
    app.processEvents()
