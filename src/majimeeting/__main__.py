"""Native Windows recording interface."""
import os
import sys
from concurrent.futures import CancelledError, ThreadPoolExecutor
from pathlib import Path

from PySide6.QtCore import QLockFile, Qt, QTimer
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFileDialog,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from majimeeting.capture import RecordingSession, WasapiBackend
from majimeeting.processing_ui import ProcessingPanel
from majimeeting.storage import MeetingStore, export_track


def enumerate_devices():
    backend = WasapiBackend()
    try:
        return backend.devices()
    finally:
        backend.close()


class MainWindow(QMainWindow):
    def __init__(self, store, scan=True):
        super().__init__()
        self.store = store
        self.session = None
        self.task = None
        self.pool = ThreadPoolExecutor(max_workers=1)
        self.setWindowTitle("MAJIMeeting — Enregistrement et transcription")
        self.resize(1000, 700)
        body = QWidget()
        layout = QVBoxLayout(body)
        self.title = QLineEdit()
        self.title.setPlaceholderText("Titre de la réunion")
        layout.addWidget(self.title)
        layout.addWidget(QLabel("Sources WASAPI (plusieurs sélections possibles)"))
        self.devices = QListWidget()
        layout.addWidget(self.devices)
        self.refresh = QPushButton("Actualiser les sources")
        self.refresh.clicked.connect(self.load_devices)
        layout.addWidget(self.refresh)
        self.start_button = QPushButton("Démarrer l'enregistrement")
        self.start_button.clicked.connect(self.start_recording)
        layout.addWidget(self.start_button)
        self.stop_button = QPushButton("Arrêter et sauvegarder")
        self.stop_button.clicked.connect(self.stop_recording)
        self.stop_button.setEnabled(False)
        layout.addWidget(self.stop_button)
        self.status = QLabel("Prêt")
        self.statusBar().addWidget(self.status, 1)
        self.dark = QCheckBox("Thème sombre")
        self.dark.toggled.connect(self.set_theme)
        layout.addWidget(self.dark)
        layout.addWidget(QLabel("Réunions locales — sélectionnez une réunion pour exporter une piste"))
        self.meetings = QListWidget()
        layout.addWidget(self.meetings)
        self.export_button = QPushButton("Exporter une piste en WAV…")
        self.export_button.clicked.connect(self.export)
        layout.addWidget(self.export_button)
        tabs = QTabWidget()
        tabs.addTab(body, 'Enregistrement et réunions')
        self.processing = ProcessingPanel(self)
        tabs.addTab(self.processing, 'Import et transcription')
        self.meetings.currentItemChanged.connect(self.processing.selected)
        self.setCentralWidget(tabs)
        recovered = self.store.recover()
        self.reload_meetings()
        if recovered:
            self.status.setText(f"{recovered} réunion(s) interrompue(s) récupérée(s).")
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.poll)
        self.timer.start(150)
        if scan:
            self.load_devices()

    def set_theme(self, dark):
        self.setStyleSheet(
            "QWidget { background: #202530; color: #edf1f7; } "
            "QLineEdit, QListWidget { background: #141922; } "
            "QPushButton { padding: 8px; background: #35445b; } "
            "QPushButton:disabled { color: #9298a1; }" if dark else ""
        )

    def busy(self, active):
        self.processing.set_busy(active)
        for widget in (self.title, self.devices, self.refresh, self.start_button,
                       self.export_button):
            widget.setEnabled(not active)

    def load_devices(self):
        self.busy(True)
        self.status.setText("Recherche des sources…")
        self.task = ("devices", self.pool.submit(enumerate_devices))

    def reload_meetings(self):
        self.meetings.clear()
        for row in self.store.list():
            item = QListWidgetItem(f"{row['created'][:19]} — {row['title']} [{row['status']}]")
            item.setData(Qt.ItemDataRole.UserRole, row['id'])
            item.setToolTip(row['error'])
            self.meetings.addItem(item)

    def start_recording(self):
        selected = [self.devices.item(i).data(Qt.ItemDataRole.UserRole)
                    for i in range(self.devices.count())
                    if self.devices.item(i).checkState() == Qt.CheckState.Checked]
        try:
            if not self.title.text().strip():
                raise ValueError("Saisissez le titre de la réunion.")
            self.session = RecordingSession(self.store, self.title.text(), selected)
            self.session.start()
            self.busy(True)
            self.stop_button.setEnabled(True)
            self.status.setText("Enregistrement en cours — pistes sauvegardées chaque seconde")
        except Exception as exc:
            QMessageBox.warning(self, "Enregistrement", str(exc))

    def stop_recording(self):
        if self.session:
            self.session.stop()
            self.stop_button.setEnabled(False)
            self.status.setText("Finalisation des pistes…")

    def poll(self):
        self.processing.poll_progress()
        if self.task and self.task[1].done():
            kind, future = self.task
            self.task = None
            self.busy(False)
            try:
                result = future.result()
                if kind == "devices":
                    self.devices.clear()
                    for device in result:
                        prefix = "Audio système" if device.loopback else "Microphone / entrée"
                        item = QListWidgetItem(f"{prefix} — {device.name}")
                        item.setData(Qt.ItemDataRole.UserRole, device)
                        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                        item.setCheckState(Qt.CheckState.Unchecked)
                        self.devices.addItem(item)
                    self.status.setText("Sélectionnez vos sources audio.")
                elif kind == 'import':
                    self.reload_meetings()
                    for i in range(self.meetings.count()):
                        if self.meetings.item(i).data(Qt.ItemDataRole.UserRole) == result:
                            self.meetings.setCurrentRow(i)
                            break
                    self.status.setText('Import terminé. Réunion sélectionnée pour transcription.')
                elif kind == 'transcribe':
                    self.status.setText('Transcription terminée.')
                elif kind == 'download':
                    self.status.setText('Modèle installé. La transcription fonctionne hors ligne.')
                else:
                    self.status.setText("Piste exportée.")
            except CancelledError:
                self.status.setText('Traitement annulé ; résultats partiels conservés.')
                if kind == 'import':
                    self.reload_meetings()
            except Exception as exc:
                self.status.setText(str(exc))
                if kind == 'import':
                    self.reload_meetings()
                QMessageBox.warning(self, "MAJIMeeting", str(exc))
            if kind != 'devices':
                self.processing.finish_progress(future.exception() is None)
            self.processing.reload()
        if self.session and self.session.done.is_set():
            error = self.session.error
            self.session.thread.join()
            self.session = None
            self.busy(False)
            self.stop_button.setEnabled(False)
            self.reload_meetings()
            self.status.setText("Enregistrement terminé." if not error else f"Erreur : {error}")
            if error:
                QMessageBox.warning(self, "Capture interrompue", error)

    def export(self):
        item = self.meetings.currentItem()
        if not item:
            return
        folder = self.store.root / item.data(Qt.ItemDataRole.UserRole)
        tracks = sorted(p for p in folder.glob("track-*") if (p / "track.json").is_file())
        if not tracks:
            QMessageBox.information(self, "Export", "Aucune piste audio disponible.")
            return
        name, ok = QInputDialog.getItem(self, "Export WAV", "Piste séparée :",
                                       [p.name for p in tracks], 0, False)
        if not ok:
            return
        destination, _ = QFileDialog.getSaveFileName(self, "Exporter la piste", name + ".wav",
                                                    "Audio WAV (*.wav)")
        if destination:
            self.busy(True)
            self.status.setText("Export en cours…")
            self.task = ("export", self.pool.submit(export_track, folder / name, destination))

    def closeEvent(self, event):
        if self.session or self.task:
            QMessageBox.information(self, "Traitement en cours",
                                    "Arrêtez l'enregistrement et attendez la fin du traitement.")
            event.ignore()
            return
        self.pool.shutdown(wait=False)
        event.accept()


def main() -> int:
    if '--download-smoke' in sys.argv:
        from majimeeting.model_download import download_model
        download_model(sys.argv[sys.argv.index('--download-smoke') + 1], model_name='tiny')
        return 0
    if '--inference-smoke' in sys.argv:
        from majimeeting.selftest import inference_smoke
        return inference_smoke(sys.argv[sys.argv.index('--inference-smoke') + 1])
    app = QApplication(sys.argv)
    app.setApplicationName("MAJIMeeting")
    root = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "MAJIMeeting" / "data"
    root.mkdir(parents=True, exist_ok=True)
    lock = QLockFile(str(root / "application.lock"))
    if not lock.tryLock(0):
        QMessageBox.warning(None, "MAJIMeeting", "Une autre instance utilise déjà ces données.")
        return 1
    smoke = "--smoke-test" in sys.argv
    window = MainWindow(MeetingStore(root), scan=not smoke)
    window.show()
    if smoke:
        QTimer.singleShot(300, window.close)
        QTimer.singleShot(500, app.quit)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
