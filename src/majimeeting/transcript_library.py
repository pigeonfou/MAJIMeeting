"""Open a saved transcription without importing audio or running Whisper again."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHeaderView,
    QLabel,
    QLineEdit,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)


def saved_transcripts(store):
    with store.connect() as db:
        return [dict(row) for row in db.execute('''
            SELECT j.id,j.meeting_id,j.created,m.title,COUNT(s.id) AS segments
            FROM transcription_jobs j JOIN meetings m ON m.id=j.meeting_id
            JOIN transcript_segments s ON s.job_id=j.id
            WHERE j.status='completed' GROUP BY j.id ORDER BY j.rowid DESC
        ''')]


class TranscriptLibrary(QDialog):
    def __init__(self, store, parent=None):
        super().__init__(parent)
        self.rows = saved_transcripts(store)
        self.setWindowTitle('Ouvrir une transcription sauvegardée')
        self.resize(900, 500)
        layout = QVBoxLayout(self)
        label = QLabel('Les transcriptions et corrections sont déjà enregistrées localement. '
                       'Ouvrir ne relance aucun calcul. L’audio d’origine doit rester présent '
                       'pour réécouter et refaire la diarisation.')
        label.setWordWrap(True)
        layout.addWidget(label)
        self.search = QLineEdit()
        self.search.setPlaceholderText('Rechercher une réunion ou une date…')
        self.search.textChanged.connect(self.filter)
        layout.addWidget(self.search)
        self.table = QTableWidget(len(self.rows), 3)
        self.table.setHorizontalHeaderLabels(['Réunion', 'Transcription', 'Passages'])
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for index, row in enumerate(self.rows):
            for column, value in enumerate((row['title'], row['created'][:19], row['segments'])):
                item = QTableWidgetItem(str(value))
                item.setData(Qt.ItemDataRole.UserRole, row['id'])
                self.table.setItem(index, column, item)
        self.table.cellDoubleClicked.connect(lambda *_: self.accept())
        self.table.currentCellChanged.connect(self.update_button)
        layout.addWidget(self.table)
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Open |
                                        QDialogButtonBox.StandardButton.Cancel)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
        if self.rows:
            self.table.setCurrentCell(0, 0)
        self.update_button()

    def job(self):
        index = self.table.currentRow()
        return (self.rows[index]['id'] if 0 <= index < len(self.rows) and
                not self.table.isRowHidden(index) else None)

    def update_button(self, *_):
        self.buttons.button(QDialogButtonBox.StandardButton.Open).setEnabled(bool(self.job()))

    def filter(self, text):
        first = None
        for index, row in enumerate(self.rows):
            visible = text.casefold() in (row['title'] + ' ' + row['created']).casefold()
            self.table.setRowHidden(index, not visible)
            if visible and first is None:
                first = index
        self.table.setCurrentCell(-1 if first is None else first, 0)
        self.update_button()

    def accept(self):
        if self.job():
            super().accept()
