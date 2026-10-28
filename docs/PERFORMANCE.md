# Transcription accélérée — préversion 0.2.5

Le signalement d'une transcription lente sur RTX 3080 Laptop a conduit à modifier le
chemin d'inférence. Aucun gain chiffré sur ce PC n'est encore mesuré.

## Réglages proposés

Dans **Import et transcription**, choisir CUDA puis :

- Cocher **Traitement par lots sur GPU** et commencer avec une taille de **8**.
- Garder **Qualité**, qui conserve une recherche de cinq hypothèses (`beam_size=5`).
- Comparer ensuite **Rapide** (`beam_size=1`) sur la même réunion ; vérifier les paroles,
  les noms propres, les nombres et les passages techniques avant d'adopter ce profil.
- Comparer `float16` et `int8_float16` sans changer les autres réglages. La meilleure
  configuration dépend du GPU et de la réunion, pas uniquement de la mémoire disponible.
- Décocher le traitement par lots pour retrouver le chemin séquentiel antérieur.

Le modèle large-v3 reste inchangé. Pas de téléchargement supplémentaire nécessaire.
Les réglages de taille, qualité et quantification sont conservés entre les sessions.
En CPU, l'interface utilise le chemin séquentiel ; le traitement par lots GPU est désactivé.

## Deux tailles distinctes

L'audio est toujours assemblé dans des fenêtres disque bornées à cinq minutes, puis
les portions détectées par le VAD sont traitées ensemble par `BatchedInferencePipeline`.
Une taille GPU de 8 désigne au maximum huit portions de décodage par appel au modèle,
pas huit modèles ni huit réunions. Les pistes restent séparées, traitées successivement.

La génération de timestamps reste activée (`without_timestamps=False`) et les temps
restaurés par faster-whisper sont décalés sur la piste puis contrôlés par le mécanisme
0.2.3. Les chevauchements entre pistes ne sont pas dédupliqués automatiquement.
Le mode par lots traite les portions sans le contexte de sortie de la portion précédente ;
certains mécanismes de reprise de décodage du chemin séquentiel diffèrent également.
Ainsi, le même modèle et le même beam ne garantissent pas un texte identique.
La qualité et les frontières doivent être comparées sur un audio représentatif.

## Mémoire et reprises

Une erreur explicite de mémoire CUDA réduit automatiquement les lots (8 → 4 → 2 → 1),
puis essaie le chemin CUDA séquentiel. Si CUDA reste inutilisable, le repli CPU/int8
n'est autorisé que si sa case est cochée. La réduction des lots reste possible avec
le repli CPU décoché. Les erreurs disque/audio et les annulations ne relancent pas le calcul.

Chaque reprise repart du début de cette tentative, remplace uniquement ses résultats
partiels et libère le modèle/pipeline précédent avant rechargement. Les tentatives
antérieures et leurs corrections restent conservées. Cette reprise peut prendre du temps ;
une taille déjà réduite à la main évite de répéter l'essai trop volumineux.

L'annulation reste coopérative : le chargement ou le lot de décodage en cours doit finir.
Un lot plus grand peut augmenter cette latence. La capture reste indépendante du moteur IA.

## Mesures

L'historique et l'export JSON affichent le mode réellement utilisé et les mesures :

- Durée totale du traitement, incluant les reprises, initialisations et libérations.
- Temps de chargement du modèle/pipeline.
- Temps de préparation des WAV à partir des fragments.
- Temps d'inférence, incluant décodage audio, VAD, caractéristiques et génération du texte.
- Temps d'écriture des segments et de leur audit SQLite.
- Audio des fenêtres entièrement terminées, additionné entre pistes, divisé par la durée
  totale : vitesse globale en fois le temps réel. Ce n'est pas un score de qualité.

Pour une réunion de dix minutes sur deux pistes, le volume traité peut être vingt
minutes-pistes. Les silences sont compris dans cette durée source. Les métriques des
anciennes tentatives ne sont pas inventées rétroactivement. Les mesures finales sont
sauvées à la fin, en erreur ou à l'annulation ; un arrêt brutal peut les perdre.
Les étapes ne couvrent pas toute la durée totale (pré-vérification CUDA et nettoyage,
notamment). Les détails par reprise sont présents dans `performance.attempts` en JSON.

## Vérification automatique et matérielle

La CI utilise les vrais poids tiny sur CPU pour exécuter un lot de deux requêtes de
décodage, la chaîne de production par lots avec VAD et le traitement hors ligne. Le même
contrôle est exécuté depuis le programme Windows installé. Les tests simulés vérifient
les paramètres, les offsets, la réduction de mémoire, la libération des modèles et
l'absence de doublons. Ils ne mesurent pas les performances CUDA ni la qualité française.

Sur le PC utilisateur : comparer séquentiel puis lots de 8, à modèle/quantification/beam
identiques, puis comparer Rapide et float16 séparément. Relever la durée totale et vérifier
les mêmes passages audio. Les graphiques 3D/vidéo du Gestionnaire des tâches ne mesurent
pas nécessairement le moteur de calcul utilisé ; sélectionner CUDA/Compute si proposé.
