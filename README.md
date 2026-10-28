# MAJIMeeting

Application Windows locale de capture, transcription multi-interlocuteurs et rédaction de comptes rendus de réunion.

## Objectifs
- Enregistrement microphone et audio système (WASAPI loopback), avec sauvegarde fiable.
- Transcription différée par faster-whisper (Whisper large-v3).
- Diarisation locale par pyannote.audio, attribution et correction des locuteurs.
- Génération de comptes rendus par modèle GGUF local (Qwen3-8B, llama.cpp).
- Traçabilité des décisions vers les passages horodatés.
- Export PDF, DOCX, Markdown et TXT.

**Statut :** amorçage du projet. Aucune release Windows validée à ce stade.

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
