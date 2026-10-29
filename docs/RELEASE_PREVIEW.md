# MAJIMeeting 0.2.11 — découpage aux voix et nomination rapide

- Parcours « Transcrire et proposer les intervenants » : transcription mot à mot, diarisation puis nomination des groupes avec de courts extraits.
- Découpage du texte lorsque les voix se succèdent dans un même segment. Les paroles simultanées restent signalées avec les groupes possibles.
- Jusqu'à trois extraits isolés par groupe, 12 secondes maximum ; noms appliqués à tous les passages correspondants et filtre des passages à vérifier.
- Réutilisation d'une transcription existante : alignement du texte original sans le redécoder, puis conservation des mots pour les essais suivants.
- Originaux et historique conservés, corrections protégées et export JSON enrichi.

Installer par-dessus0.2.10. Aucun nouveau modèle nécessaire ; Whisper et Community-1 locaux restent requis. Pour une ancienne transcription, rouvrir puis relancer la diarisation avec le modèle Whisper sélectionné. L'alignement mot à mot ajoute du calcul. Les voix simultanées et les erreurs de regroupement ne sont pas résolues avec certitude ; qualité et performances sur vos réunions restent à vérifier.
