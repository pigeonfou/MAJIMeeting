# Essais GPU avancés — préversion 0.2.6

Cette version permet de tester les optimisations proposées après les mesures utilisateur
0.2.5. Aucun gain ni compatibilité Flash Attention sur la RTX ne sont encore certifiés.
Un seul modèle Whisper reste chargé. Aucun poids à télécharger de nouveau.
Flash Attention et deux workers sont désactivés par défaut.

## Protocole RTX 3080 Laptop

Conserver même réunion, même modèle, CUDA / float16 / lots 16 / Rapide. Installer par-dessus
l'ancienne version puis effectuer ces essais séparément :

| Essai | Flash Attention | Workers | Fenêtre | Lot maximum |
|---|---|---:|---:|---:|
| Référence avec cette version | Non | 1 | 5 min | 16 |
| Flash seul | Oui | 1 | 5 min | 16 |
| Concurrence seule | Non | 2 | 5 min | 16 |
| Remplissage seul | Non | 1 | 10 min | 16 |
| Plus grand lot, si utile | Non | 1 | 10 min | 32 |

Combiner seulement après les essais séparés. Relever durée totale, mode effectif,
remplissage et avertissements. Réécouter les mêmes passages, noms, nombres et termes
techniques. Répéter les meilleurs essais pour distinguer leur effet des variations
initiales de chargement. L'export JSON conserve paramètres et mesures.

## Flash Attention

La case transmet `flash_attention=True` à CTranslate2. Le moteur installé peut ne pas le
prendre en charge. Une erreur explicite mentionnant Flash Attention déclenche une reprise
CUDA sans cette option, sans imposer CPU. L'historique indique alors Flash Attention non
et le motif. Cela ne constitue pas un benchmark Flash : le temps de l'essai échoué figure
dans le total. Une option acceptée ne prouve pas une occupation particulière des Tensor Cores.
Les autres erreurs ne sont pas assimilées automatiquement à une incompatibilité Flash.

## Deux workers et reprises

`WhisperModel(num_workers=2)` configure deux workers CT2 partageant les poids. Deux threads
soumettent réellement des fenêtres distinctes, chacune avec son propre pipeline et état
temporel. Les WAV et offsets sont isolés ; l'affichage final reste trié par horodatage.
Cela n'ajoute aucune diarisation des personnes.

La file est bornée à deux fenêtres. Les tâches sont attendues avant suppression de leurs
fichiers et libération du modèle, y compris en erreur ou annulation. L'annulation reste
coopérative et peut attendre le lot en cours. Aucun fichier n'est réécrit pendant sa lecture.

Si la VRAM manque, reprise à un worker avant réduction des lots, puis CUDA séquentiel
et l'éventuel repli CPU autorisé. La tentative courante repart du début sans doublons ;
les autres tentatives et corrections sont conservées. Le partage des poids n'empêche pas
une augmentation de mémoire de travail. Deux workers peuvent être plus lents qu'un seul.

## Lots natifs et métriques

Les fenêtres disque passent de 5 à 10 minutes sur choix explicite. Deux fenêtres au maximum
sont confiées aux workers, avec un WAV de préparation supplémentaire. Le VAD et le découpage
natif Whisper restent actifs.
Les frontières et le contexte peuvent modifier le texte : comparer la qualité.

L'instrumentation du forward natif relève les tailles réellement décodées. Remplissage =
portions / somme des capacités maximales des appels. Exemple : tailles 16 et 4, limite 16,
donnent 20/32 = 62,5 %. Ce n'est ni l'occupation GPU ni le pourcentage de parole. Un silence
entièrement supprimé par VAD ne produit aucun appel compté.

Avec deux workers, inférence et écriture sont cumulées entre threads et peuvent dépasser
le temps total. Comparer le temps total pour le débit ; la vitesse globale conserve les
secondes-pistes complètement traitées. Les détails restent dans l'export JSON.

## Validation

Les simulations vérifient les replis Flash/mémoire, le partage du modèle, l'isolation des
fichiers, le chevauchement réel des workers, les offsets, l'absence de doublons et l'annulation.
Les vrais poids tiny exécutent deux décodages concurrents en CPU et le chemin de production
parallèle avec VAD. Le workflow Windows exécute ces contrôles dans l'application installée.
Ces contrôles ne valident pas les kernels Flash CUDA, la VRAM ni large-v3 sur la RTX.
