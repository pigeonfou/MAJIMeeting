"""Keep Qt alive and dispose native windows between independent GUI tests."""
import pytest
from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtWidgets import QApplication


@pytest.fixture(scope='session', autouse=True)
def qt_application():
    app = QApplication.instance() or QApplication([])
    yield app
    app.processEvents()


@pytest.fixture(autouse=True)
def dispose_windows(qt_application):
    yield
    for widget in qt_application.topLevelWidgets():
        widget.close()
        widget.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    qt_application.processEvents()
