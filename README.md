# MAJIMeeting

Application Windows locale de capture, transcription multi-interlocuteurs et rédaction de comptes rendus de réunion.

## Objectifs
- Enregistrement microphone et audio système (WASAPI loopback), avec sauvegarde fiable.
- Transcription différée par faster-whisper (Whisper large-v3).
- Diarisation locale par pyannote.audio, attribution et correction des locuteurs.
- Génération de comptes rendus par modèle GGUF local (Qwen3-8B, llama.cpp).
- Traçabilité des décisions vers les passages horodatés.
- Export PDF, DOCX, Markdown et TXT.

**Statut :** jalon 2 en validation utilisateur, première partie du jalon 3 intégrée.
Capture partiellement validée sur matériel, transcription locale, corrections et réécoute
disponibles ; aucune release stable validée.

## Développement
Python 3.11+, PySide6, SQLite. Installation de développement :
```powershell
py -3.11 -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
python -m majimeeting
```
Le téléchargement explicite de large-v3 est intégré. Pour CUDA, installer séparément
les bibliothèques NVIDIA décrites dans [le guide Windows](docs/CUDA_WINDOWS.md).

Voir [l'architecture](docs/ARCHITECTURE.md) et [la feuille de route](docs/ROADMAP.md).


## Prototype d'enregistrement (jalon 1)
Sous Windows, sélectionnez une ou plusieurs sources WASAPI, donnez un titre à la réunion
et démarrez. Les microphones et sorties système loopback restent sur des pistes séparées.
Arrêtez avant de fermer l'application. L'historique permet d'exporter une piste en WAV.
Les réunions interrompues sont repérées au redémarrage et leurs fragments finalisés restent
exportables. Les données sont dans `%LOCALAPPDATA%\MAJIMeeting\data`.

La CI construit un installateur Windows de préversion et vérifie son installation et son
démarrage. Il est fourni comme artefact de workflow ; cela ne valide pas les périphériques
physiques. Les modèles sont téléchargés séparément depuis Paramètres. L'application fonctionne localement.

Voir [la progression](docs/PROGRESS.md) et [les essais Windows](docs/WINDOWS_TESTS.md).

## Transcription locale (jalon 2)
La colonne **Mes réunions** permet d’importer un WAV/MP3/FLAC/M4A ou d’ouvrir une réunion
enregistrée. Dans **Paramètres**, choisir un modèle faster-whisper local (ou télécharger
large-v3), puis CPU/int8 ou CUDA si les bibliothèques NVIDIA sont installées. Lancer le
traitement depuis **Transcription et intervenants**.
La transcription française est horodatée, persistante, consultable et exportable TXT/JSON.
Voir [le guide de transcription](docs/TRANSCRIPTION.md) pour les essais et limites.

La préversion 0.2.4 ajoute [les corrections et la réécoute](docs/EDITOR.md), avec
attribution manuelle des noms et historique. La diarisation automatique Community-1 est disponible en préversion, avec réglages,
historique et nomination par courts extraits ; sa qualité reste à valider sur les réunions réelles.

La préversion 0.2.5 ajoute le [traitement par lots GPU et les mesures de vitesse](docs/PERFORMANCE.md).
Les profils Qualité/Rapide et le chemin séquentiel sont proposés pour comparer la même réunion.

La préversion 0.2.6 propose [des essais GPU avancés](docs/GPU_EXPERIMENTS.md) : Flash Attention,
deux workers partageant le modèle, fenêtres de dix minutes et mesure du remplissage réel.
Ces options expérimentales sont à comparer séparément sur le PC utilisateur.


## Canal Windows DEV sans compilation

Pour les essais fréquents, le canal DEV exécute les sources dans un environnement Python permanent. Il dispose de données et réglages séparés, de mises à jour vérifiées et d'un retour à la version précédente. Aucun Git ni terminal nécessaire après l'installation initiale. Les modèles locaux existants sont réutilisables.

Télécharger `MAJIMeeting-DEV-Setup.zip` dans une release **MAJIMeeting DEV**, extraire puis lancer `Installer-DEV.cmd`. Voir [Installation et fonctionnement du canal DEV](docs/DEV_CHANNEL.md). Les installateurs classiques restent disponibles pour les versions de distribution.


## Interface organisée par tâche

**Mes réunions** reste visible à gauche, avec recherche et réouverture sans recalcul.
Trois espaces : **Enregistrer**, **Transcription et intervenants**, **Paramètres**.
Les résultats sont répartis en **Texte**, **Intervenants** et **Diagnostic** ; progression
et annulation restent visibles partout. Voir [le guide de l’interface](docs/INTERFACE.md).
Les changements d’interface sont distribués par le canal DEV.
