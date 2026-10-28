# MAJIMeeting 0.2.5 — transcription GPU par lots

- Traitement par lots GPU, taille 8 proposée, pour mieux alimenter la carte NVIDIA.
- Profil Qualité (beam 5, réglage conservé) ou Rapide (beam 1, qualité à comparer).
- Réduction automatique des lots si la VRAM manque, avant tentative CUDA séquentielle
  puis éventuel repli CPU si autorisé.
- Horodatages, audit, résultats et corrections des tentatives précédentes conservés.
- Mesures : durée totale, chargement, préparation, inférence/VAD et écriture ; mode effectif,
  taille et vitesse globale affichés dans l'historique et exportés en JSON.
- Quantification, taille de lot et profil mémorisés entre les sessions.

Installer par-dessus la version précédente. Dans Import et transcription, choisir CUDA,
cocher Traitement par lots sur GPU, taille 8 et conserver d'abord Qualité. Comparer la
même réunion, puis essayer Rapide ou float16 séparément. Aucun nouveau modèle nécessaire.

Les intégrations 0.2.4 ont été validées par l'utilisateur. La diarisation automatique reste
à intégrer. Les tests utilisent des poids tiny réels sur CPU et des scénarios GPU simulés ;
le gain RTX/large-v3 et la qualité sur la réunion réelle restent à mesurer. Le traitement
par lots peut produire un texte différent du chemin séquentiel. Voir docs/PERFORMANCE.md.
