"""Name a handful of groups from short representative excerpts, not a full replay."""
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PySide6.QtCore import QTimer, QUrl
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import (
    QComboBox,
    QCompleter,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from majimeeting.playback import make_excerpt
from majimeeting.speakers import latest_run, name_group

REASONS = dict(overlap='Paroles simultanées', voice_boundary='Changement de voix incertain',
               uncovered='Voix non attribuée', low_alignment_confidence='Alignement du mot incertain',
               word_alignment_missing='Alignement mot à mot nécessaire',
               manual_source_correction='Correction existante : découpage à vérifier')


def speaker_display(row):
    if row['speaker']:
        return row['speaker']
    reason = REASONS.get(row.get('speaker_reason'), 'Voix à vérifier')
    candidates = row.get('speaker_candidates', [])
    return reason + (' : ' + ' / '.join(candidates) if candidates else '')


def samples(store, job):
    with store.connect() as db:
        run = latest_run(db, job)
        turns = [dict(r) for r in db.execute('SELECT * FROM speaker_turns WHERE run_id=? ORDER BY start', (run,))]
        names = {}
        for row in db.execute('SELECT group_id,name FROM speaker_names WHERE run_id=? ORDER BY id', (run,)):
            names[row['group_id']] = row['name']
    rows = store.segments(job)
    result = []
    for track, label in sorted({(t['track'], t['label']) for t in turns}):
        group = track + ':' + label
        choices = []
        for turn in sorted((t for t in turns if (t['track'], t['label']) == (track, label)),
                           key=lambda t: t['end'] - t['start'], reverse=True)[:20]:
            intervals = [(turn['start'], turn['end'])]
            for other in (t for t in turns if t['track'] == track and t['label'] != label):
                clean = []
                for a, b in intervals:
                    if other['end'] <= a or other['start'] >= b:
                        clean.append((a, b))
                    else:
                        if a < other['start']:
                            clean.append((a, other['start']))
                        if b > other['end']:
                            clean.append((other['end'], b))
                intervals = clean
            for a, b in intervals:
                if b - a >= 1.:
                    text = ' '.join(r['corrected_text'].strip() for r in rows
                                    if r['track'] == track and r['start'] < min(b, a + 12) and r['end'] > a)
                    choices.append(dict(track=track, start=a, end=min(b, a + 12), text=text,
                                        score=min(b - a, 12)))
        choices.sort(key=lambda c: (-c['score'], c['start']))
        chosen = []
        for choice in choices:
            if all(abs(choice['start'] - c['start']) > 5 for c in chosen):
                chosen.append(choice)
            if len(chosen) == 3:
                break
        result.append(dict(group=group, name=names.get(group, ''), samples=chosen,
                           passages=sum(r['speaker_group'] == group for r in rows)))
    return result


class SpeakerOverview(QDialog):
    def __init__(self, store, job, parent=None):
        super().__init__(parent)
        self.store, self.job = store, job
        self.groups = samples(store, job)
        with store.connect() as db:
            self.meeting = db.execute('SELECT meeting_id FROM transcription_jobs WHERE id=?', (job,)).fetchone()[0]
        self.future = None
        self.pool = ThreadPoolExecutor(max_workers=1)
        self.temp = tempfile.TemporaryDirectory(prefix='majimeeting-voices-')
        self.setWindowTitle('Nommer les intervenants — quelques extraits représentatifs')
        self.resize(1000, 600)
        layout = QVBoxLayout(self)
        label = QLabel('Écoutez un court extrait par groupe si nécessaire, puis donnez son nom une seule fois. '
                       'Le nom s’applique à tous ses passages non corrigés. Une même personne peut être '
                       'fragmentée en plusieurs groupes : vous pouvez leur donner le même nom. '
                       'Les groupes restent des hypothèses, pas une identification certaine.')
        label.setWordWrap(True)
        layout.addWidget(label)
        self.table = QTableWidget(len(self.groups), 4)
        self.table.setHorizontalHeaderLabels(['Groupe / piste', 'Nom', 'Passages', 'Extrait proposé'])
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setStretchLastSection(True)
        for column, width in enumerate((180, 180, 80)):
            self.table.setColumnWidth(column, width)
        with store.connect() as db:
            known = [r[0] for r in db.execute('SELECT DISTINCT n.name FROM speaker_names n '
                     'JOIN diarization_runs r ON r.id=n.run_id WHERE r.job_id=? AND n.name<>?', (job, ''))]
        self.names = []
        for index, group in enumerate(self.groups):
            self.table.setItem(index, 0, QTableWidgetItem(group['group']))
            field = QLineEdit(group['name'])
            field.setMaxLength(200)
            field.setCompleter(QCompleter(known, field))
            self.names.append(field)
            self.table.setCellWidget(index, 1, field)
            self.table.setItem(index, 2, QTableWidgetItem(str(group['passages'])))
            text = group['samples'][0]['text'] if group['samples'] else 'Aucun extrait isolé : à vérifier'
            self.table.setItem(index, 3, QTableWidgetItem(text))
        layout.addWidget(self.table)
        self.choice = QComboBox()
        layout.addWidget(self.choice)
        self.table.currentCellChanged.connect(self.selected)
        self.choice.currentIndexChanged.connect(lambda *_: self.stop())
        controls = QHBoxLayout()
        self.listen = QPushButton('Écouter cet extrait (12 s maximum)')
        self.listen.clicked.connect(self.play)
        controls.addWidget(self.listen)
        stop = QPushButton('Arrêter')
        stop.clicked.connect(self.stop)
        controls.addWidget(stop)
        apply = QPushButton('Appliquer les noms à tous les passages')
        apply.clicked.connect(self.apply_names)
        controls.addWidget(apply)
        layout.addLayout(controls)
        self.status = QLabel('')
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.audio = QAudioOutput(self)
        self.player = QMediaPlayer(self)
        self.player.setAudioOutput(self.audio)
        self.player.errorOccurred.connect(lambda *_: self.status.setText(self.player.errorString()))
        self.play_pending = False
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.poll)
        self.timer.start(100)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        if self.groups:
            self.table.setCurrentCell(0, 0)
        self.selected()

    def selected(self, *_):
        self.stop()
        self.choice.clear()
        index = self.table.currentRow()
        if 0 <= index < len(self.groups):
            for sample in self.groups[index]['samples']:
                self.choice.addItem(f"{sample['start']:.1f}–{sample['end']:.1f} s — {sample['text'][:100]}", sample)
        self.listen.setEnabled(self.future is None and self.choice.count() > 0)

    def apply_names(self):
        try:
            for group, field in zip(self.groups, self.names):
                value = field.text().strip()
                if value != group['name']:
                    name_group(self.store, self.job, group['group'], value)
                    group['name'] = value
            self.status.setText('Noms enregistrés et appliqués à tous les passages correspondants.')
            return True
        except Exception as exc:
            self.status.setText(str(exc))
            return False

    def play(self):
        sample = self.choice.currentData()
        if self.future is not None or not sample:
            return
        self.stop()
        self.player.setSource(QUrl())
        self.listen.setEnabled(False)
        self.play_pending = True
        self.future = self.pool.submit(make_excerpt,
            self.store.root / self.meeting / sample['track'], sample['start'], sample['end'],
            Path(self.temp.name) / 'voice.wav')
        self.status.setText('Préparation du court extrait…')

    def poll(self):
        if self.future is None or not self.future.done():
            return
        future, self.future = self.future, None
        self.listen.setEnabled(self.choice.count() > 0)
        try:
            future.result()
            if self.play_pending:
                self.player.setSource(QUrl.fromLocalFile(str(Path(self.temp.name) / 'voice.wav')))
                self.player.play()
                self.status.setText('Lecture de l’extrait représentatif.')
        except Exception as exc:
            self.status.setText(str(exc))

    def stop(self):
        self.play_pending = False
        if hasattr(self, 'player'):
            self.player.stop()

    def done(self, result):
        if self.future is not None:
            self.stop()
            self.status.setText('Attendez la fin de préparation de l’extrait avant de fermer.')
            return
        if not self.apply_names():
            return
        self.timer.stop()
        self.player.stop()
        self.player.setSource(QUrl())
        self.pool.shutdown(wait=False)
        self.temp.cleanup()
        super().done(result)
