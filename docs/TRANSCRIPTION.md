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
  En cas d’indisponibilité CUDA, l’option de repli CPU/int8 permet une reprise automatique.
  Cette option est visible et peut être désactivée ; les transcriptions précédentes sont conservées.
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

## Téléchargement corrigé — 0.2.1

Le bouton affiche désormais connexion, fichier en cours, Mo reçus, pourcentage et contrôle
 d'intégrité. La connexion et chaque lecture réseau utilisent des délais de 10 et 15 secondes
 respectivement (sans boucle de réessai infinie). Le bouton Annuler arrête au prochain bloc
 ou après la fin de l'attente réseau en cours. Les fichiers `.part` sont conservés et repris
 au prochain clic si leurs métadonnées correspondent au modèle demandé.

Les téléchargements utilisent HTTPS directement, sans charger le moteur d'inférence ni
 les barres de progression console du SDK. Tous les fichiers sont contrôlés par empreinte
 avant remplacement ; les fichiers déjà complets et vérifiés sont conservés.
 Le fichier `download.log` dans le dossier du modèle contient le diagnostic local.

Le test Windows installé télécharge réellement un modèle tiny via ce même composant,
 puis lance l'inférence avec ce dossier en mode hors ligne. Il ne télécharge pas les 3 Go
 de large-v3 dans la CI. Les essais utilisateur large-v3/CUDA restent nécessaires.

## CUDA indisponible — 0.2.2

Le message `Library cublas64_12.dll is not found or cannot be loaded` concerne le calcul
NVIDIA, pas les poids Whisper. Choisir **CPU / int8** permet de transcrire sans ces DLL.

En CUDA, la case **Si CUDA est indisponible, reprendre sur CPU/int8** autorise une reprise
explicite. Les bibliothèques et le pilote sont vérifiés avant l'inférence. Le modèle GPU
est libéré avant chargement du modèle CPU. Si l'erreur survient pendant l'itération paresseuse
des segments, la tentative est recommencée en entier : ses segments GPU partiels sont
remplacés par la sortie CPU, sans doublons ni modification des tentatives précédentes.
L'historique conserve le mode effectif, la quantification et la raison du repli.
Les erreurs non liées à CUDA et les annulations ne déclenchent pas une relance CPU.

Les dossiers standard CUDA 12/cuDNN 9 et les variables CUDA_PATH/CUDNN_PATH sont explorés.
Le champ facultatif des DLL permet d'indiquer un dossier déjà installé, sans modifier le
PATH système. Les DLL et le pilote ne sont pas fournis par cette préversion.
Voir [l'installation GPU Windows](CUDA_WINDOWS.md) pour les sources officielles NVIDIA.

## Limites de lots et avertissements — 0.2.3

Whisper peut renvoyer des temps qui dépassent la durée du dernier lot, notamment sur
sa fin complétée par du silence. Ces segments ne provoquent plus l'arrêt de la réunion.
Les intervalles qui recoupent l'audio sont bornés à sa durée réelle. Les segments entièrement
hors audio, sans durée ou aux temps non finis/inversés sont écartés de la transcription
horodatée. Les sorties vides sont ignorées avant contrôle temporel.

Chaque ajustement ou rejet non vide est conservé dans une table d'audit locale avec piste,
début du lot, temps bruts, motif et texte brut. L'historique affiche les compteurs et le
bouton **Voir les avertissements d'horodatage**. L'export JSON ajoute `timestamp_warnings` ;
l'export TXT signale leur nombre. Les textes rejetés ne sont pas mélangés aux segments
validés. Ces passages doivent être réécoutés/vérifiés : borner un temps ne prouve pas
l'exactitude du texte reconnu, et le correctif ne reconstitue aucune parole manquante.

Les tentatives antérieures restent consultables. Après mise à jour, relancer la transcription
de la réunion existante ; il n'est pas nécessaire de réimporter l'audio ni le modèle.
Les erreurs de décodage, de disque ou de modèle continuent à être signalées en erreur.

## Accélération GPU — 0.2.5

La transcription peut désormais grouper les portions de décodage sur GPU, avec choix de
la taille et du profil de recherche. Les mesures finales figurent dans l'historique.
Voir [les réglages et le protocole de comparaison](PERFORMANCE.md). Le mode séquentiel,
les horodatages contrôlés et les corrections restent disponibles.
