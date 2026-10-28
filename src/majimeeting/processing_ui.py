"""Deferred audio processing controls, sharing the application's serial worker."""
import json
import queue
import threading
from pathlib import Path

from PySide6.QtCore import QSettings, Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
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
        layout.addWidget(QLabel('CUDA : cuBLAS CUDA 12 + cuDNN 9 requis ; CPU sans GPU disponible.'))
        self.cuda_path = QLineEdit(str(self.settings.value('cuda_path', '')))
        self.cuda_path.setPlaceholderText('Dossier des DLL NVIDIA (facultatif, si déjà installées)')
        layout.addWidget(self.cuda_path)
        self.cuda_browse = QPushButton('Choisir le dossier CUDA / cuDNN…')
        self.cuda_browse.clicked.connect(self.choose_cuda_path)
        layout.addWidget(self.cuda_browse)
        self.cpu_fallback = QCheckBox('Si CUDA est indisponible, reprendre sur CPU/int8')
        self.cpu_fallback.setChecked(self.settings.value('cpu_fallback', True, type=bool))
        layout.addWidget(self.cpu_fallback)
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
        self.execution = QLabel('')
        self.execution.setWordWrap(True)
        layout.addWidget(self.execution)
        self.warnings_button = QPushButton('Voir les avertissements d’horodatage…')
        self.warnings_button.clicked.connect(self.show_warnings)
        self.warnings_button.setEnabled(False)
        layout.addWidget(self.warnings_button)
        self.text = QPlainTextEdit()
        self.text.setReadOnly(True)
        layout.addWidget(self.text)
        self.export_button = QPushButton('Exporter la transcription (TXT ou JSON)…')
        self.export_button.clicked.connect(self.export)
        layout.addWidget(self.export_button)
        self.edit_button = QPushButton('Corriger les textes, nommer les intervenants et réécouter…')
        self.edit_button.clicked.connect(self.open_editor)
        layout.addWidget(self.edit_button)

    def device_changed(self, device):
        self.compute.clear()
        self.compute.addItems(['int8', 'float32'] if device == 'cpu' else
                              ['int8_float16', 'float16'])

    def set_busy(self, active):
        for widget in (self.import_button, self.model, self.browse, self.download, self.device,
                       self.compute, self.cuda_path, self.cuda_browse, self.cpu_fallback,
                       self.transcribe_button, self.export_button, self.edit_button):
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

    def choose_cuda_path(self):
        path = QFileDialog.getExistingDirectory(self, 'Dossier des bibliothèques NVIDIA',
                                                self.cuda_path.text())
        if path:
            self.cuda_path.setText(path)
            self.settings.setValue('cuda_path', path)

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
                                       self.compute.currentText(),
                                       allow_cpu_fallback=self.cpu_fallback.isChecked(),
                                       cuda_library_path=self.cuda_path.text().strip())
        self.settings.setValue('model', options.model_path)
        self.settings.setValue('device', options.device)
        self.settings.setValue('cuda_path', options.cuda_library_path)
        self.settings.setValue('cpu_fallback', options.allow_cpu_fallback)
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
                self.jobs.setItemData(self.jobs.count() - 1, row['options'],
                                      Qt.ItemDataRole.UserRole + 1)
        self.jobs.blockSignals(False)
        self.show_transcript()

    def show_transcript(self):
        job = self.jobs.currentData()
        options_json = self.jobs.currentData(Qt.ItemDataRole.UserRole + 1)
        execution = json.loads(options_json).get('execution', {}) if options_json else {}
        actual = f"{execution.get('device', '?')}/{execution.get('compute_type', '?')}"
        reason = execution.get('fallback_reason')
        self.execution.setText((f'Calcul réellement utilisé : {actual}. ' +
                                (f'Repli CPU car CUDA indisponible : {reason}' if reason else ''))
                               if execution else '')
        counts = self.window.store.warning_counts(job) if job else {}
        warning_count = sum(counts.values())
        self.warnings_button.setEnabled(warning_count > 0)
        if warning_count:
            self.execution.setText(self.execution.text() +
                                   f" Horodatages : {counts.get('clipped', 0)} intervalle(s) ajusté(s), "
                                   f"{warning_count - counts.get('clipped', 0)} segment(s) écarté(s). "
                                   'Voir les avertissements pour vérifier ces passages.')
        self.text.setPlainText('\n'.join(
            f"[{timestamp(row['start'])} → {timestamp(row['end'])}] "
            f"{row['speaker'] or 'Inconnu'} ({row['track']}) : {row['corrected_text']}"
            for row in self.window.store.segments(job)) if job else '')

    def open_editor(self):
        job = self.jobs.currentData()
        if not job:
            return
        from majimeeting.editor_ui import TranscriptEditor
        dialog = TranscriptEditor(self.window.store, job, self)
        dialog.exec()
        self.show_transcript()

    def show_warnings(self):
        job = self.jobs.currentData()
        if not job:
            return
        rows = self.window.store.transcription_warnings(job, limit=500)
        labels = {'clipped': 'Intervalle borné à la durée audio',
                  'outside_audio': 'Segment hors audio ou sans durée : écarté',
                  'invalid_timestamp': 'Horodatage non exploitable : segment écarté'}
        dialog = QDialog(self)
        dialog.setWindowTitle('Avertissements d’horodatage — contrôle de la transcription')
        dialog.resize(850, 500)
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel('Les 500 premiers avertissements sont affichés. '
                                'L’export JSON conserve l’audit complet.'))
        details = QPlainTextEdit()
        details.setReadOnly(True)
        details.setPlainText('\n\n'.join(
            f"{row['track']} — lot à {timestamp(row['batch_offset'])} — "
            f"{labels.get(row['kind'], row['kind'])}\n"
            f"Temps bruts relatifs au lot : {row['raw_start']} → {row['raw_end']} s\n"
            f"Texte brut à vérifier : {row['text']}" for row in rows))
        layout.addWidget(details)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        dialog.exec()

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
        for row in rows:
            row['text'] = row.pop('corrected_text')
        if Path(path).suffix.lower() == '.json':
            text = json.dumps({'job_id': job, 'segments': rows,
                               'timestamp_warnings': [dict(row) for row in
                                    self.window.store.transcription_warnings(job)]},
                              ensure_ascii=False, indent=2)
        else:
            text = '\n'.join(f"[{timestamp(r['start'])} → {timestamp(r['end'])}] "
                             f"{r['speaker'] or 'Inconnu'} ({r['track']}) : {r['text']}" for r in rows)
        if Path(path).suffix.lower() != '.json':
            count = sum(self.window.store.warning_counts(job).values())
            if count:
                text += (f'\n\nHorodatages : {count} avertissement(s). '
                         'Consultez l’historique ou l’export JSON pour les détails.')
        target = Path(path)
        temp = target.with_suffix(target.suffix + '.part')
        try:
            temp.write_text(text, encoding='utf-8')
            temp.replace(target)
        finally:
            temp.unlink(missing_ok=True)
