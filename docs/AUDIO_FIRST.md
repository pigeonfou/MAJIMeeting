# Parcours expérimental : audio, voix puis transcription

Cette option permet de comparer le nouveau parcours au parcours classique sur la
même réunion. Le parcours classique reste sélectionné par défaut. Aucun gain de vitesse
ou de qualité n’est acquis avant les essais sur des réunions représentatives.

## Essayer depuis le canal DEV

1. Ouvrir **Paramètres → Parcours de traitement complet**.
2. Choisir **Expérimental — audio, voix puis transcription**.
3. Pour la première comparaison, laisser la normalisation désactivée, le seuil VAD à
   0,50 et le silence entre zones à 500 ms. Garder les réglages GPU habituels.
4. Sélectionner la même réunion dans Mes réunions. Ouvrir **Transcription et intervenants**
   et lancer **Transcrire et identifier les intervenants…**.
5. Vérifier le runtime Community-1, son modèle et le calcul CPU/CUDA dans le dialogue.
   Lancer le nouveau parcours, puis nommer les groupes à partir des extraits proposés.
6. Comparer les changements de voix, les mots proches des silences et les passages
   simultanés avec la transcription classique. Chaque lancement garde un résultat distinct.

**Transcrire uniquement** reste une transcription classique, quel que soit le parcours
choisi pour l’analyse complète. Les anciennes transcriptions restent consultables.

## Traitements exécutés

1. Vérification des fragments et de leur chronologie. Copie de travail mono 16 kHz,
   avec conservation de l’origine de chaque piste et insertion de silence dans les trous.
   Les fichiers enregistrés/importés ne sont jamais réécrits.
2. Mesure de crête, RMS et échantillons saturés. Normalisation facultative : cible de
   crête −3 dBFS, gain limité entre ×0,5 et ×2. Elle ne restaure pas un son déjà saturé.
   Aucun débruitage ni filtre spectral dans cette première version.
3. VAD Silero livré avec faster-whisper, exécuté localement sur CPU par blocs de
   dix minutes avec contexte autour des bornes. Zones horodatées sauvegardées sur
   l’axe original ; pas de suppression physique des silences dans la piste de travail.
4. Community-1 analyse globalement chaque piste, y compris ses pauses. Les annotations
   normales et exclusives sont conservées. Le processus PyTorch se termine avant
   le chargement de Whisper ; les modèles ne partagent pas simultanément la VRAM.
5. Fenêtres regroupant les zones de parole, avec contexte. Les annotations exclusives
   aident à choisir une coupure proche de la limite d’une fenêtre. Les clips de décodage
   sont limités à 29,5 s, sans concaténation de leur axe temporel. Les zones VAD déjà
   calculées sont transmises à Whisper : son VAD interne n’est pas relancé. Traitement
   séquentiel ou par lots, un ou deux workers et reprises CUDA/CPU existants conservés.
6. Reconstruction aux mots avec les annotations normales : elles restent la référence
   pour signaler les chevauchements. Puis nomination rapide par extraits et corrections
   habituelles. La sortie exclusive ne sépare pas acoustiquement deux voix simultanées.

Une piste entièrement silencieuse selon le VAD donne un résultat vide explicite,
sans chargement des modèles Whisper ou Community-1. Si une parole faible manque,
comparer avec le parcours classique et essayer un seuil VAD plus bas.

## Réutilisation et corrections

Les étapes sont enregistrées dans `analysis-cache/v1` du dossier de la réunion.
Chaque résultat publié possède un manifeste et des empreintes de contenu. Les étapes
incomplètes ne sont pas réutilisées ; une étape endommagée est conservée à part puis
recalculée. Les copies de travail occupent environ 115 Mo par heure et par piste ;
plusieurs réglages de normalisation peuvent conserver plusieurs copies.

| Changement | Recalcul nécessaire |
| --- | --- |
| Nom ou correction manuelle | Aucun modèle |
| Regroupement / nombre de voix | Diarisation ; audio/VAD réutilisés, texte conservé |
| Nouvelle transcription avec le même audio et les mêmes réglages de voix | Whisper ; audio/VAD/voix réutilisables |
| Seuil VAD ou silence | VAD et nouvelle transcription ; voix réutilisables si audio inchangé et présence de parole inchangée |
| Normalisation, contenu ou chronologie des sources | Nouvelle préparation puis étapes dépendantes |
| Modèle Community-1, runtime ou réglages de diarisation | Nouvelle diarisation |

**Intervenants → Réessayer la diarisation…** reconnaît les transcriptions issues du
nouveau parcours et réutilise leurs copies audio et leur VAD. Les corrections humaines
restent prioritaires ; un alignement du texte déjà connu peut être nécessaire si ses
horodatages de mots manquent, sans nouveau décodage de la transcription.
Les noms restent propres à chaque analyse ; aucun transfert certain d’identité entre
des regroupements différents n’est effectué.

Si les sources ont changé depuis la transcription, la réattribution des voix est refusée :
créer une nouvelle transcription pour ne pas associer un ancien texte à une autre chronologie.
Les réglages audio d’un ancien résultat restent ceux de sa création ; changer les paramètres
VAD/normalisation dans Paramètres s’applique au prochain traitement complet.

La vérification de cache lit les empreintes des fichiers audio et du modèle local ; elle
consomme donc encore des accès disque même si l’inférence est réutilisée. Les étapes
terminées restent disponibles après annulation d’une étape suivante. Le premier essai
peut être plus long, car il doit créer toutes les copies et calculer les étapes.

## Mesures et limites

**Diagnostic** indique les temps de Whisper et, séparément, le temps écoulé avant
transcription ainsi que les étapes réutilisées. Les options et l’historique JSON gardent
les réglages, empreintes, origines et informations d’exécution des réseaux. Les temps
Whisper seuls ne permettent pas de conclure à un gain sur l’ensemble du parcours.

Limite actuelle : quatre heures par piste, comme l’adaptateur Community-1 précédent.
La qualité des frontières VAD, des coupures et des groupes sur réunions longues,
les niveaux faibles et les paroles simultanées restent à évaluer sur le PC utilisateur.
Une étape de filtrage facultatif et le compte rendu Qwen/llama.cpp restent à développer.
