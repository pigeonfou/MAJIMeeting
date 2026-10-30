# Utiliser la nouvelle interface

La liste **Mes réunions** reste visible à gauche pendant l’enregistrement, la lecture
et la préparation des modèles. Le champ de recherche filtre les titres, dates et états.
Cliquer sur une réunion affiche ses transcriptions ; cela ne relance aucun calcul.

## Parcours principal

1. **Enregistrer** : donner un titre, cocher les sources audio, démarrer puis arrêter.
   La réunion enregistrée est sélectionnée à la fin de la capture.
   Pour un fichier existant, utiliser **Importer de l’audio…** dans la colonne de gauche.
2. **Transcription et intervenants** : lancer **Transcrire et identifier les intervenants…**.
   Le dialogue conserve les réglages Community-1 et les préparatifs nécessaires.
3. Dans **Texte**, lire le résultat, **Corriger et réécouter…**, ou exporter en TXT/JSON.
4. Dans **Intervenants**, nommer les groupes par de courts extraits. Les analyses
   précédentes restent accessibles et la diarisation peut être relancée sans refaire
   la transcription. Les voix superposées restent signalées comme incertaines.
5. **Diagnostic** contient le calcul réellement utilisé, les performances et les
   avertissements d’horodatage de la transcription sélectionnée.

**Ouvrir une transcription…** retrouve une transcription sauvegardée, affiche l’onglet
Texte et enlève le filtre de recherche si celui-ci masquait la réunion.
Le sélecteur de transcription permet de revenir aux traitements précédents de la réunion.

## Paramètres

Les dossiers de modèles, le téléchargement de large-v3, CPU/CUDA, la précision, les
lots et les options GPU avancées sont regroupés dans **Paramètres**.
Les valeurs antérieures sont conservées : cette réorganisation ne change pas les
moteurs de transcription ou de diarisation ni leurs réglages.

**Préparer Community-1…** ouvre directement la préparation du modèle et des dépendances,
même sans réunion sélectionnée. **Enregistrer les réglages** y mémorise les chemins
sans lancer d’analyse. Les traitements eux-mêmes restent dans l’espace Transcription.
Le thème sombre se trouve dans Apparence ; son choix est mémorisé dans le canal utilisé.

## Menus et raccourcis

| Menu / raccourci | Action |
| --- | --- |
| Fichier / Ctrl+I | Importer de l’audio |
| Fichier / Ctrl+O | Ouvrir une transcription sauvegardée |
| Fichier | Exporter une piste WAV ou une transcription |
| Enregistrement | Actualiser les sources, démarrer, arrêter |
| Analyse | Transcrire, nommer, corriger ou relancer la diarisation |
| Affichage / Ctrl+1 | Enregistrer |
| Affichage / Ctrl+2 | Transcription et intervenants |
| Affichage / Ctrl+3 | Paramètres |
| Fichier / Ctrl+Q | Quitter, avec protection si un traitement est en cours |

La progression et le bouton d’annulation sont visibles en bas sur tous les écrans,
y compris pendant un téléchargement. Les commandes concurrentes sont désactivées,
y compris dans les menus ; l’annulation attend la fin du segment en cours.

Les dialogues spécialisés de correction, de nomination et de réglage Community-1
restent disponibles depuis ces espaces. Aucun compte rendu LLM n’est encore généré.
