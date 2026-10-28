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

