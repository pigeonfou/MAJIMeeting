# MAJIMeeting

Application Windows locale de capture, transcription multi-interlocuteurs et rédaction de comptes rendus de réunion.

## Objectifs
- Enregistrement microphone et audio système (WASAPI loopback), avec sauvegarde fiable.
- Transcription différée par faster-whisper (Whisper large-v3).
- Diarisation locale par pyannote.audio, attribution et correction des locuteurs.
- Génération de comptes rendus par modèle GGUF local (Qwen3-8B, llama.cpp).
- Traçabilité des décisions vers les passages horodatés.
- Export PDF, DOCX, Markdown et TXT.

**Statut :** jalon 2 en validation. Capture partiellement validée sur matériel et transcription locale intégrée ; aucune release stable validée.

## Développement
Python 3.11+, PySide6, SQLite. Installation de développement :
```powershell
py -3.11 -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
python -m majimeeting
```
Le téléchargement des modèles et les dépendances CUDA seront intégrés aux jalons ultérieurs.

Voir [l'architecture](docs/ARCHITECTURE.md) et [la feuille de route](docs/ROADMAP.md).


## Prototype d'enregistrement (jalon 1)
Sous Windows, sélectionnez une ou plusieurs sources WASAPI, donnez un titre à la réunion
et démarrez. Les microphones et sorties système loopback restent sur des pistes séparées.
Arrêtez avant de fermer l'application. L'historique permet d'exporter une piste en WAV.
Les réunions interrompues sont repérées au redémarrage et leurs fragments finalisés restent
exportables. Les données sont dans `%LOCALAPPDATA%\MAJIMeeting\data`.

La CI construit un installateur Windows de préversion et vérifie son installation et son
démarrage. Il est fourni comme artefact de workflow ; cela ne valide pas les périphériques
physiques. Les modèles sont téléchargés séparément depuis l'onglet de transcription. L'application fonctionne localement.

Voir [la progression](docs/PROGRESS.md) et [les essais Windows](docs/WINDOWS_TESTS.md).

## Transcription locale (jalon 2)
L'onglet **Import et transcription** permet d'importer un WAV/MP3/FLAC/M4A ou de transcrire
une réunion enregistrée. Choisir un modèle local faster-whisper (ou télécharger large-v3
avec le bouton dédié), puis CPU/int8 ou CUDA si les bibliothèques NVIDIA sont installées.
La transcription française est horodatée, persistante, consultable et exportable TXT/JSON.
Voir [le guide de transcription](docs/TRANSCRIPTION.md) pour les essais et limites.
