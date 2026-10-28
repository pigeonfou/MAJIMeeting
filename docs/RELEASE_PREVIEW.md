# MAJIMeeting 0.2.4 — correction, intervenants et réécoute

Première partie du jalon 3, ajoutée au socle Windows existant.

- Éditeur de transcription avec correction du texte par passage.
- Attribution manuelle du nom d'un intervenant, sans identification automatique.
- Texte original, horodatages et historique daté des corrections conservés.
- Restauration de l'original sous forme d'une nouvelle révision.
- Double-clic sur un passage pour réécouter sa piste audio, jusqu'à 60 secondes.
- Extrait préparé dans un worker ; décalages de piste et silences des fragments manquants
  conservés. Aucun modèle IA ni téléchargement pour la lecture ou les corrections.
- Exports TXT/JSON avec textes corrigés et noms ; texte original inclus dans le JSON.

Installer par-dessus la préversion précédente : réunions, modèles et réglages conservés.
Ouvrir une transcription puis « Corriger les textes, nommer les intervenants et réécouter… ».
Enregistrer chaque correction avant de changer de ligne.

La diarisation automatique pyannote, la génération de comptes rendus et les exports
PDF/DOCX restent à développer. La validation de la transcription complète large-v3 sur
la réunion utilisateur, l'écoute réelle Windows et les essais matériels précédemment
reportés restent à réaliser. Préversion, sans certification de qualité des transcriptions.
