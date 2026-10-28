"""Deferred audio processing controls, sharing the application's serial worker."""
import json
import queue
import threading
from pathlib import Path

from PySide6.QtCore import QSettings, Qt
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from majimeeting.transcription import (
    TranscriptionOptions,
    download_model,
    import_audio,
    transcribe_meeting,
)


def timestamp(seconds):
    milliseconds = round(seconds * 1000)
    hours, rest = divmod(milliseconds, 3600000)
    minutes, rest = divmod(rest, 60000)
    seconds, milliseconds = divmod(rest, 1000)
    return f'{hours:02}:{minutes:02}:{seconds:02}.{milliseconds:03}'


class ProcessingPanel(QWidget):
    def __init__(self, window):
        super().__init__()
        self.window = window
        self.cancel = threading.Event()
        self.messages = queue.Queue(maxsize=1)
        self.settings = QSettings('MAJIMeeting', 'MAJIMeeting')
        self.current_meeting = None
        layout = QVBoxLayout(self)
        self.selection = QLabel('Sélectionnez une réunion dans l’onglet Enregistrement.')
        layout.addWidget(self.selection)
        self.import_button = QPushButton('Importer un fichier WAV, MP3, FLAC ou M4A…')
        self.import_button.clicked.connect(self.import_file)
        layout.addWidget(self.import_button)
        layout.addWidget(QLabel('Modèle faster-whisper local (large-v3 recommandé)'))
        self.model = QLineEdit(str(self.settings.value('model', str(
            window.store.root.parent / 'models' / 'large-v3'))))
        layout.addWidget(self.model)
        self.browse = QPushButton('Choisir le dossier du modèle…')
        self.browse.clicked.connect(self.choose_model)
        layout.addWidget(self.browse)
        self.download = QPushButton('Télécharger large-v3 (~3 Go, connexion requise)')
        self.download.clicked.connect(self.fetch_model)
        layout.addWidget(self.download)
        self.download_status = QLabel('Modèle local : aucun téléchargement en cours.')
        self.download_status.setWordWrap(True)
        layout.addWidget(self.download_status)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)
        self.device = QComboBox()
        self.device.addItems(['cpu', 'cuda'])
        self.compute = QComboBox()
        self.device.currentTextChanged.connect(self.device_changed)
        self.device_changed(self.device.currentText())
        self.device.setCurrentText(str(self.settings.value('device', 'cpu')))
        layout.addWidget(QLabel('Calcul : CPU ou CUDA ; quantification'))
        layout.addWidget(self.device)
        layout.addWidget(self.compute)
        layout.addWidget(QLabel('CUDA : bibliothèques NVIDIA requises ; CPU disponible sans GPU.'))
        self.transcribe_button = QPushButton('Transcrire la réunion sélectionnée en français')
        self.transcribe_button.clicked.connect(self.transcribe)
        layout.addWidget(self.transcribe_button)
        self.cancel_button = QPushButton('Annuler le traitement (après le segment en cours)')
        self.cancel_button.clicked.connect(self.cancel.set)
        self.cancel_button.setEnabled(False)
        layout.addWidget(self.cancel_button)
        layout.addWidget(QLabel('Historique des transcriptions — les pistes ne sont pas des personnes'))
        self.jobs = QComboBox()
        self.jobs.currentIndexChanged.connect(self.show_transcript)
        layout.addWidget(self.jobs)
        self.text = QPlainTextEdit()
        self.text.setReadOnly(True)
        layout.addWidget(self.text)
        self.export_button = QPushButton('Exporter la transcription (TXT ou JSON)…')
        self.export_button.clicked.connect(self.export)
        layout.addWidget(self.export_button)

    def device_changed(self, device):
        self.compute.clear()
        self.compute.addItems(['int8', 'float32'] if device == 'cpu' else
                              ['int8_float16', 'float16'])

    def set_busy(self, active):
        for widget in (self.import_button, self.model, self.browse, self.download, self.device,
                       self.compute, self.transcribe_button, self.export_button):
            widget.setEnabled(not active)
        if not active:
            self.cancel_button.setEnabled(False)

    def progress(self, message, percent=None):
        try:
            self.messages.get_nowait()
        except queue.Empty:
            pass
        try:
            self.messages.put_nowait((message, percent))
        except queue.Full:
            pass

    def poll_progress(self):
        try:
            message, percent = self.messages.get_nowait()
            self.window.status.setText(message)
            self.download_status.setText(message)
            self.progress_bar.setRange(0, 0 if percent is None else 100)
            if percent is not None:
                self.progress_bar.setValue(percent)
        except queue.Empty:
            pass

    def finish_progress(self, success):
        while not self.messages.empty():
            self.messages.get_nowait()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(100 if success else 0)
        self.download_status.setText(self.window.status.text())

    def submit(self, kind, function, *args, cancellable=False):
        self.cancel.clear()
        self.window.busy(True)
        self.window.status.setText('Traitement en cours…')
        self.download_status.setText('Connexion au serveur de modèles…' if kind == 'download'
                                     else 'Traitement en cours…')
        self.progress_bar.setRange(0, 0)
        self.cancel_button.setText('Annuler le téléchargement' if kind == 'download'
                                   else 'Annuler le traitement (après le segment en cours)')
        self.cancel_button.setEnabled(cancellable)
        self.window.task = (kind, self.window.pool.submit(function, *args))

    def choose_model(self):
        path = QFileDialog.getExistingDirectory(self, 'Modèle faster-whisper local', self.model.text())
        if path:
            self.model.setText(path)
            self.settings.setValue('model', path)

    def fetch_model(self):
        destination = self.model.text().strip()
        if not destination:
            return
        self.settings.setValue('model', destination)
        self.submit('download', download_model, destination, self.cancel, self.progress,
                    cancellable=True)

    def import_file(self):
        path, _ = QFileDialog.getOpenFileName(self, 'Importer de l’audio', '',
                                             'Audio (*.wav *.mp3 *.flac *.m4a)')
        if path:
            self.submit('import', import_audio, self.window.store, path, self.cancel,
                        self.progress, cancellable=True)

    def transcribe(self):
        if not self.current_meeting:
            self.window.status.setText('Sélectionnez d’abord une réunion.')
            return
        options = TranscriptionOptions(self.model.text().strip(), self.device.currentText(),
                                       self.compute.currentText())
        self.settings.setValue('model', options.model_path)
        self.settings.setValue('device', options.device)
        self.submit('transcribe', transcribe_meeting, self.window.store, self.current_meeting,
                    options, self.cancel, self.progress, cancellable=True)

    def selected(self):
        item = self.window.meetings.currentItem()
        self.current_meeting = item.data(Qt.ItemDataRole.UserRole) if item else None
        self.selection.setText(item.text() if item else 'Sélectionnez une réunion.')
        self.reload()

    def reload(self):
        self.jobs.blockSignals(True)
        self.jobs.clear()
        if self.current_meeting:
            for row in self.window.store.transcription_jobs(self.current_meeting):
                self.jobs.addItem(f"{row['created'][:19]} [{row['status']}] {row['error']}", row['id'])
        self.jobs.blockSignals(False)
        self.show_transcript()

    def show_transcript(self):
        job = self.jobs.currentData()
        self.text.setPlainText('\n'.join(
            f"[{timestamp(row['start'])} → {timestamp(row['end'])}] {row['track']} : {row['text']}"
            for row in self.window.store.segments(job)) if job else '')

    def export(self):
        job = self.jobs.currentData()
        if not job:
            return
        path, _ = QFileDialog.getSaveFileName(self, 'Exporter la transcription', 'transcription.txt',
                                             'Texte (*.txt);;JSON (*.json)')
        if path:
            self.submit('transcript-export', self.write_export, job, path)

    def write_export(self, job, path):
        rows = [dict(row) for row in self.window.store.segments(job)]
        if Path(path).suffix.lower() == '.json':
            text = json.dumps({'job_id': job, 'segments': rows}, ensure_ascii=False, indent=2)
        else:
            text = '\n'.join(f"[{timestamp(r['start'])} → {timestamp(r['end'])}] "
                             f"{r['track']} : {r['text']}" for r in rows)
        target = Path(path)
        temp = target.with_suffix(target.suffix + '.part')
        try:
            temp.write_text(text, encoding='utf-8')
            temp.replace(target)
        finally:
            temp.unlink(missing_ok=True)
