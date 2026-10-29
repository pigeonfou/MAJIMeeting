"""Quality controls for the supported Community-1 / VBx pipeline."""
from dataclasses import asdict

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)

from majimeeting.diarization_options import DiarizationOptions


def count_box(value=0):
    box = QSpinBox()
    box.setRange(0, 50)
    box.setSpecialValueText('Automatique')
    box.setValue(value)
    return box


def decimal_box(low, high, value, step):
    box = QDoubleSpinBox()
    box.setRange(low, high)
    box.setDecimals(3)
    box.setSingleStep(step)
    box.setValue(value)
    return box


class DiarizationControls(QWidget):
    def __init__(self, speakers=0, tuning=None, tracks=(), parent=None):
        super().__init__(parent)
        self.tracks = list(tracks)
        layout = QVBoxLayout(self)
        help_text = QLabel('Relance uniquement la diarisation : audio et transcription sont réutilisés. '
            'Une voix retrouvée peut former plusieurs groupes ; ces réglages ne créent pas '
            'de reconnaissance biométrique. Les groupes de pistes différentes restent indépendants.')
        help_text.setWordWrap(True)
        layout.addWidget(help_text)
        form = QFormLayout()
        self.speakers = count_box()
        self.minimum = count_box()
        self.maximum = count_box()
        form.addRow('Nombre exact de voix par piste (0 = auto)', self.speakers)
        form.addRow('Minimum (0 = modèle)', self.minimum)
        form.addRow('Maximum (0 = modèle)', self.maximum)
        self.speakers.valueChanged.connect(self.update_counts)
        layout.addLayout(form)
        self.table = QTableWidget(len(self.tracks), 5)
        self.table.setHorizontalHeaderLabels(['Piste', 'Spécifique', 'Exact', 'Minimum', 'Maximum'])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setMaximumHeight(170)
        self.track_controls = {}
        for index, track in enumerate(self.tracks):
            label = QLabel(track)
            check = QCheckBox()
            exact, minimum, maximum = count_box(), count_box(), count_box()
            self.track_controls[track] = (check, exact, minimum, maximum)
            for column, widget in enumerate((label, check, exact, minimum, maximum)):
                self.table.setCellWidget(index, column, widget)
            check.toggled.connect(self.update_counts)
            exact.valueChanged.connect(self.update_counts)
        if self.tracks:
            layout.addWidget(QLabel('Réglage spécifique si micro et audio système n’ont pas le même nombre de voix :'))
            layout.addWidget(self.table)
        self.clustering = QGroupBox('Modifier le regroupement des voix — avancé')
        self.clustering.setCheckable(True)
        group_form = QFormLayout(self.clustering)
        self.threshold = decimal_box(.5, .8, .6, .01)
        self.fa = decimal_box(.01, .5, .07, .01)
        self.fb = decimal_box(.01, 15., .8, .1)
        group_form.addRow('Seuil initial de regroupement (0,5–0,8)', self.threshold)
        group_form.addRow('VBx Fa (0,01–0,5)', self.fa)
        group_form.addRow('VBx Fb (0,01–15)', self.fb)
        hint = QLabel('Seuil plus élevé : davantage de fusions lors du regroupement initial. '
                      'VBx peut ensuite modifier les groupes : le résultat doit être comparé. '
                      'Fa/Fb sont expérimentaux ; changez un seul réglage à la fois. '
                      'Case décochée : paramètres du modèle conservés.')
        hint.setWordWrap(True)
        group_form.addRow(hint)
        layout.addWidget(self.clustering)
        self.segmentation = QGroupBox('Modifier le comblement des silences')
        self.segmentation.setCheckable(True)
        segmentation_form = QFormLayout(self.segmentation)
        self.silence = decimal_box(0., 1., 0., .05)
        segmentation_form.addRow('Combler les pauses inférieures à (secondes)', self.silence)
        layout.addWidget(self.segmentation)
        performance = QFormLayout()
        self.overlap = QComboBox()
        self.overlap.addItem('Réglage du modèle', None)
        self.overlap.addItem('Exclure les voix superposées des empreintes', True)
        self.overlap.addItem('Inclure les voix superposées dans les empreintes', False)
        performance.addRow('Extraction des empreintes vocales', self.overlap)
        self.seg_batch, self.emb_batch = QSpinBox(), QSpinBox()
        for box in (self.seg_batch, self.emb_batch):
            box.setRange(0, 64)
            box.setSpecialValueText('Modèle')
        performance.addRow('Lot de segmentation (vitesse / VRAM)', self.seg_batch)
        performance.addRow('Lot d’empreintes (vitesse / VRAM)', self.emb_batch)
        layout.addLayout(performance)
        note = QLabel('Les tailles de lots règlent le débit et la mémoire ; elles ne garantissent '
                      'pas une meilleure reconnaissance. En cas de mémoire insuffisante, réduisez-les.')
        note.setWordWrap(True)
        layout.addWidget(note)
        self.reset = QPushButton('Rétablir les réglages du modèle et le nombre automatique')
        self.reset.clicked.connect(lambda: self.load(0, {}))
        layout.addWidget(self.reset)
        layout.addStretch()
        self.load(speakers, tuning or {})

    def load(self, speakers, tuning):
        self.speakers.setValue(speakers)
        self.minimum.setValue(tuning.get('min_speakers', 0))
        self.maximum.setValue(tuning.get('max_speakers', 0))
        self.clustering.setChecked(any(tuning.get(k) is not None for k in ('threshold', 'fa', 'fb')))
        for name, box, default in [('threshold', self.threshold, .6), ('fa', self.fa, .07),
                                    ('fb', self.fb, .8)]:
            box.setValue(tuning.get(name) if tuning.get(name) is not None else default)
        self.segmentation.setChecked(tuning.get('min_duration_off') is not None)
        self.silence.setValue(tuning.get('min_duration_off') or 0.)
        value = tuning.get('exclude_overlap')
        self.overlap.setCurrentIndex(0 if value is None else (1 if value else 2))
        self.seg_batch.setValue(tuning.get('segmentation_batch_size', 0))
        self.emb_batch.setValue(tuning.get('embedding_batch_size', 0))
        for track, (check, exact, minimum, maximum) in self.track_controls.items():
            values = tuning.get('track_speakers', {}).get(track)
            check.setChecked(values is not None)
            values = values or {}
            exact.setValue(values.get('speakers', 0))
            minimum.setValue(values.get('min_speakers', 0))
            maximum.setValue(values.get('max_speakers', 0))
        self.update_counts()

    def update_counts(self, *_):
        for active, exact, minimum, maximum in [
            (True, self.speakers, self.minimum, self.maximum),
            *((c.isChecked(), e, low, high) for c, e, low, high in self.track_controls.values())]:
            exact.setEnabled(active)
            for box in (minimum, maximum):
                box.setEnabled(active and exact.value() == 0)
                if exact.value():
                    box.setValue(0)

    def values(self):
        tracks = {track: dict(speakers=exact.value(), min_speakers=minimum.value(),
                              max_speakers=maximum.value())
                  for track, (check, exact, minimum, maximum) in self.track_controls.items()
                  if check.isChecked()}
        options = DiarizationOptions(
            min_speakers=self.minimum.value(), max_speakers=self.maximum.value(),
            threshold=self.threshold.value() if self.clustering.isChecked() else None,
            fa=self.fa.value() if self.clustering.isChecked() else None,
            fb=self.fb.value() if self.clustering.isChecked() else None,
            min_duration_off=self.silence.value() if self.segmentation.isChecked() else None,
            exclude_overlap=self.overlap.currentData(),
            segmentation_batch_size=self.seg_batch.value(), embedding_batch_size=self.emb_batch.value(),
            track_speakers=tracks).validate(self.speakers.value())
        return asdict(options)
