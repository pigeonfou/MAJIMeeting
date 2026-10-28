"""Human corrections and bounded source playback, independent of inference."""
import sqlite3
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PySide6.QtCore import QTimer, QUrl
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from majimeeting.playback import make_excerpt


class TranscriptEditor(QDialog):
    def __init__(self, store, job, parent=None):
        super().__init__(parent)
        self.store, self.job = store, job
        with store.connect() as db:
            record = db.execute('SELECT meeting_id,status FROM transcription_jobs WHERE id=?',
                                (job,)).fetchone()
        if record is None or record['status'] == 'running':
            raise ValueError('Sélectionnez un traitement terminé.')
        self.meeting = record['meeting_id']
        self.rows = []
        self.future = None
        self.play_when_ready = False
        self.pool = ThreadPoolExecutor(max_workers=1)
        self.temporary = tempfile.TemporaryDirectory(prefix='majimeeting-playback-')
        self.setWindowTitle('Transcription — corrections et réécoute')
        self.resize(1100, 750)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel('Sélectionnez un passage pour le corriger ; double-cliquez pour '
                                'l’écouter (60 s maximum). Les pistes ne sont pas des personnes.'))
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(['Début (s)', 'Piste', 'Intervenant', 'Texte'])
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.currentCellChanged.connect(self.selected)
        self.table.cellDoubleClicked.connect(lambda *_: self.play())
        layout.addWidget(self.table)
        self.speaker = QLineEdit()
        self.speaker.setMaxLength(200)
        self.speaker.setPlaceholderText('Nom attribué manuellement ; vide = intervenant inconnu')
        layout.addWidget(self.speaker)
        self.text = QPlainTextEdit()
        self.text.setMaximumHeight(120)
        layout.addWidget(self.text)
        controls = QHBoxLayout()
        self.save = QPushButton('Enregistrer la correction')
        self.save.clicked.connect(self.save_edit)
        controls.addWidget(self.save)
        self.restore = QPushButton('Rétablir le texte original et retirer le nom')
        self.restore.clicked.connect(self.restore_original)
        controls.addWidget(self.restore)
        self.listen = QPushButton('Écouter ce passage')
        self.listen.clicked.connect(self.play)
        controls.addWidget(self.listen)
        stop = QPushButton('Arrêter la lecture')
        stop.clicked.connect(self.stop)
        controls.addWidget(stop)
        layout.addLayout(controls)
        self.history = QPlainTextEdit()
        self.history.setReadOnly(True)
        self.history.setMaximumHeight(120)
        layout.addWidget(self.history)
        self.status = QLabel('')
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.audio = QAudioOutput(self)
        self.player = QMediaPlayer(self)
        self.player.setAudioOutput(self.audio)
        self.player.errorOccurred.connect(lambda *_: self.status.setText(
            'Erreur de lecture : ' + self.player.errorString()))
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.poll)
        self.timer.start(100)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.reload()

    def reload(self, selected=0):
        self.rows = self.store.segments(self.job)
        self.table.blockSignals(True)
        self.table.setRowCount(len(self.rows))
        for index, row in enumerate(self.rows):
            for column, value in enumerate((f"{row['start']:.3f}", row['track'],
                                             row['speaker'] or 'Inconnu', row['corrected_text'])):
                self.table.setItem(index, column, QTableWidgetItem(value))
        self.table.blockSignals(False)
        if self.rows:
            self.table.setCurrentCell(min(selected, len(self.rows) - 1), 0)
        self.selected()

    def current(self):
        index = self.table.currentRow()
        return self.rows[index] if 0 <= index < len(self.rows) else None

    def selected(self, *_):
        row = self.current()
        for widget in (self.save, self.restore, self.speaker, self.text):
            widget.setEnabled(row is not None)
        self.listen.setEnabled(row is not None and self.future is None)
        self.text.setPlainText(row['corrected_text'] if row else '')
        self.speaker.setText(row['speaker'] if row else '')
        if row:
            edits = self.store.segment_history(row['id'])
            self.history.setPlainText('Original : ' + row['original_text'] + '\n' + '\n'.join(
                f"{edit['created']} — {edit['speaker'] or 'Inconnu'} : {edit['text']}"
                for edit in edits))
        else:
            self.history.clear()

    def save_edit(self):
        row = self.current()
        if row is None:
            return
        try:
            self.store.edit_segment(row['id'], self.text.toPlainText(), self.speaker.text())
            self.reload(self.table.currentRow())
            self.status.setText('Correction enregistrée ; original et historique conservés.')
        except (ValueError, OSError, sqlite3.Error) as exc:
            self.status.setText(str(exc))

    def restore_original(self):
        row = self.current()
        if row:
            self.text.setPlainText(row['original_text'])
            self.speaker.clear()
            self.save_edit()

    def play(self):
        row = self.current()
        if row is None or self.future is not None:
            return
        self.player.stop()
        self.player.setSource(QUrl())
        track = self.store.root / self.meeting / row['track']
        # Only catalogue-generated track names may address meeting audio.
        if Path(row['track']).name != row['track'] or not row['track'].startswith('track-'):
            self.status.setText('Piste audio invalide.')
            return
        self.listen.setEnabled(False)
        self.status.setText('Préparation du passage audio…')
        self.play_when_ready = True
        self.future = self.pool.submit(make_excerpt, track, row['start'], row['end'],
                                       Path(self.temporary.name) / 'excerpt.wav')

    def poll(self):
        if self.future is None or not self.future.done():
            return
        future, self.future = self.future, None
        self.listen.setEnabled(self.current() is not None)
        try:
            duration = future.result()
            if not self.play_when_ready:
                self.status.setText('Lecture arrêtée.')
                return
            self.player.setSource(QUrl.fromLocalFile(str(Path(self.temporary.name) / 'excerpt.wav')))
            self.player.play()
            self.status.setText(f'Lecture du passage sélectionné ({duration:.1f} s).')
        except Exception as exc:
            self.status.setText('Lecture impossible : ' + str(exc))

    def stop(self):
        self.player.stop()
        self.play_when_ready = False
        self.status.setText('Lecture arrêtée.')

    def done(self, result):
        if self.future is not None:
            self.status.setText('Attendez la fin de préparation du passage avant de fermer.')
            return
        self.timer.stop()
        self.player.stop()
        self.player.setSource(QUrl())
        self.pool.shutdown(wait=False)
        self.temporary.cleanup()
        super().done(result)
