# Architecture — MAJIMeeting

## Principes
Application Windows native PySide6 ; modules Python découplés et workers hors thread UI.

1. **Capture** : WASAPI microphone/loopback ; pistes séparées ; écriture incrémentale avec récupération sur incident.
2. **Prétraitement** : VAD, segmentation et conservation des horodatages.
3. **Transcription** : faster-whisper / Whisper large-v3, CUDA, traitement différé ; résultats modifiables.
4. **Diarisation** : pyannote Community-1 local ; correspondance des locuteurs et correction humaine.
5. **Persistance** : SQLite pour réunions, segments, intervenants, tâches, provenance et versions ; audio en fichiers.
6. **Synthèse** : llama.cpp et Qwen3-8B GGUF, extraction JSON par blocs, consolidation, vérification de la provenance.
7. **Export** : PDF, DOCX, Markdown, TXT.

## Contraintes
- RTX 3080 Laptop 16 Go : charger les modèles successivement ; mesurer VRAM et prévoir repli CPU.
- Aucune transmission distante du contenu des réunions.
- Capture prioritaire et indépendante des traitements GPU.
- Le nom réel d'un locuteur ne se déduit pas de la seule diarisation.
- Les décisions et actions doivent référencer les segments source.
- Les enregistrements doivent être signalés aux participants conformément aux obligations applicables.

## Schéma logique initial
Meeting -> AudioTrack ; Meeting -> Speaker ; Meeting -> Segment (start/end/text/speaker) ; Meeting -> Report -> Evidence(segment_id).

## Décisions à valider par des essais
Compatibilité CUDA/CTranslate2/pyannote sur Windows ; consommation mémoire ; qualité WER/DER sur français technique ; capture simultanée microphone et loopback ; packaging PyInstaller.


## Implémentation des jalons 1 et 2

- `storage.py` : catalogue SQLite, jobs de transcription, segments horodatés et fragments WAV atomiques.
- `capture.py` : WASAPI, callbacks vers une file bornée et worker d'écriture indépendant de Qt.
- `transcription.py` : import PyAV en streaming, assemblage de lots audio bornés,
  chargement exclusif d'un modèle local et sauvegarde au fil des segments.
- `processing_ui.py` : import, choix du modèle/calcul, historique et exports de transcription.
- `selftest.py` : contrôle d'intégration CPU avec vrais poids, import et VAD sans accès au Hub.

Les tâches différées partagent un worker série ; aucun modèle n'est chargé pendant la
capture. La diarisation et la synthèse devront conserver cette exclusivité des modèles.
La base est enrichie par des créations de tables additives, sans suppression des réunions existantes.

## Éditeur et lecture locale

Les corrections résident dans une table SQLite additive `segment_edits` : segment source,
date, texte et nom attribué manuellement. La vue courante applique la dernière révision
sans réécrire le texte original ni les temps. Une nouvelle tentative de transcription
conserve son propre jeu de segments.

Qt Multimedia lit un extrait WAV temporaire préparé dans un worker dédié. Les positions
utilisent les métadonnées de chaque fragment, avec silence aux trous, sans assemblage
de la réunion complète. La durée de lecture est bornée à 60 secondes par passage.
Aucun modèle IA n’est chargé pour éditer ou lire.
