# MAJIMeeting 0.2.12 — canal Windows DEV sans compilation

- Nouveau canal source : environnement Python permanent, mises à jour par commit validé et retour à la version précédente.
- Données et paramètres DEV isolés, copie explicite des réunions habituelles avec leurs audios, modèles existants réutilisés.
- Raccourcis pour lancer, mettre à jour et lancer, revenir en arrière et copier les réunions.
- Paquet d'installation DEV séparé dans les releases `dev-<commit>` ; Python3.11x64 requis. Voir docs/DEV_CHANNEL.md.
- Les changements courants de code ne reconstruisent plus l'EXE. Ce premier jalon conserve une construction complète pour valider la coexistence.

La transcription et la diarisation0.2.11 sont conservées. Les contrôles automatiques ne remplacent pas l'essai CUDA et WASAPI du nouveau canal sur votre PC. Le changement de distribution n'accélère pas les modèles IA.
