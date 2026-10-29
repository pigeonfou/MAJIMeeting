"""Configuration for the optional, isolated Community-1 runtime."""
import os
from pathlib import Path

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)


class DiarizationDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Distinguer les interlocuteurs — Community-1 local')
        self.resize(700, 430)
        self.settings = QSettings('MAJIMeeting', 'MAJIMeeting')
        root = Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'MAJIMeeting'
        layout = QVBoxLayout(self)
        label = QLabel('Analyse après transcription, sans serveur. Les groupes ne constituent '
                       'pas une identification des personnes. Chaque piste a ses propres groupes. '
                       'Les passages ambigus restent à vérifier.\n\n'
                       'Préparation initiale : utilisez le script setup-diarization.ps1 livré dans '
                       'le dossier de l’application. Il nécessite Python 3.11, un accès Hugging Face '
                       'autorisé à Community-1 et une connexion pour installer le runtime/modèle.')
        label.setWordWrap(True)
        layout.addWidget(label)
        layout.addWidget(QLabel('Python du runtime de diarisation :'))
        self.python = QLineEdit(str(self.settings.value('diarization_python', root / 'runtime/Scripts/python.exe')))
        layout.addWidget(self.python)
        browse = QPushButton('Choisir python.exe…')
        browse.clicked.connect(self.choose_python)
        layout.addWidget(browse)
        layout.addWidget(QLabel('Dossier local Community-1 complet (config.yaml) :'))
        self.model = QLineEdit(str(self.settings.value('diarization_model', root / 'models/community-1')))
        layout.addWidget(self.model)
        browse_model = QPushButton('Choisir le modèle Community-1…')
        browse_model.clicked.connect(self.choose_model)
        layout.addWidget(browse_model)
        self.device = QComboBox()
        self.device.addItems(['cpu', 'cuda'])
        self.device.setCurrentText(str(self.settings.value('diarization_device', 'cuda')))
        layout.addWidget(self.device)
        layout.addWidget(QLabel('Nombre de voix par piste (0 = détection automatique) :'))
        self.speakers = QSpinBox()
        self.speakers.setRange(0, 50)
        layout.addWidget(self.speakers)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def choose_python(self):
        path, _ = QFileDialog.getOpenFileName(self, 'Runtime Python', self.python.text(), 'Python (python.exe);;Tous (*)')
        if path:
            self.python.setText(path)

    def choose_model(self):
        path = QFileDialog.getExistingDirectory(self, 'Community-1 local', self.model.text())
        if path:
            self.model.setText(path)

    def values(self):
        for key, value in (('diarization_python', self.python.text()),
                           ('diarization_model', self.model.text()),
                           ('diarization_device', self.device.currentText())):
            self.settings.setValue(key, value)
        return self.python.text(), self.model.text(), self.device.currentText(), self.speakers.value()
