"""Task-oriented layout, independent of recording and inference workers."""
from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QComboBox,
    QDockWidget,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)


def scroll(widget):
    area = QScrollArea()
    area.setWidgetResizable(True)
    area.setFrameShape(QScrollArea.Shape.NoFrame)
    area.setWidget(widget)
    return area


def page(title, description):
    widget = QWidget()
    layout = QVBoxLayout(widget)
    layout.setContentsMargins(20, 16, 20, 16)
    layout.setSpacing(10)
    heading = QLabel(title)
    font = heading.font()
    font.setPointSize(font.pointSize() + 5)
    font.setBold(True)
    heading.setFont(font)
    layout.addWidget(heading)
    hint = QLabel(description)
    hint.setWordWrap(True)
    layout.addWidget(hint)
    return widget, layout


def row(layout, *widgets):
    controls = QHBoxLayout()
    for widget in widgets:
        controls.addWidget(widget)
    controls.addStretch()
    layout.addLayout(controls)


def section(layout, title, fields):
    group = QGroupBox(title)
    form = QFormLayout(group)
    form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
    form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
    for label, widget in fields:
        if label:
            form.addRow(label, widget)
        else:
            form.addRow(widget)
    layout.addWidget(group)
    return group


def build_processing(panel):
    layout = QVBoxLayout(panel)
    layout.setContentsMargins(20, 16, 20, 16)
    layout.setSpacing(10)
    panel.selection.setWordWrap(True)
    layout.addWidget(panel.selection)
    panel.full_analysis.setText('Transcrire et identifier les intervenants…')
    panel.full_analysis.setDefault(True)
    row(layout, panel.full_analysis)
    layout.addWidget(QLabel('Les modèles et les réglages GPU sont accessibles dans Paramètres.'))
    layout.addWidget(QLabel('Transcription sauvegardée'))
    layout.addWidget(panel.jobs)
    panel.result_tabs = QTabWidget()
    layout.addWidget(panel.result_tabs, 1)
    transcript, content = page('Transcription', 'Consultez le texte ou ouvrez l’éditeur pour corriger et réécouter.')
    panel.text.setMinimumHeight(180)
    content.addWidget(panel.text, 1)
    panel.edit_button.setText('Corriger et réécouter…')
    panel.export_button.setText('Exporter le texte…')
    row(content, panel.edit_button, panel.export_button)
    panel.result_tabs.addTab(transcript, 'Texte')
    speakers, content = page('Intervenants', 'Écoutez quelques extraits pour nommer les groupes de voix. '
                             'Les passages ambigus restent à vérifier dans l’éditeur.')
    panel.speaker_button.setText('Nommer les intervenants par extraits…')
    content.addWidget(panel.speaker_button)
    panel.diarize_button.setText('Réessayer la diarisation…')
    section(content, 'Analyses conservées', [
        ('Analyse', panel.analyses), ('', panel.use_analysis),
        ('', panel.diarize_button)])
    content.addWidget(panel.analysis_details)
    content.addStretch()
    panel.result_tabs.addTab(scroll(speakers), 'Intervenants')
    diagnostics, content = page('Historique du calcul', 'Informations sur la transcription sélectionnée ci-dessus.')
    content.addWidget(panel.execution)
    content.addWidget(panel.performance)
    content.addWidget(panel.warnings_button)
    content.addStretch()
    panel.result_tabs.addTab(scroll(diagnostics), 'Diagnostic')

    # Model installation and performance controls no longer occupy the reading area.
    panel.settings_page, settings = page('Paramètres', 'Ces réglages sont réutilisés pour les prochains traitements.')
    section(settings, 'Modèle de transcription', [
        ('Dossier local', panel.model), ('', panel.browse), ('', panel.download)])
    section(settings, 'Calcul et qualité', [
        ('Processeur', panel.device), ('Précision', panel.compute),
        ('Recherche', panel.quality), ('', panel.batched),
        ('Taille des lots', panel.batch_size), ('', panel.cpu_fallback)])
    advanced = section(settings, 'Réglages GPU avancés', [
        ('', panel.flash), ('Workers', panel.workers), ('Fenêtres audio', panel.audio_window),
        ('Dossier CUDA / cuDNN', panel.cuda_path), ('', panel.cuda_browse)])
    advanced.setToolTip('Réglages expérimentaux : comparez les résultats avant de les conserver.')
    panel.prepare_speakers = QPushButton(
        'Préparer Community-1…')
    panel.prepare_speakers.clicked.connect(panel.prepare_diarization)
    section(settings, 'Modèle des intervenants', [('', panel.prepare_speakers)])
    section(settings, 'Transcription seule', [('', panel.transcribe_button)])
    for combo in panel.findChildren(QComboBox) + panel.settings_page.findChildren(QComboBox):
        combo.setMinimumContentsLength(18)
        combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        combo.currentTextChanged.connect(combo.setToolTip)
        combo.setToolTip(combo.currentText())
    settings.addStretch()


def build_workspace(window, recording):
    panel = window.processing
    tabs = QTabWidget()
    tabs.setDocumentMode(True)
    tabs.addTab(recording, 'Enregistrer')
    tabs.addTab(panel, 'Transcription et intervenants')
    settings_layout = panel.settings_page.layout()
    settings_layout.takeAt(settings_layout.count() - 1)
    section(settings_layout, 'Apparence', [('', window.dark)])
    settings_layout.addStretch()
    tabs.addTab(scroll(panel.settings_page), 'Paramètres')
    window.setCentralWidget(tabs)

    library = QWidget()
    layout = QVBoxLayout(library)
    window.meeting_search = QLineEdit()
    window.meeting_search.setPlaceholderText('Rechercher une réunion…')
    window.meeting_search.setClearButtonEnabled(True)
    window.meeting_search.textChanged.connect(window.filter_meetings)
    layout.addWidget(window.meeting_search)
    layout.addWidget(window.meetings, 1)
    window.meetings.itemClicked.connect(lambda *_: tabs.setCurrentIndex(1))
    panel.import_button.setText('Importer de l’audio…')
    panel.open_saved.setText('Ouvrir une transcription…')
    layout.addWidget(panel.import_button)
    layout.addWidget(panel.open_saved)
    layout.addWidget(window.export_button)
    window.library_dock = QDockWidget('Mes réunions', window)
    window.library_dock.setFeatures(QDockWidget.DockWidgetFeature.NoDockWidgetFeatures)
    window.library_dock.setWidget(library)
    window.library_dock.setMinimumWidth(260)
    window.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, window.library_dock)
    window.resizeDocks([window.library_dock], [310], Qt.Orientation.Horizontal)

    # Progress and cancellation stay visible on every page, including model downloads.
    progress = QWidget()
    progress_layout = QHBoxLayout(progress)
    progress_layout.setContentsMargins(4, 0, 4, 0)
    progress_layout.addWidget(panel.download_status, 1)
    panel.progress_bar.setMaximumWidth(160)
    progress_layout.addWidget(panel.progress_bar)
    panel.cancel_button.setText('Annuler le traitement')
    panel.cancel_button.setToolTip('L’annulation attend la fin du segment en cours.')
    progress_layout.addWidget(panel.cancel_button)
    window.progress_dock = QDockWidget('Traitement', window)
    window.progress_dock.setFeatures(QDockWidget.DockWidgetFeature.NoDockWidgetFeatures)
    window.progress_dock.setWidget(progress)
    window.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, window.progress_dock)

    window.command_actions = []
    def command(menu, label, button, shortcut=None, destination=None):
        action = QAction(label, window)
        if shortcut:
            action.setShortcut(shortcut)
        def trigger():
            if button.isEnabled():
                if destination is not None:
                    tabs.setCurrentIndex(destination)
                button.click()
        action.triggered.connect(trigger)
        menu.addAction(action)
        window.command_actions.append((action, button))
        return action

    file_menu = window.menuBar().addMenu('&Fichier')
    command(file_menu, 'Importer de l’audio…', panel.import_button, 'Ctrl+I', 1)
    command(file_menu, 'Ouvrir une transcription…', panel.open_saved, 'Ctrl+O', 1)
    file_menu.addSeparator()
    command(file_menu, 'Exporter une piste WAV…', window.export_button)
    command(file_menu, 'Exporter la transcription…', panel.export_button)
    file_menu.addSeparator()
    quit_action = file_menu.addAction('Quitter')
    quit_action.setShortcut('Ctrl+Q')
    quit_action.triggered.connect(window.close)
    record_menu = window.menuBar().addMenu('&Enregistrement')
    command(record_menu, 'Actualiser les sources', window.refresh)
    command(record_menu, 'Démarrer', window.start_button, destination=0)
    command(record_menu, 'Arrêter et sauvegarder', window.stop_button)
    analysis_menu = window.menuBar().addMenu('&Analyse')
    command(analysis_menu, 'Transcrire et identifier…', panel.full_analysis, destination=1)
    command(analysis_menu, 'Nommer les intervenants…', panel.speaker_button, destination=1)
    command(analysis_menu, 'Corriger et réécouter…', panel.edit_button, destination=1)
    command(analysis_menu, 'Relancer la diarisation…', panel.diarize_button, destination=1)
    view_menu = window.menuBar().addMenu('&Affichage')
    for index, title in enumerate(('Enregistrer', 'Transcription et intervenants', 'Paramètres')):
        action = view_menu.addAction(title)
        action.setShortcut(f'Ctrl+{index + 1}')
        action.triggered.connect(lambda checked=False, i=index: tabs.setCurrentIndex(i))
    for menu in (file_menu, record_menu, analysis_menu):
        menu.aboutToShow.connect(window.sync_commands)
    window.sync_commands()
