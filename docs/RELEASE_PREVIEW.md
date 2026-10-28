# MAJIMeeting — préversion du jalon 2

Installateur Windows x64, sans droits administrateur. Conserve les réunions existantes.

Nouveautés : import WAV/MP3/FLAC/M4A, transcription française locale faster-whisper,
choix CPU/CUDA et quantification, gestion du modèle large-v3, progression/annulation,
historique persistant des transcriptions et export TXT/JSON horodaté.

Le modèle large-v3 est téléchargé séparément depuis l'application (~3 Go).
Les bibliothèques CUDA/cuDNN ne sont pas incluses ; CPU/int8 fonctionne sans NVIDIA.
Après installation du modèle, les traitements sont locaux et sans téléchargement implicite.

La capture microphone/loopback, l'export séparé et la récupération après arrêt forcé ont
été confirmés par l'utilisateur sur la préversion du jalon 1. Les essais complémentaires
(débranchement, longue durée/dérive, hors réseau, désinstallation) restent à réaliser.

Contrôles automatisés : tests Windows/Linux, Ruff, démarrage Qt, inférence CPU avec un
petit modèle de test, construction/installation et inférence du programme installé.
Ces contrôles ne valident pas la qualité française de large-v3 ni CUDA sur votre RTX.

Préversion sans signature de code. Diarisation, correction synchronisée et comptes rendus
ne sont pas encore intégrés. Voir docs/TRANSCRIPTION.md et docs/PROGRESS.md.
