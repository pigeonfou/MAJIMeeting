# Interlocuteurs — Community-1 et découpage du texte (0.2.11)

La transcription et ses optimisations restent disponibles. La diarisation est une phase
séparée déclenchée sur une transcription terminée. Elle ne déduit jamais les noms réels.

## Préparation sur Windows (une fois, avec connexion)

L'application normale ne contient pas PyTorch : son runtime est isolé pour conserver
le moteur Whisper existant et libérer la VRAM à la fin de chaque processus d'analyse.

1. Installer Python 3.11 x64 avec le lanceur `py` si absent.
2. Avec votre compte Hugging Face, accepter les conditions du modèle
   https://huggingface.co/pyannote/speaker-diarization-community-1 et créer un jeton de lecture.
   Aucun accès au compte n'est demandé à ChatGPT. L'acceptation reste personnelle.
3. Dans **Distinguer automatiquement les interlocuteurs**, choisir CPU ou CUDA puis
   cliquer **Télécharger et installer les dépendances**. La progression et les messages
   d'installation sont affichés dans cette fenêtre. Le modèle n'est pas retéléchargé.
   L'installation s'effectue dans le runtime utilisateur géré ; son Python est sélectionné
   automatiquement après réussite. Python 3.11 x64 avec le lanceur `py` reste un prérequis.
4. Cliquer **Télécharger le modèle Community-1** et saisir le jeton dans le champ masqué.
   Le téléchargement est indépendant du runtime, reprend les transferts partiels et
   vérifie les fichiers par taille/empreinte à une révision fixe du dépôt. Le jeton n'est
   enregistré ni en paramètres ni en journal. Les erreurs 401/403 indiquent de vérifier
   les conditions d'accès et le jeton. Les fichiers déjà présents et vérifiés sont réutilisés.
5. Chemins par défaut : `%LOCALAPPDATA%\MAJIMeeting\runtime\Scripts\python.exe` et
   `%LOCALAPPDATA%\MAJIMeeting\models\community-1`. Un modèle téléchargé manuellement
   peut toujours être sélectionné sans utiliser le bouton de téléchargement.

Pendant une préparation, les chemins et le lancement de l'analyse sont désactivés.
Le bouton d'annulation interrompt l'installation et ses processus enfants ; le téléchargement
peut attendre la fin de la requête réseau en cours (délais de connexion/lecture bornés).
Fermer la fenêtre demande l'arrêt avant fermeture. Une annulation conserve les téléchargements
partiels pour reprise ; relancer l'installation répare le runtime incomplet.
Le raccourci historique du menu Démarrer et le script restent disponibles en alternative.

Ce runtime utilisateur et les modèles persistent après mise à jour ou désinstallation
pour éviter de perdre les données. Ils peuvent être supprimés manuellement si inutiles.

## Analyse hors ligne

Sélectionner une transcription terminée puis **Distinguer automatiquement les interlocuteurs**.
Choisir le runtime et le dossier Community-1 local, CUDA ou CPU et éventuellement un nombre
connu de voix **par piste** (0 = automatique). Le worker série de l'application exclut
la capture pendant cette tâche. Whisper et Community-1 ne résident pas ensemble sur le GPU.
Un sous-processus termine et libère Torch
après chaque piste. Annuler arrête le processus ; une analyse interrompue ou échouée ne
remplace jamais la dernière analyse terminée.

L'analyse bloque les connexions réseau du sous-processus et désactive les métriques
pyannote, OpenTelemetry et le Hub en ligne. Aucun téléchargement pendant une analyse.
Un modèle incomplet provoque une erreur explicite.

## Groupes et corrections

Chaque piste a son propre espace de groupes : `track-00:SPEAKER_00` n'est pas supposé
identique à `track-01:SPEAKER_00`. Dans l'éditeur, sélectionner un passage puis **Nommer tous
les passages du groupe sélectionné**. Le même nom peut être attribué explicitement à
plusieurs groupes après écoute. Les corrections individuelles restent prioritaires,
y compris le choix manuel de retirer un nom. Les noms successifs de groupe sont historisés.

Les tours pyannote et les segments originaux sont conservés séparément. Depuis0.2.11,
l'affichage peut découper un segment aux mots lorsque plusieurs voix s'y succèdent.
Les superpositions, les limites incertaines et les mots sans couverture fiable restent à vérifier.
Aucun texte n'est distribué proportionnellement au temps, ni dupliqué sous plusieurs noms.
Les tours en chevauchement et l'historique restent dans le JSON. Voir le parcours0.2.11 ci-dessous.

## Limites et validation

- La première version limite une piste à 4 heures de chronologie pour borner le tenseur
  utilisé par Community-1. La préparation WAV mono 16 kHz est en streaming et conserve
  les trous en silence et l'origine absolue de la piste. Ne pas découper une piste en
  petits appels indépendants : les groupes n'y auraient pas une identité cohérente.
- Le découpage mot à mot est intégré en0.2.11. Il ne sépare pas acoustiquement deux voix
  simultanées dans une piste mono et ne corrige pas à lui seul une fusion erronée de voix par le modèle.
- Les tests automatiques vérifient persistance, reprises, processus annulable, PCM,
  horodatages, corrections et interface. Le job runtime Windows installe et importe les
  vraies bibliothèques CPU. Les poids Community-1 soumis à acceptation ne sont pas fournis
  à la CI : ne pas confondre ces contrôles avec un test de qualité de diarisation.
- À réaliser sur le PC cible : préparation CUDA/modèle, traitement d'une réunion connue
  avec 2–3 voix, chevauchements, silence et pistes mic/système, puis test sans connexion,
  renommage, correction individuelle, export JSON et interruption/reprise. Vérifier que
  les passages difficiles restent signalés ; relever durée, RAM et VRAM.

Sources primaires : fiche modèle Community-1 ci-dessus (usage local, waveform et sorties
régulières/exclusives), dépendances pyannote.audio 4.0.7 sur PyPI et télémétrie pyannote.audio.


## Réglages et essais successifs (0.2.10)

Dans **Import et transcription**, **Ouvrir une transcription existante…** liste les transcriptions terminées de la base locale, avec recherche par réunion/date. Cette action ne lance ni import ni Whisper. Les textes, corrections, pistes et analyses sont réutilisés. La dernière transcription ouverte est retrouvée au démarrage. Conserver le répertoire de données et l'audio d'origine : un export TXT seul ne permet pas de refaire la diarisation.

**Distinguer / réessayer…** ouvre désormais deux onglets : réglages de l'analyse et préparation du modèle/dépendances. Les réglages sont conservés ; sélectionner une ancienne analyse permet de reprendre ses réglages. Les options avancées décochées conservent les valeurs du modèle local, sans réécrire son config.yaml.

- **Nombre exact OU minimum/maximum** : 0 laisse le modèle décider. Un réglage spécifique par piste permet par exemple un seul locuteur au micro et plusieurs sur Teams. Ne pas compter deux fois une même personne, et ne pas imposer le nombre global de personnes à toutes les pistes.
- **Seuil initial VBx** (0,5–0,8), **Fa** (0,01–0,5) et **Fb** (0,01–15) : paramètres pris en charge par Community-1/pyannote.audio4.0.7. Le seuil augmente la fusion lors du regroupement initial ; VBx intervient ensuite, le nombre final n'est donc pas garanti. Les valeurs affichées à l'activation manuelle (0,6 / 0,07 / 0,8) sont les références du code pyannote4.0.7, pas une lecture du fichier config local. Les paramètres effectivement appliqués sont enregistrés pour chaque piste.
- **Comblement des silences** : durée minimale de pause conservée, 0–1 seconde. Augmenter comble des interruptions courtes ; cela peut modifier les limites de parole.
- **Chevauchements et empreintes** : laisser le modèle décider, ou inclure/exclure les voix superposées lors de l'extraction des empreintes. L'exclusion ne supprime pas l'audit des chevauchements.
- **Lots segmentation / empreintes** : 0 conserve le modèle, 1–64 règle débit et mémoire. Ces réglages ne garantissent pas une meilleure qualité. Pas de reprise OOM automatique pour cette première intégration : réduire les lots puis réessayer. Les réglages Whisper restent distincts.

L'historique des essais conserve date, statut, nombre de groupes et passages ambigus, durée totale, réglages demandés et effectifs par piste. **Revenir au résultat de cette analyse** réaffiche une analyse terminée, avec ses noms de groupes. La sélection survit au redémarrage. Une nouvelle analyse réussie devient celle affichée ; un échec ne remplace pas la précédente. Les corrections individuelles de texte et de noms restent prioritaires, même en réanalysant. Les noms attribués aux groupes ne sont pas automatiquement transférés à de nouveaux groupes : cela supposerait une identification certaine non démontrée.

### Diagnostiquer CPU et CUDA

Le choix CUDA de Whisper ne configure pas le runtime pyannote. Dans le dialogue de diarisation, choisir **cuda**. L'application vérifie CUDA puis le placement du pipeline et des réseaux segmentation/empreintes ; elle refuse de continuer si CUDA était demandé et qu'un réseau reste sur CPU. Elle affiche les étapes et le nom du GPU, puis conserve les périphériques effectifs et le pic mémoire allouée par Torch dans l'historique/JSON. Les intervalles entre notifications des hooks sont conservés à titre de diagnostic, pas comme mesure précise du temps GPU.

La préparation PCM, la collecte de résultats, le regroupement VBx/PLDA et certaines opérations d'empreintes utilisent le CPU. Une période CPU chargée et GPU peu actif ne prouve donc pas un repli CPU de l'ensemble du pipeline. Le graphique 3D du Gestionnaire des tâches n'est pas une mesure fiable de CUDA ; sélectionner NVIDIA puis CUDA/Compute. Le pourcentage d'occupation GPU instantané n'est pas mesuré par MAJIMeeting.

### Premier protocole de comparaison

1. Ouvrir la transcription existante, conserver les réglages modèle et noter les groupes/passages problématiques.
2. Si le nombre de voix est connu, régler ce nombre sur la bonne piste et relancer seulement la diarisation.
3. Si une voix est fragmentée en plusieurs groupes, comparer un seul changement de seuil à la fois (par exemple0,60 puis0,65), en gardant Fa/Fb et les autres contrôles fixes. Ne pas confondre fusion indue de deux personnes et amélioration.
4. Réécouter les mêmes passages, vérifier aussi les changements de voix et chevauchements. Un total de groupes ou de passages ambigus plus faible ne prouve pas une meilleure qualité.
5. Revenir à un essai précédent si nécessaire ; les analyses et corrections ne sont pas effacées.

Références d'implémentation : [SpeakerDiarization4.0.7](https://github.com/pyannote/pyannote-audio/blob/4.0.7/src/pyannote/audio/pipelines/speaker_diarization.py), [VBxClustering4.0.7](https://github.com/pyannote/pyannote-audio/blob/4.0.7/src/pyannote/audio/pipelines/clustering.py), [placement des pipelines](https://github.com/pyannote/pyannote-audio/blob/4.0.7/src/pyannote/audio/core/pipeline.py).


## Parcours simple : transcrire, découper, nommer (0.2.11)

1. Sélectionner la réunion puis **Transcrire et proposer les intervenants…**. Confirmer les réglages locaux et le nombre de voix par piste si connu (0 = automatique).
2. Le worker enchaîne Whisper avec horodatage par mot, puis Community-1. Les modèles sont libérés successivement. Si la diarisation échoue, la transcription terminée est conservée et peut être rouverte sans refaire le texte.
3. L'écran de nomination s'ouvre à la fin. Il propose jusqu'à trois extraits représentatifs par groupe (12 secondes maximum), en évitant les tours simultanés. Nommer chaque groupe une seule fois, avec écoute d'un bref extrait si nécessaire. Les noms s'appliquent aux passages correspondants ; les noms connus de cette réunion sont proposés en complétion. Le bouton Appliquer enregistre les noms, et la fermeture les conserve aussi.
4. Consulter au besoin **Afficher uniquement les passages à vérifier** dans l'éditeur. Les passages attribués ne nécessitent pas une réécoute intégrale. Une attribution automatique reste une hypothèse : cette ergonomie réduit la revue, sans garantir une exactitude parfaite.

**Pour une transcription0.2.10 déjà réalisée :** l'ouvrir, vérifier que le modèle Whisper local est sélectionné dans le panneau, puis relancer seulement **Distinguer / réessayer…**. Après Community-1, le texte original des segments ambigus sans horodatage lexical est aligné sur l'audio avec l'API d'attention de faster-whisper, sans nouveau décodage du texte. Le PCM déjà préparé est réutilisé. Les mots validés sont conservés pour les essais suivants. Nommer ensuite les groupes avec **Nommer les intervenants à partir de courts extraits…**.

### Ce qui est conservé

- Segments et textes originaux inchangés ; table additive d'horodatages lexicaux et passages dérivés propres à chaque analyse.
- Historique des analyses, noms et corrections. Les corrections anciennes au niveau d'un segment restent prioritaires : l'application ne redistribue pas arbitrairement un texte humain modifié entre plusieurs voix.
- Une correction d'un passage découpé est réutilisée lors d'un autre essai seulement si les bornes et le texte source de ce passage sont identiques. Si le découpage change, l'ancienne correction reste dans son analyse/historique, sans transfert incertain ; revenir à l'ancienne analyse permet de la retrouver.
- Le JSON exporte les passages affichés, les segments sources, les mots et l'historique des corrections et analyses.

### Exceptions à vérifier et limites

Deux personnes qui parlent successivement ne rendent plus systématiquement toute une phrase ambiguë : on compare les mots aux tours de parole et on découpe aux changements de groupe. Un mot à une frontière mal déterminée, une faible couverture ou un alignement peu fiable reste signalé. En présence de voix réellement simultanées, le texte n'est ni dupliqué ni attribué avec certitude : les groupes possibles sont indiqués.

Pour l'alignement d'une ancienne transcription, les segments dépassant30secondes ou400tokens restent non résolus dans cette première version. Une absence de modèle Whisper local laisse les passages concernés explicitement sans alignement ; aucun téléchargement automatique n'a lieu. Des mots invalides ou ne reproduisant pas le texte original sont refusés. Les nouvelles transcriptions demandent directement les horodatages à Whisper et peuvent donc prendre davantage de temps que les anciens essais sans cette option. Aucun gain de vitesse ou de précision globale n'est annoncé sans mesure sur vos réunions.

La qualité de regroupement de Community-1 reste déterminante : si deux personnes sont fusionnées en un seul groupe acoustique, le découpage lexical ne peut pas créer leur identité réelle. La séparation des paroles simultanées et l'identification certaine de personnes ne sont pas réalisées par cette version.
