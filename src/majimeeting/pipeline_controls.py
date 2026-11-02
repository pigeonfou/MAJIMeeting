"""Opt-in audio-first workflow controls; legacy results remain readable."""
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QSpinBox,
)

from majimeeting.audio_preparation import PreparationOptions


class PipelineControls(QGroupBox):
    def __init__(self, settings):
        super().__init__('Parcours de traitement complet')
        self.settings = settings
        form = QFormLayout(self)
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        self.mode = QComboBox()
        self.mode.addItem('Classique — transcription puis voix', 'legacy')
        self.mode.addItem('Expérimental — audio, voix puis transcription', 'audio_first_v1')
        self.mode.setCurrentIndex(max(0, self.mode.findData(settings.value('pipeline_mode', 'legacy'))))
        form.addRow('Parcours', self.mode)
        self.normalize = QCheckBox('Normalisation modérée sur les copies de travail')
        self.normalize.setChecked(settings.value('audio_normalize', False, type=bool))
        self.normalize.setToolTip('Cible crête −3 dBFS, gain limité entre ×0,5 et ×2. Aucun débruitage.')
        form.addRow(self.normalize)
        self.threshold = QDoubleSpinBox()
        self.threshold.setRange(.1, .9)
        self.threshold.setSingleStep(.05)
        self.threshold.setValue(settings.value('vad_threshold', .5, type=float))
        form.addRow('Seuil de parole VAD', self.threshold)
        self.silence = QSpinBox()
        self.silence.setRange(100, 2000)
        self.silence.setSingleStep(100)
        self.silence.setSuffix(' ms')
        self.silence.setValue(settings.value('vad_min_silence', 500, type=int))
        form.addRow('Silence entre zones', self.silence)
        hint = QLabel('Le nouveau parcours conserve audio, VAD et voix séparément. '
                      'Comparez les deux parcours sur la même réunion avant de choisir. '
                      'Transcrire uniquement utilise toujours le parcours classique.')
        hint.setWordWrap(True)
        form.addRow(hint)
        self.mode.currentIndexChanged.connect(self.update_mode)
        self.update_mode()

    def update_mode(self):
        enabled = self.mode.currentData() == 'audio_first_v1'
        for field in (self.normalize, self.threshold, self.silence):
            field.setEnabled(enabled)

    def values(self):
        result = PreparationOptions(self.normalize.isChecked(), self.threshold.value(),
                                    self.silence.value()).validate()
        self.settings.setValue('pipeline_mode', self.mode.currentData())
        self.settings.setValue('audio_normalize', result.normalize)
        self.settings.setValue('vad_threshold', result.vad_threshold)
        self.settings.setValue('vad_min_silence', result.min_silence_ms)
        return result
