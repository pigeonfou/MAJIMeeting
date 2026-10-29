# Interlocuteurs — première intégration Community-1 (0.2.7)

La transcription et ses optimisations restent disponibles. La diarisation est une phase
séparée déclenchée sur une transcription terminée. Elle ne déduit jamais les noms réels.

## Préparation sur Windows (une fois, avec connexion)

L'application normale ne contient pas PyTorch : son runtime est isolé pour conserver
le moteur Whisper existant et libérer la VRAM à la fin de chaque processus d'analyse.

1. Installer Python 3.11 x64 avec le lanceur `py` si absent.
2. Avec votre compte Hugging Face, accepter les conditions du modèle
   https://huggingface.co/pyannote/speaker-diarization-community-1 et créer un jeton de lecture.
   Aucun accès au compte n'est demandé à ChatGPT. L'acceptation reste personnelle.
3. Lancer le raccourci du menu Démarrer **Préparer la diarisation locale**. Le script
   `setup-diarization.ps1` crée un environnement utilisateur, installe PyTorch 2.8.0 CUDA 12.8,
   torchaudio 2.8.0, torchcodec 0.7.0 et pyannote.audio 4.0.7, puis demande le jeton sans
   l'afficher ni le sauvegarder et télécharge le modèle. Plusieurs Go sont nécessaires.
   Il teste ensuite le chargement local en mode Hub hors ligne.
   Pour une machine sans GPU, le script accepte `-Device cpu`.
4. Chemins par défaut : `%LOCALAPPDATA%\MAJIMeeting\runtime\Scripts\python.exe` et
   `%LOCALAPPDATA%\MAJIMeeting\models\community-1`.

Ce runtime utilisateur et les modèles persistent après mise à jour ou désinstallation
pour éviter de perdre les données. Ils peuvent être supprimés manuellement si inutiles.

## Analyse hors ligne

Sélectionner une transcription terminée puis **Distinguer automatiquement les interlocuteurs**.
Choisir le runtime et le dossier Community-1 local, CUDA ou CPU et éventuellement un nombre
connu de voix **par piste** (0 = automatique). Le worker série de l'application exclut
la capture et Whisper pendant cette tâche. Un sous-processus termine et libère Torch
après chaque piste. Annuler arrête le processus ; une analyse interrompue ou échouée ne
remplace jamais la dernière analyse terminée.

L'analyse bloque les connexions réseau du sous-processus et désactive les métriques
pyannote, OpenTelemetry et le Hub en ligne. Aucun téléchargement pendant une analyse.
Un modèle incomplet provoque une erreur explicite.

## Groupes et corrections

Chaque piste a son propre espace de groupes : `track-00:SPEAKER_00` n'est pas supposé
identique à `track-01:SPEAKER_00`. Dans l'éditeur, sélectionner un passage puis **Nommer tous
les passages du groupe sélectionné**. Le même nom peut être attribué explicitement à
plusieurs groupes après écoute. Les corrections individuelles restent prioritaires,
y compris le choix manuel de retirer un nom. Les noms successifs de groupe sont historisés.

Les tours pyannote sont conservés séparément du texte. On attribue un groupe seulement
si une unique voix couvre au moins la moitié du segment. Plusieurs voix, un changement
de voix ou une couverture faible donnent un passage « À vérifier ». Le texte n'est pas
coupé arbitrairement et ses temps d'origine ne changent pas. Les tours en chevauchement
restent dans l'export JSON avec l'historique des analyses et des noms.

## Limites et validation

- La première version limite une piste à 4 heures de chronologie pour borner le tenseur
  utilisé par Community-1. La préparation WAV mono 16 kHz est en streaming et conserve
  les trous en silence et l'origine absolue de la piste. Ne pas découper une piste en
  petits appels indépendants : les groupes n'y auraient pas une identité cohérente.
- Le groupe majoritaire n'est pas forcé sur les segments multi-voix. L'alignement mot à
  mot et la séparation fine du texte aux changements de voix restent à développer.
- Les tests automatiques vérifient persistance, reprises, processus annulable, PCM,
  horodatages, corrections et interface. Le job runtime Windows installe et importe les
  vraies bibliothèques CPU. Les poids Community-1 soumis à acceptation ne sont pas fournis
  à la CI : ne pas confondre ces contrôles avec un test de qualité de diarisation.
- À réaliser sur le PC cible : préparation CUDA/modèle, traitement d'une réunion connue
  avec 2–3 voix, chevauchements, silence et pistes mic/système, puis test sans connexion,
  renommage, correction individuelle, export JSON et interruption/reprise. Vérifier que
  les passages difficiles restent signalés ; relever durée, RAM et VRAM.

Sources primaires : fiche modèle Community-1 ci-dessus (usage local, waveform et sorties
régulières/exclusives), dépendances pyannote.audio 4.0.7 sur PyPI et télémétrie pyannote.audio.
