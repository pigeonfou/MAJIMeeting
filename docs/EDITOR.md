# Correction et réécoute — préversion 0.2.4

Après une transcription, sélectionner la réunion puis une tentative dans l'historique.
Cliquer sur **Corriger les textes, nommer les intervenants et réécouter…**.

- Sélectionner une ligne, corriger son texte et saisir un nom, puis **Enregistrer la correction**.
- Le nom concerne ce passage uniquement. Une piste est une source audio ; elle ne permet
  pas d'identifier automatiquement une personne. La diarisation automatique reste à intégrer.
- Un nom vide signifie « Inconnu ». Les noms sont des attributions humaines.
- Le texte original, les temps et la piste ne sont jamais réécrits. Chaque correction
  ajoute une entrée datée à l'historique SQLite, visible sous l'éditeur.
- **Rétablir le texte original et retirer le nom** ajoute une nouvelle révision ; les
  corrections précédentes restent consultables.
- Les modifications saisies doivent être enregistrées avant de changer de ligne ou fermer.
- Une tentative terminée, interrompue, annulée ou en échec peut être corrigée ; une nouvelle
  transcription crée une autre tentative et ne reprend pas ces corrections automatiquement.

## Réécoute locale

Double-cliquer sur une ligne ou utiliser **Écouter ce passage**. Le lecteur utilise la
piste originale correspondant au segment et les horodatages des fragments. Les trous
entre fragments deviennent du silence ; les fichiers absents ne sont pas reconstitués.
La préparation fonctionne dans un worker indépendant de Qt ; aucun modèle IA n'est chargé.
Le bouton Arrêter empêche aussi le démarrage différé d'un extrait encore en préparation.

La lecture est limitée aux 60 premières secondes de chaque segment. Les fragments sont
parcourus pour créer uniquement cet extrait temporaire, sans WAV de réunion complète.
La fermeture attend la fin de sa préparation ; l'extrait est supprimé à la fermeture
normale du dialogue. Après un arrêt forcé, un fichier temporaire peut subsister dans
le dossier temporaire Windows. Les horloges des sources restent approximatives, sans
correction de dérive ; cela ne change pas les limites de la capture initiale.

## Exports

TXT utilise les textes corrigés et les noms. JSON utilise les champs `text` corrigé,
`original_text`, `speaker`, les temps et l'identifiant d'origine. L'historique complet
reste dans la base SQLite. Les avertissements d'horodatage restent séparés et accessibles.
Ces exports ne constituent pas une sauvegarde complète de la réunion et de ses fichiers.

## Vérification

`python -m majimeeting --editor-smoke` teste l'éditeur et la persistance puis décode
un extrait WAV avec Qt Multimedia, sans périphérique audio physique. Le workflow Windows
exécute ce contrôle depuis l'application installée. Cela ne garantit pas que le son
est audible dans le casque de l'utilisateur : l'écoute réelle reste à vérifier.
