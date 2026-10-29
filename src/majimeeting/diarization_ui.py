"""Configuration for the optional, isolated Community-1 runtime."""
import json
import os
import queue
import threading
from concurrent.futures import CancelledError, ThreadPoolExecutor
from pathlib import Path

from PySide6.QtCore import QSettings, QTimer
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from majimeeting.diarization_controls import DiarizationControls
from majimeeting.diarization_setup import download_community, install_dependencies


class DiarizationDialog(QDialog):
    def __init__(self, parent=None, initial=None, tracks=(), transcribe_first=False):
        super().__init__(parent)
        self.setWindowTitle('Distinguer les interlocuteurs — Community-1 local')
        self.resize(820, 800)
        self.transcribe_first = transcribe_first
        self.future = None
        self.operation = ''
        self.close_pending = False
        self.cancel = threading.Event()
        self.messages = queue.Queue(maxsize=200)
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix='majimeeting-setup')
        self.settings = QSettings('MAJIMeeting', 'MAJIMeeting')
        root = Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'MAJIMeeting'
        initial = initial or {}
        root_layout = QVBoxLayout(self)
        tabs = QTabWidget()
        root_layout.addWidget(tabs)
        try:
            remembered = json.loads(str(self.settings.value('diarization_tuning', '{}')))
        except (ValueError, TypeError):
            remembered = {}
        self.controls = DiarizationControls(
            initial.get('speakers', self.settings.value('diarization_speakers', 0, type=int)),
            initial.get('tuning', remembered), tracks)
        if transcribe_first:
            self.setWindowTitle('Transcrire puis proposer les intervenants')
            self.controls.layout().itemAt(0).widget().setText(
                'Lance la transcription mot à mot, puis le découpage par voix. '
                'Vous pourrez ensuite nommer les groupes avec de courts extraits. '
                'Les superpositions et attributions incertaines restent signalées.')
        analysis = QWidget()
        analysis_layout = QVBoxLayout(analysis)
        self.device = QComboBox()
        self.device.addItems(['cpu', 'cuda'])
        self.device.setCurrentText(str(initial.get('device', self.settings.value('diarization_device', 'cuda'))))
        analysis_layout.addWidget(QLabel('Calcul de diarisation :'))
        analysis_layout.addWidget(self.device)
        analysis_layout.addWidget(self.controls)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(analysis)
        tabs.addTab(scroll, 'Réglages de l’analyse')
        preparation = QWidget()
        layout = QVBoxLayout(preparation)
        preparation_scroll = QScrollArea()
        preparation_scroll.setWidgetResizable(True)
        preparation_scroll.setWidget(preparation)
        tabs.addTab(preparation_scroll, 'Modèle et dépendances')
        self.speakers = self.controls.speakers
        label = QLabel('Analyse après transcription, sans serveur. Les groupes ne constituent '
                       'pas une identification des personnes. Chaque piste a ses propres groupes. '
                       'Les passages ambigus restent à vérifier.\n\n'
                       'Préparation initiale avec connexion : installez les dépendances puis '
                       'téléchargez le modèle. Python 3.11 x64 avec le lanceur py est requis. '
                       'Un modèle déjà téléchargé peut être sélectionné directement.')
        label.setWordWrap(True)
        layout.addWidget(label)
        layout.addWidget(QLabel('Python du runtime de diarisation :'))
        self.python = QLineEdit(str(initial.get('python', self.settings.value('diarization_python', root / 'runtime/Scripts/python.exe'))))
        layout.addWidget(self.python)
        self.browse = QPushButton('Choisir python.exe…')
        self.browse.clicked.connect(self.choose_python)
        layout.addWidget(self.browse)
        layout.addWidget(QLabel('Dossier local Community-1 complet (config.yaml) :'))
        self.model = QLineEdit(str(initial.get('model', self.settings.value('diarization_model', root / 'models/community-1'))))
        layout.addWidget(self.model)
        self.browse_model = QPushButton('Choisir le modèle Community-1…')
        self.browse_model.clicked.connect(self.choose_model)
        layout.addWidget(self.browse_model)
        self.install = QPushButton('Télécharger et installer les dépendances (CPU / CUDA sélectionné)')
        self.install.clicked.connect(self.install_runtime)
        layout.addWidget(self.install)
        access = QLabel('<a href="https://huggingface.co/pyannote/speaker-diarization-community-1">'
                        'Accepter les conditions Community-1 sur Hugging Face</a> — '
                        'le téléchargement demande un jeton de lecture, non enregistré.')
        access.setOpenExternalLinks(True)
        access.setWordWrap(True)
        layout.addWidget(access)
        self.download = QPushButton('Télécharger le modèle Community-1')
        self.download.clicked.connect(self.download_model)
        layout.addWidget(self.download)
        self.status = QLabel('Prêt. Les deux opérations sont indépendantes.')
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.bar = QProgressBar()
        self.bar.setRange(0, 100)
        self.bar.setValue(0)
        layout.addWidget(self.bar)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.document().setMaximumBlockCount(300)
        self.log.setMaximumHeight(110)
        layout.addWidget(self.log)
        self.cancel_setup = QPushButton('Annuler la préparation en cours')
        self.cancel_setup.setEnabled(False)
        self.cancel_setup.clicked.connect(self.cancel.set)
        layout.addWidget(self.cancel_setup)
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Lancer la diarisation")
        root_layout.addWidget(self.buttons)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.poll)
        self.timer.start(100)

    def report(self, message, percent=None):
        try:
            self.messages.put_nowait((message, percent))
        except queue.Full:
            pass

    def set_preparing(self, active):
        for widget in (self.python, self.model, self.browse, self.browse_model,
                       self.device, self.controls, self.install, self.download):
            widget.setEnabled(not active)
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(not active)
        self.cancel_setup.setEnabled(active)

    def submit(self, operation, function, *args):
        if self.future is not None:
            return
        self.cancel.clear()
        self.operation = operation
        self.log.clear()
        self.status.setText('Préparation en cours…')
        self.bar.setRange(0, 0)
        self.set_preparing(True)
        self.future = self.pool.submit(function, *args, self.cancel, self.report)

    def install_runtime(self):
        self.submit('dependencies', install_dependencies, self.device.currentText())

    def download_model(self):
        if self.future is not None:
            return
        token, accepted = QInputDialog.getText(self, 'Accès au modèle Community-1',
            'Jeton Hugging Face de lecture autorisé (non enregistré) :', QLineEdit.EchoMode.Password)
        if accepted and token.strip():
            self.submit('model', download_community, self.model.text(), token.strip())

    def poll(self):
        for _ in range(50):
            try:
                message, percent = self.messages.get_nowait()
            except queue.Empty:
                break
            self.status.setText(message)
            self.log.appendPlainText(message)
            self.bar.setRange(0, 0 if percent is None else 100)
            if percent is not None:
                self.bar.setValue(percent)
        if self.future is None or not self.future.done():
            return
        future, self.future = self.future, None
        self.set_preparing(False)
        self.bar.setRange(0, 100)
        try:
            result = future.result()
            if self.operation == 'dependencies':
                self.python.setText(result)
                self.settings.setValue('diarization_python', result)
                message = 'Dépendances installées et vérifiées. Le Python du runtime est sélectionné.'
            else:
                self.model.setText(result)
                self.settings.setValue('diarization_model', result)
                message = 'Modèle téléchargé et intégrité vérifiée. Le runtime reste nécessaire pour l’analyse.'
            self.bar.setValue(100)
        except CancelledError:
            message = 'Préparation annulée. Relancez le même bouton pour reprendre ou réparer.'
            self.bar.setValue(0)
        except Exception as exc:
            message = str(exc)
            self.bar.setValue(0)
        while not self.messages.empty():
            self.messages.get_nowait()
        self.status.setText(message)
        self.log.appendPlainText(message)
        if self.close_pending:
            self.done(QDialog.DialogCode.Rejected)

    def done(self, result):
        if self.future is not None:
            self.close_pending = True
            self.cancel.set()
            self.status.setText('Arrêt de la préparation en cours avant fermeture…')
            return
        self.timer.stop()
        self.pool.shutdown(wait=False)
        super().done(result)

    def choose_python(self):
        path, _ = QFileDialog.getOpenFileName(self, 'Runtime Python', self.python.text(), 'Python (python.exe);;Tous (*)')
        if path:
            self.python.setText(path)

    def choose_model(self):
        path = QFileDialog.getExistingDirectory(self, 'Community-1 local', self.model.text())
        if path:
            self.model.setText(path)

    def accept(self):
        try:
            self.controls.values()
            if self.transcribe_first and (not Path(self.python.text()).is_file() or
                    not (Path(self.model.text()) / 'config.yaml').is_file()):
                raise ValueError('Préparez le runtime Python et Community-1 dans '
                                 'l’onglet Modèle et dépendances avant de lancer le traitement complet.')
        except ValueError as exc:
            QMessageBox.warning(self, 'Réglages de diarisation', str(exc))
            return
        super().accept()

    def values(self):
        for key, value in (('diarization_python', self.python.text()),
                           ('diarization_model', self.model.text()),
                           ('diarization_device', self.device.currentText())):
            self.settings.setValue(key, value)
        tuning = self.controls.values()
        self.settings.setValue('diarization_speakers', self.speakers.value())
        self.settings.setValue('diarization_tuning', json.dumps(tuning))
        return (self.python.text(), self.model.text(), self.device.currentText(),
                self.speakers.value(), tuning)
