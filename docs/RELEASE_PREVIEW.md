# MAJIMeeting 0.2.10 — réglages de diarisation et transcriptions sauvegardées

- Ouvrir une transcription existante sans refaire Whisper ; recherche et dernière sélection retrouvée au démarrage.
- Nombre de voix exact ou bornes, réglages par piste, paramètres VBx, pauses, chevauchements et lots de diarisation.
- Historique des essais : réglages demandés/effectifs, groupes, passages ambigus, durée et retour à un résultat précédent.
- Diagnostic CPU/CUDA indépendant de Whisper : étape, périphériques des réseaux, GPU et mémoire Torch. Certaines phases restent CPU.
- Corrections individuelles conservées ; aucune identification certaine ou fusion automatique de personnes.

Installer par-dessus la version précédente. Aucun nouveau modèle à télécharger. La qualité et les performances sur la RTX utilisateur restent à vérifier ; les tests CPU et doublures ne valident pas le GPU réel.
