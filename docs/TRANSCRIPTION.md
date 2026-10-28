# Jalon 2 — import et transcription locale

Dans l'onglet **Enregistrement et réunions**, sélectionner une réunion existante.
Passer à **Import et transcription** ; le titre sélectionné est affiché en haut.
On peut aussi importer un WAV, MP3, FLAC ou M4A : une nouvelle réunion sera créée,
l'original conservé et la première piste audio décodée en fragments mono 16 kHz.
Les pistes enregistrées sont traitées séparément, sans mélange ni identification de personnes.

## Modèle et calcul

- Choisir un dossier de modèle **faster-whisper/CTranslate2**, avec au minimum model.bin,
  config.json et tokenizer.json. Un modèle GGUF ne convient pas à ce moteur.
- Ou utiliser **Télécharger large-v3** : connexion nécessaire pour les poids (~3 Go),
  aucun contenu de réunion envoyé. Le dossier proposé se trouve sous
  `%LOCALAPPDATA%\MAJIMeeting\models\large-v3`.
- CPU/int8 est le réglage initial. CPU/float32, CUDA/int8_float16 et CUDA/float16 sont proposés.
- CUDA nécessite les bibliothèques NVIDIA compatibles avec CTranslate2 : CUDA 12/cuBLAS
  et cuDNN 9 pour la branche actuelle. Elles ne sont pas fournies dans cette préversion.
  En cas d'erreur CUDA, choisir CPU/int8 et relancer ; aucun résultat précédent n'est écrasé.
- Après installation du modèle, la transcription utilise le dossier local avec
  `local_files_only=True`. Aucun téléchargement de modèle pendant la transcription.

## Traitement et résultats

Cliquer sur **Transcrire la réunion sélectionnée en français**. Le traitement est différé,
indépendant de la capture et effectué dans un worker. Un seul modèle est chargé à la fois,
puis libéré. La capture est indisponible pendant ce traitement dans cette version.
Les fichiers sont traités par lots de cinq minutes pour borner la mémoire de décodage.
Les frontières entre lots sont sans recouvrement : qualité à vérifier sur réunion longue.

Les segments sont enregistrés dans SQLite au fil de leur production, avec piste et temps
de début/fin. La barre d'état affiche la progression. Le bouton Annuler est coopératif :
le chargement du modèle ou le segment en cours doit se terminer avant son application.
La fermeture est bloquée tant que le worker est actif. Après un arrêt forcé, un traitement
inachevé est signalé `interrupted`, ses segments déjà écrits restent consultables.

L'historique conserve toutes les tentatives, y compris partielles et en erreur.
La transcription peut être exportée en TXT ou JSON. Les noms de piste ne sont pas des
noms d'intervenants ; la diarisation et les corrections appartiennent au jalon 3.

## Essais à réaliser sur votre PC

1. Télécharger large-v3 dans l'application, puis couper le réseau.
2. Transcrire une des réunions déjà validées en CPU/int8 ; vérifier français, contenu,
   horodatages par rapport aux WAV et exports TXT/JSON.
3. Importer un fichier audio français et le transcrire sans réseau.
4. Annuler un traitement : les segments terminés doivent rester consultables.
5. Tester CUDA après installation des bibliothèques adaptées, relever durée et VRAM.
6. Tester une réunion dépassant cinq minutes ; contrôler les mots à la frontière des lots.

La CI utilise un petit modèle `tiny` pour une véritable inférence CPU, le VAD et le
chemin import/transcription sans réseau. Ce test ne mesure pas la qualité de large-v3,
la précision du français, la VRAM ni la compatibilité CUDA sur votre matériel.
