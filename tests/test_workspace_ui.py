"""Navigation and worker safety across the task-oriented workspace."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from majimeeting.__main__ import MainWindow
from majimeeting.storage import MeetingStore
from majimeeting.transcription import TranscriptionOptions


def populated(tmp_path):
    store = MeetingStore(tmp_path)
    meeting = store.create('Projet acoustique')
    store.finish(meeting, 'completed')
    store.start_transcription('saved', meeting, TranscriptionOptions('local'))
    store.add_segment('saved', 'track-01', 1, 3, 'Une transcription déjà conservée.')
    store.finish_transcription('saved', 'completed')
    store.finish(store.create('Autre réunion'), 'completed')
    return MainWindow(store, scan=False), meeting


def test_saved_transcript_opens_reading_area_and_reveals_filtered_meeting(tmp_path):
    window, meeting = populated(tmp_path)
    window.meeting_search.setText('aucun résultat')
    window.centralWidget().setCurrentIndex(2)
    window.processing.result_tabs.setCurrentIndex(2)
    assert window.processing.activate_job('saved')
    assert window.centralWidget().currentIndex() == 1
    assert window.processing.result_tabs.currentIndex() == 0
    assert window.processing.current_meeting == meeting
    assert not window.meetings.currentItem().isHidden()
    assert 'déjà conservée' in window.processing.text.toPlainText()
    assert window.task is None
    window.close()


def test_library_search_and_refresh_preserve_selected_meeting(tmp_path):
    window, meeting = populated(tmp_path)
    window.processing.activate_job('saved')
    window.meeting_search.setText('ACOUSTIQUE')
    window.reload_meetings()
    assert window.meetings.currentItem().data(Qt.ItemDataRole.UserRole) == meeting
    visible = [window.meetings.item(i) for i in range(window.meetings.count())
               if not window.meetings.item(i).isHidden()]
    assert len(visible) == 1
    assert visible[0] is window.meetings.currentItem()
    window.close()


def test_menu_commands_cannot_bypass_worker_lock(tmp_path, monkeypatch):
    window, _ = populated(tmp_path)
    recording = window.menuBar().actions()[1].menu()
    start = next(action for action in recording.actions() if action.text() == 'Démarrer')
    clicks = []
    monkeypatch.setattr(window.start_button, 'click', lambda: clicks.append('start'))
    window.busy(True)
    assert not start.isEnabled()
    start.trigger()
    assert not clicks
    window.busy(False)
    assert start.isEnabled()
    start.trigger()
    assert clicks == ['start']
    assert window.centralWidget().currentIndex() == 0
    window.close()


def test_settings_and_global_progress_are_accessible_on_every_page(tmp_path):
    window, _ = populated(tmp_path)
    window.show()
    app = QApplication.instance()
    panel = window.processing
    tabs = window.centralWidget()
    assert [tabs.tabText(i) for i in range(tabs.count())] == [
        'Enregistrer', 'Transcription et intervenants', 'Paramètres']
    tabs.setCurrentIndex(1)
    app.processEvents()
    assert panel.text.isVisible()
    assert not panel.model.isVisible()
    assert not panel.device.isVisible()
    tabs.setCurrentIndex(2)
    app.processEvents()
    assert panel.model.isVisible()
    assert not panel.text.isVisible()
    panel.messages.put(('Téléchargement modèle : 42 %', 42))
    panel.poll_progress()
    assert panel.progress_bar.isVisible()
    assert panel.progress_bar.value() == 42
    assert panel.download_status.isVisible()
    assert window.meetings.isVisible()
    window.busy(True)
    assert not panel.prepare_speakers.isEnabled()
    window.busy(False)
    assert panel.prepare_speakers.isEnabled()
    window.close()
