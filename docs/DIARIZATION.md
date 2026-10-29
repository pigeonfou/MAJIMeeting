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
3. Dans **Distinguer automatiquement les interlocuteurs**, choisir CPU ou CUDA puis
   cliquer **Télécharger et installer les dépendances**. La progression et les messages
   d'installation sont affichés dans cette fenêtre. Le modèle n'est pas retéléchargé.
   L'installation s'effectue dans le runtime utilisateur géré ; son Python est sélectionné
   automatiquement après réussite. Python 3.11 x64 avec le lanceur `py` reste un prérequis.
4. Cliquer **Télécharger le modèle Community-1** et saisir le jeton dans le champ masqué.
   Le téléchargement est indépendant du runtime, reprend les transferts partiels et
   vérifie les fichiers par taille/empreinte à une révision fixe du dépôt. Le jeton n'est
   enregistré ni en paramètres ni en journal. Les erreurs 401/403 indiquent de vérifier
   les conditions d'accès et le jeton. Les fichiers déjà présents et vérifiés sont réutilisés.
5. Chemins par défaut : `%LOCALAPPDATA%\MAJIMeeting\runtime\Scripts\python.exe` et
   `%LOCALAPPDATA%\MAJIMeeting\models\community-1`. Un modèle téléchargé manuellement
   peut toujours être sélectionné sans utiliser le bouton de téléchargement.

Pendant une préparation, les chemins et le lancement de l'analyse sont désactivés.
Le bouton d'annulation interrompt l'installation et ses processus enfants ; le téléchargement
peut attendre la fin de la requête réseau en cours (délais de connexion/lecture bornés).
Fermer la fenêtre demande l'arrêt avant fermeture. Une annulation conserve les téléchargements
partiels pour reprise ; relancer l'installation répare le runtime incomplet.
Le raccourci historique du menu Démarrer et le script restent disponibles en alternative.

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
