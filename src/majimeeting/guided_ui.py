"""Select a few clean references, review proposals, apply an independent analysis."""
import json
import queue
import tempfile
import threading
from concurrent.futures import CancelledError, ThreadPoolExecutor
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from majimeeting.diarization_setup import default_runtime
from majimeeting.guided_store import (
    add_reference,
    apply_proposals,
    decisions,
    references,
    remove_reference,
)
from majimeeting.guided_voice import GuidedOptions, propose_guided
from majimeeting.playback import make_excerpt
from majimeeting.runtime_context import application_settings, shared_models
from majimeeting.speaker_overview import REASONS, speaker_display
from majimeeting.workspace_ui import scroll


class GuidedVoiceDialog(QDialog):
    def __init__(self, store, job, parent=None, seed=None):
        super().__init__(parent)
        self.store, self.job = store, job
        self.rows = store.segments(job)
        self.owner = parent
        while self.owner is not None and not hasattr(self.owner, 'busy'):
            self.owner = self.owner.parentWidget()
        with store.connect() as db:
            record = db.execute('SELECT meeting_id,status FROM transcription_jobs WHERE id=?', (job,)).fetchone()
        if record is None or record['status'] != 'completed':
            raise ValueError('Choisissez une transcription terminée.')
        self.meeting = record['meeting_id']
        self.settings = application_settings()
        self.python = str(self.settings.value('diarization_python', default_runtime()/'Scripts/python.exe'))
        self.model = str(self.settings.value('diarization_model', shared_models()/'community-1'))
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix='guided-voices')
        self.future = None
        self.operation = ''
        self.cancel = threading.Event()
        self.messages = queue.Queue(maxsize=1)
        self.close_pending = False
        self.preview = None
        self.proposals = []
        self.accepted = set()
        self.temp = tempfile.TemporaryDirectory(prefix='majimeeting-guide-')
        self.setWindowTitle('Séparer des voix confondues — références et propositions')
        self.resize(1100, 740)
        layout = QVBoxLayout(self)
        hint = QLabel('Ciblez le groupe mélangé et ses différentes voix. Choisissez 2 ou 3 extraits propres par personne (au moins un de 3 à 20 s). '
                      'Nommez-les, calculez l’aperçu puis retenez les propositions. '
                      'Aucun nouveau décodage Whisper ; les corrections manuelles restent protégées.')
        hint.setWordWrap(True)
        layout.addWidget(hint)
        form = QFormLayout()
        self.track = QComboBox()
        self.track.addItems(sorted({r['track'] for r in self.rows}))
        self.scope = QComboBox()
        self.device = QComboBox()
        self.device.addItems(['cpu','cuda'])
        self.device.setCurrentText(str(self.settings.value('diarization_device','cuda')))
        form.addRow('Piste à corriger', self.track)
        form.addRow('Groupe mélangé', self.scope)
        form.addRow('Calcul des empreintes', self.device)
        layout.addLayout(form)
        self.configure = QPushButton('Modèle et runtime Community-1…')
        self.configure.clicked.connect(self.configure_runtime)
        layout.addWidget(self.configure)
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs, 1)
        reference_page = QWidget()
        content = QVBoxLayout(reference_page)
        self.sources = QTableWidget(0, 4)
        self.sources.setHorizontalHeaderLabels(['Début / fin (s)', 'Groupe actuel', 'Intervenant', 'Texte'])
        self.sources.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.sources.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.sources.horizontalHeader().setStretchLastSection(True)
        self.sources.currentCellChanged.connect(self.seed_from_row)
        content.addWidget(self.sources, 1)
        fields = QHBoxLayout()
        self.name = QLineEdit()
        self.name.setPlaceholderText('Nom de la personne dans cet extrait')
        self.name.setMaxLength(200)
        self.first = QDoubleSpinBox()
        self.last = QDoubleSpinBox()
        for field in (self.first,self.last):
            field.setRange(0,86400)
            field.setDecimals(3)
            field.setSuffix(' s')
        fields.addWidget(self.name, 2)
        fields.addWidget(QLabel('Début'))
        fields.addWidget(self.first)
        fields.addWidget(QLabel('Fin'))
        fields.addWidget(self.last)
        content.addLayout(fields)
        self.clean = QCheckBox('J’ai écouté : une seule personne parle dans cet extrait')
        content.addWidget(self.clean)
        controls = QHBoxLayout()
        self.listen = QPushButton('Écouter ces bornes')
        self.listen.clicked.connect(lambda: self.play(self.track.currentText(),self.first.value(),self.last.value()))
        self.stop = QPushButton('Arrêter la lecture')
        self.stop.clicked.connect(self.player_stop)
        self.add = QPushButton('Ajouter comme référence')
        self.add.clicked.connect(self.add_sample)
        for widget in (self.listen,self.stop,self.add):
            controls.addWidget(widget)
        content.addLayout(controls)
        self.reference_table = QTableWidget(0, 3)
        self.reference_table.setHorizontalHeaderLabels(['Personne', 'Début / fin (s)', 'Piste'])
        self.reference_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.reference_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.reference_table.currentCellChanged.connect(self.seed_reference)
        self.reference_table.setMaximumHeight(140)
        content.addWidget(self.reference_table)
        self.remove = QPushButton('Retirer la référence sélectionnée')
        self.remove.clicked.connect(self.remove_sample)
        content.addWidget(self.remove)
        self.tabs.addTab(scroll(reference_page),'1. Références')
        preview_page = QWidget()
        content = QVBoxLayout(preview_page)
        options = QFormLayout()
        self.similarity = QDoubleSpinBox()
        self.similarity.setRange(.1,.95)
        self.similarity.setSingleStep(.05)
        self.similarity.setValue(.65)
        self.margin = QDoubleSpinBox()
        self.margin.setRange(.01,.5)
        self.margin.setSingleStep(.01)
        self.margin.setValue(.08)
        self.window = QDoubleSpinBox()
        self.window.setRange(1.5,5.)
        self.window.setSingleStep(.5)
        self.window.setValue(3.)
        options.addRow('Similarité cosinus minimale (pas une probabilité)',self.similarity)
        options.addRow('Écart minimal entre les deux personnes',self.margin)
        options.addRow('Contexte vocal (secondes)',self.window)
        content.addLayout(options)
        self.compute = QPushButton('Calculer / actualiser les propositions')
        self.compute.clicked.connect(self.calculate)
        content.addWidget(self.compute)
        self.summary = QLabel('Ajoutez au moins deux personnes distinctes sur cette piste.')
        self.summary.setWordWrap(True)
        self.summary.setMaximumHeight(140)
        content.addWidget(self.summary)
        self.proposal_table = QTableWidget(0, 6)
        self.proposal_table.setHorizontalHeaderLabels(['Retenir', 'Début / fin', 'Proposition', 'Cosinus', 'Écart', 'Texte / incertitude'])
        self.proposal_table.horizontalHeader().setStretchLastSection(True)
        self.proposal_table.itemChanged.connect(self.selection_changed)
        self.proposal_table.cellDoubleClicked.connect(self.play_proposal)
        content.addWidget(self.proposal_table, 1)
        choices = QHBoxLayout()
        self.all_button = QPushButton('Retenir toutes les propositions distinctes')
        self.none_button = QPushButton('Tout laisser à vérifier')
        self.all_button.clicked.connect(lambda: self.select_all(True))
        self.none_button.clicked.connect(lambda: self.select_all(False))
        choices.addWidget(self.all_button)
        choices.addWidget(self.none_button)
        content.addLayout(choices)
        explanation = QLabel('Appliquer crée une nouvelle analyse. Les passages ciblés incertains ou décochés '
            'deviennent « à vérifier ». Les autres groupes et corrections restent conservés. '
            'Double-cliquez une proposition pour écouter son début (60 s maximum).')
        explanation.setWordWrap(True)
        content.addWidget(explanation)
        self.apply = QPushButton('Appliquer les propositions retenues')
        self.apply.setEnabled(False)
        self.apply.clicked.connect(self.apply_selected)
        content.addWidget(self.apply)
        self.tabs.addTab(scroll(preview_page),'2. Comparer et appliquer')
        self.status = QLabel('Prêt. Les références et empreintes restent sur cet ordinateur.')
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.cancel_button = QPushButton('Annuler le calcul')
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(self.cancel.set)
        layout.addWidget(self.cancel_button)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.audio = QAudioOutput(self)
        self.player = QMediaPlayer(self)
        self.player.setAudioOutput(self.audio)
        self.player.errorOccurred.connect(lambda *_: self.status.setText('Lecture : '+self.player.errorString()))
        self.track.currentTextChanged.connect(self.reload_sources)
        self.scope.currentIndexChanged.connect(self.invalidate)
        for field in (self.similarity,self.margin,self.window):
            field.valueChanged.connect(self.invalidate)
        self.device.currentTextChanged.connect(self.invalidate)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.poll)
        self.timer.start(100)
        if seed and seed['track'] in [self.track.itemText(i) for i in range(self.track.count())]:
            self.track.setCurrentText(seed['track'])
        self.reload_sources()
        if seed:
            index = self.scope.findData(seed.get('speaker_group',''))
            self.scope.setCurrentIndex(max(0,index))
            self.first.setValue(seed['start'])
            self.last.setValue(seed['start']+min(12,max(3,seed['end']-seed['start'])))

    def configure_runtime(self):
        from majimeeting.diarization_ui import DiarizationDialog
        dialog = DiarizationDialog(self,initial=dict(python=self.python,model=self.model,device=self.device.currentText()))
        dialog.setWindowTitle('Modèle et runtime pour les références vocales')
        dialog.buttons.button(QDialogButtonBox.StandardButton.Ok).setText('Utiliser ces paramètres')
        if dialog.exec()==QDialog.DialogCode.Accepted:
            self.python,self.model,device,_,_ = dialog.values()
            self.device.setCurrentText(device)
            self.invalidate()

    def reload_sources(self, *_):
        self.local = [r for r in self.rows if r['track']==self.track.currentText()]
        self.sources.blockSignals(True)
        self.sources.setRowCount(len(self.local))
        for i,row in enumerate(self.local):
            for col,value in enumerate((f"{row['start']:.3f} → {row['end']:.3f}",row['speaker_group'],speaker_display(row),row['corrected_text'])):
                self.sources.setItem(i,col,QTableWidgetItem(value))
        self.sources.blockSignals(False)
        previous_scope = self.scope.currentData()
        self.scope.clear()
        self.scope.addItem('Choisir le groupe mélangé…',None)
        self.scope.addItem('Toute la piste — références pour toutes ses voix','')
        for group in sorted({r['speaker_group'] for r in self.local if r['speaker_group']}):
            self.scope.addItem(group,group)
        if previous_scope is not None:
            index = self.scope.findData(previous_scope)
            self.scope.setCurrentIndex(max(0,index))
        self.reload_references()
        self.invalidate()
        if self.local:
            self.sources.setCurrentCell(0,0)
            self.seed_from_row()

    def seed_from_row(self, *_):
        index = self.sources.currentRow()
        if 0 <= index < len(self.local):
            row = self.local[index]
            self.first.setValue(row['start'])
            self.last.setValue(row['start']+min(12,max(3,row['end']-row['start'])))
            self.clean.setChecked(False)

    def reload_references(self):
        self.refs = references(self.store,self.job,self.track.currentText())
        self.reference_table.setRowCount(len(self.refs))
        for i,ref in enumerate(self.refs):
            for col,value in enumerate((ref['name'],f"{ref['start']:.3f} → {ref['end']:.3f}",ref['track'])):
                self.reference_table.setItem(i,col,QTableWidgetItem(value))

    def seed_reference(self, *_):
        index = self.reference_table.currentRow()
        if 0 <= index < len(self.refs):
            ref = self.refs[index]
            self.first.setValue(ref['start'])
            self.last.setValue(ref['end'])
            self.name.setText(ref['name'])
            self.clean.setChecked(False)

    def add_sample(self):
        if not self.clean.isChecked():
            self.status.setText('Écoutez l’extrait et confirmez qu’une seule personne parle.')
            return
        try:
            add_reference(self.store,self.job,self.track.currentText(),self.first.value(),self.last.value(),self.name.text())
            self.reload_references()
            self.clean.setChecked(False)
            self.invalidate()
            self.status.setText('Référence enregistrée. Ajoutez un autre extrait ou une autre personne.')
        except (ValueError,OSError) as exc:
            self.status.setText(str(exc))

    def remove_sample(self):
        index = self.reference_table.currentRow()
        if 0 <= index < len(self.refs):
            remove_reference(self.store,self.job,self.refs[index]['id'])
            self.reload_references()
            self.invalidate()

    def invalidate(self, *_):
        self.preview = None
        self.apply.setEnabled(False)
        self.summary.setText('Aperçu à calculer avec les références et réglages actuels.')

    def progress(self,message):
        try:
            self.messages.get_nowait()
        except queue.Empty:
            pass
        self.messages.put_nowait(message)

    def launch(self,operation,function,*args):
        if self.future is not None:
            return
        self.player_stop()
        self.cancel.clear()
        self.operation = operation
        self.future = self.pool.submit(function,*args)
        for widget in (self.track,self.scope,self.configure,self.device,self.tabs):
            widget.setEnabled(False)
        self.cancel_button.setEnabled(operation!='play')
        if self.owner:
            self.owner.guided_busy = True
            self.owner.busy(True)
        self.status.setText('Traitement en cours…')

    def calculate(self):
        if self.scope.currentData() is None:
            self.status.setText('Choisissez le groupe mélangé ou explicitement Toute la piste.')
            return
        self.invalidate()
        options = GuidedOptions(self.similarity.value(),self.margin.value(),self.window.value())
        self.launch('propose',propose_guided,self.store,self.job,self.track.currentText(),self.scope.currentData(),
                    self.python,self.model,self.device.currentText(),options,self.cancel,self.progress)

    def select_all(self,enabled):
        self.accepted = {r['id'] for r in self.proposals if r['target'] and r['group_id'] and not r['reason']} if enabled else set()
        self.render()

    def render(self):
        visible = [r for r in self.proposals if r['target']][:1000]
        self.visible = visible
        self.proposal_table.blockSignals(True)
        self.proposal_table.setRowCount(len(visible))
        for i,row in enumerate(visible):
            item = QTableWidgetItem()
            valid = bool(row['group_id'] and not row['reason'])
            item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable |
                          (Qt.ItemFlag.ItemIsUserCheckable if valid else Qt.ItemFlag.NoItemFlags))
            item.setCheckState(Qt.CheckState.Checked if row['id'] in self.accepted else Qt.CheckState.Unchecked)
            self.proposal_table.setItem(i,0,item)
            values = (f"{row['start']:.3f} → {row['end']:.3f}", self.names.get(row['group_id'],'À vérifier'),
                f"{row['score']:.3f}" if row['score'] is not None else ('référence' if row['group_id'] and not row['reason'] else '—'),
                f"{row['margin']:.3f}" if row['margin'] is not None else '—',
                row['text'] + (' — '+REASONS.get(row['reason'],row['reason']) if row['reason'] else ''))
            for col,value in enumerate(values,1):
                self.proposal_table.setItem(i,col,QTableWidgetItem(value))
        self.proposal_table.blockSignals(False)
        self.update_count()

    def selection_changed(self,item):
        if item.column()!=0 or not 0 <= item.row() < len(self.visible):
            return
        rid = self.visible[item.row()]['id']
        if item.checkState()==Qt.CheckState.Checked:
            self.accepted.add(rid)
        else:
            self.accepted.discard(rid)
        self.update_count()

    def update_count(self):
        self.apply.setText(f'Appliquer les propositions retenues ({len(self.accepted)})')
        self.apply.setEnabled(bool(self.preview and self.accepted) and self.future is None)

    def play(self,track,start,end):
        self.launch('play',make_excerpt,self.store.root/self.meeting/track,start,min(end,start+60),Path(self.temp.name)/'excerpt.wav')

    def play_proposal(self,index,*_):
        if 0 <= index < len(self.visible):
            row = self.visible[index]
            self.play(self.track.currentText(),row['start'],row['end'])

    def player_stop(self):
        if hasattr(self,'player'):
            self.player.stop()
            self.player.setSource(QUrl())

    def apply_selected(self):
        if self.preview and self.accepted:
            self.launch('apply',apply_proposals,self.store,self.preview,set(self.accepted),self.cancel)

    def poll(self):
        try:
            self.status.setText(self.messages.get_nowait())
        except queue.Empty:
            pass
        if self.future is None or not self.future.done():
            return
        future,self.future = self.future,None
        for widget in (self.track,self.scope,self.configure,self.device,self.tabs):
            widget.setEnabled(True)
        self.cancel_button.setEnabled(False)
        if self.owner:
            self.owner.guided_busy = False
            self.owner.busy(False)
        try:
            result = future.result()
            if self.operation=='propose':
                self.preview = result
                self.proposals = decisions(self.store,result)
                with self.store.connect() as db:
                    info = json.loads(db.execute('SELECT options FROM guided_runs WHERE id=?',(result,)).fetchone()[0])
                self.names = info['names']
                self.select_all(True)
                count = sum(bool(r['group_id'] and not r['reason']) for r in self.proposals if r['target'])
                total = sum(r['target'] for r in self.proposals)
                self.summary.setText(f'{count}/{total} propositions distinctes. {min(total,1000)} lignes affichées ; '
                    f'l’application concerne toutes les propositions retenues, y compris hors affichage. '
                    f"Segments corrigés protégés : {info['protected_segments']}. "
                    f"Empreintes réutilisées : passages={info['clips_reused']}, références={info['references_reused']}.\n"+
                    '\n'.join(info.get('warnings',[])[:6]))
                self.summary.setToolTip('\n'.join(info.get('warnings',[])))
                self.tabs.setCurrentIndex(1)
                self.status.setText('Aperçu prêt. Vérifiez les propositions avant de les appliquer.')
            elif self.operation=='apply':
                self.preview = None
                self.rows = self.store.segments(self.job)
                self.reload_sources()
                self.status.setText('Nouvelle analyse appliquée. L’ancienne reste disponible dans l’historique.')
            elif not self.close_pending:
                self.player.setSource(QUrl.fromLocalFile(str(Path(self.temp.name)/'excerpt.wav')))
                self.player.play()
                self.status.setText(f'Lecture ({result:.1f} s).')
        except CancelledError:
            self.status.setText('Calcul annulé ; attributions précédentes conservées.')
        except Exception as exc:
            self.status.setText(str(exc))
        self.update_count()
        if self.close_pending:
            self.done(QDialog.DialogCode.Rejected)

    def done(self,result):
        if self.future is not None:
            self.close_pending = True
            self.cancel.set()
            self.status.setText('Arrêt du traitement avant fermeture…')
            return
        self.timer.stop()
        self.player_stop()
        self.pool.shutdown(wait=False)
        self.temp.cleanup()
        super().done(result)
