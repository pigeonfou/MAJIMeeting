# Séparer des voix confondues avec quelques références

Cette fonction expérimentale propose des attributions à partir d’exemples que vous
nommez. Elle réutilise le modèle d’empreintes local de Community-1 ; elle ne réentraîne
pas le modèle et ne redécode pas la transcription avec Whisper. Elle peut aider quand
le regroupement automatique mélange des personnes, sans garantir leur distinction.

## Parcours conseillé

1. Ouvrir la transcription et son analyse des voix. Dans **Intervenants**, cliquer sur
   **Séparer des voix confondues avec des extraits de référence…**. Depuis l’éditeur,
   sélectionner un passage puis utiliser le bouton équivalent : piste, groupe et début
   du passage sont présélectionnés.
2. Choisir explicitement le **groupe mélangé** à corriger. **Toute la piste** concerne
   toutes ses voix et nécessite des références représentant ses différents intervenants.
   Une voix absente des références peut être confondue avec une voix représentée,
   même si son score paraît élevé : privilégier une cible précise.
3. Dans **Références**, sélectionner un passage, ajuster Début/Fin, écouter ces bornes,
   saisir le nom et confirmer qu’une seule personne parle. Ajouter la référence.
   Choisir des extraits de **3 à 20 secondes**, sans autre voix ni musique, idéalement
   **deux ou trois extraits différents par personne**. Au moins deux personnes distinctes
   sont nécessaires sur la piste choisie ; les références ne traversent pas les pistes.
4. Vérifier le modèle/runtime Community-1 existants et CPU/CUDA. Dans **Comparer et
   appliquer**, conserver pour commencer le cosinus minimal **0,65**, l’écart **0,08**
   et le contexte **3 secondes**, puis calculer les propositions.
5. Lire le résumé et les avertissements. Double-cliquer quelques propositions pour
   écouter leur début ; décocher les attributions douteuses. Les scores sont des
   **similarités cosinus, pas des probabilités ni des taux de précision**.
6. Cliquer **Appliquer les propositions retenues**. Une nouvelle analyse est sélectionnée.
   L’ancienne reste accessible dans l’historique habituel : sélectionner son résultat
   puis **Revenir au résultat de cette analyse** pour restaurer ses attributions.

L’aperçu ne modifie aucune attribution. L’application porte sur toutes les propositions
retenues, y compris au-delà des 1000 premières lignes affichées ; le résumé indique
les comptes complets. **Tout laisser à vérifier** les décoche toutes.
Les passages ciblés incertains ou décochés deviennent « à vérifier » dans la nouvelle
analyse. Les groupes non ciblés, les pistes non ciblées et les corrections humaines
restent conservés. Un segment contenant une correction individuelle est protégé en
entier, pour ne pas répartir arbitrairement son texte corrigé entre plusieurs personnes.

## Comparaison et limites

Les extraits confirmés servent à former des références moyennes normalisées par nom.
L’application compare les fenêtres audio autour des mots à ces références. Une
proposition automatique nécessite une similarité minimale, un écart suffisant avec
la seconde personne et un accord de fenêtres voisines. Les références presque
identiques empêchent la propagation hors des extraits confirmés. Les avertissements
signalent aussi des exemples peu cohérents ou des références proches.

Le modèle ne devient pas plus discriminant par simple ajout d’un nom. Si ses empreintes
ne distinguent pas les deux personnes, le résultat doit rester incertain. Choisir de
meilleurs extraits, ou comparer ultérieurement un autre modèle d’empreintes, sera alors
nécessaire. Abaisser les seuils peut augmenter les erreurs ; ne changer qu’un réglage
à la fois après écoute de quelques exemples connus.

Les fenêtres ne traversent pas les chevauchements déjà détectés. Les mots effectivement
simultanés restent signalés ; cette fonction ne sépare pas acoustiquement deux voix.
Les chevauchements manqués par le modèle peuvent encore contaminer les références ou
les propositions. Les paroles très courtes et les changements de voix restent difficiles.

Les mots doivent déjà posséder des horodatages fiables pour découper une phrase mélangée.
Les passages sans mots horodatés restent inchangés et sont signalés. Une analyse des voix
avec alignement du texte existant peut les préparer sans redécodage Whisper ; la correction
guidée elle-même ne lance aucun alignement ou modèle Whisper.

## Réutilisation, sécurité des résultats et audit

- Références enregistrées localement par transcription et par piste, sans identification
  automatique entre réunions. Les bornes et noms restent modifiables en retirant un
  exemple des essais futurs puis en ajoutant sa nouvelle version.
- Empreintes de références et de passages mises en cache séparément dans le dossier de
  la réunion. Ajuster les seuils ne recharge pas le modèle ; ajouter une référence peut
  réutiliser les empreintes des passages. La vérification des fichiers consomme encore
  du disque, même si le calcul du modèle est réutilisé.
- Extraction dans le runtime pyannote isolé, sur CPU ou CUDA ; aucun modèle Whisper
  chargé. Le périphérique effectif et le pic mémoire CUDA sont conservés dans l’analyse.
- Aperçu lié au texte, aux références, aux corrections, à l’analyse active et aux sources
  audio. Si ces éléments changent avant l’application, recalculer l’aperçu est obligatoire.
- Application atomique SQLite : nouvelles pièces dérivées et nouvelle sélection d’analyse,
  sans réécriture des originaux ni des textes. Annuler avant validation laisse l’analyse
  précédente active. Les résultats historiques restent conservés.
- Export JSON enrichi : références, propositions, scores, incertitudes et choix appliqués.
  Les vecteurs biométriques bruts ne sont pas inclus dans cet export.
- Retirer une référence ne supprime pas les analyses ni les caches historiques. Les
  copies DEV et sauvegardes existantes restent indépendantes de l’original.

Limites de cette version : une piste par aperçu, 60 références par transcription,
2 à 20 noms par piste, 20000 fenêtres au maximum (cibler un groupe plus étroit si besoin),
et quatre heures par piste comme la préparation audio existante.

## Validation

Les tests automatiques utilisent des empreintes simulées pour vérifier le contrat,
la séparation des attributions, la conservation du texte, les corrections, les caches,
les aperçus obsolètes, les chevauchements, l’annulation et le retour à une ancienne analyse.
Ils exécutent aussi le code du worker avec un modèle simulé pour vérifier les formes,
le classement des fenêtres et les contrôles CPU/CUDA. Cela ne valide ni la précision des
voix réelles ni l’inférence du checkpoint Community-1 sur GPU : ces essais nécessitent
le modèle déjà installé et les réunions du PC utilisateur.

La télémétrie ONNX est désactivée explicitement avant les sessions VAD. Les vérifications
CI s’exécutent avec les accès Internet du processus bloqués au niveau système, indépendamment
des paramètres de télémétrie : filtre seccomp sous Linux, règles temporaires du pare-feu
sur les runners Windows. L’installation des bibliothèques et le téléchargement explicite
du petit modèle d’intégration restent des étapes connectées distinctes. Ces règles CI
ne modifient pas le pare-feu du PC utilisateur.
