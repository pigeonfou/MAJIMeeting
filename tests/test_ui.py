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
