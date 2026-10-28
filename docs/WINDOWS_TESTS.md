# Validation du prototype Windows

## Résultats utilisateur — 28 octobre 2026

| Essai | État |
| --- | --- |
| Sélection du microphone et de la sortie système | Réussi |
| Capture ≥ 2 minutes, silence et interface réactive | Réussi |
| Export et écoute des deux pistes, durée et intelligibilité | Réussi |
| Arrêt forcé, redémarrage et export des fragments récupérés | Réussi |
| Débranchement du microphone | À réaliser |
| Réunion longue, charge mémoire/CPU/disque et dérive | À réaliser |
| Capture et export sans réseau | À réaliser |
| Désinstallation et conservation des réunions | À réaliser |

L'utilisateur demande de poursuivre J2 avec ces essais complémentaires encore ouverts.

## Protocole

Le build automatisé ne peut pas valider votre matériel audio. Ces essais ne nécessitent
pas encore le GPU ni l'installation des modèles.

1. Télécharger l'artefact MAJIMeeting-Windows-preview du dernier workflow CI réussi.
2. Installer le programme puis le lancer depuis le menu Démarrer.
3. Donner un titre à la réunion et cocher le microphone et le périphérique « Audio système »
   correspondant aux haut-parleurs/casque de Teams ou Zoom.
4. Enregistrer au moins deux minutes : parler dans le micro, lire une source audio système,
   inclure une période silencieuse et arrêter. L'interface doit rester réactive.
5. Sélectionner la réunion, exporter chacune des deux pistes et écouter les WAV : vérifier
   sources distinctes, durée, absence de coupures et volume intelligible.
6. Faire une nouvelle capture, attendre 10 secondes, terminer le processus dans le
   Gestionnaire des tâches puis relancer. La réunion doit être « interrupted » et ses
   fragments finalisés doivent pouvoir être exportés.
7. Tester le débranchement du microphone pendant la capture : l'erreur doit être visible
   et les fragments déjà sauvés conservés. Certains pilotes ne signalent pas immédiatement
   la déconnexion : consigner le modèle du périphérique et le comportement observé.
8. Enregistrer une heure avec les deux sources et un signal commun au début et à la fin.
   Mesurer leur décalage initial et leur dérive. Vérifier mémoire, charge CPU et espace disque.
9. Refaire démarrage, capture et export sans connexion réseau.
10. Désinstaller : le programme doit être supprimé, les réunions conservées.

Données : `%LOCALAPPDATA%\MAJIMeeting\data`. Chaque piste contient `track.json`, des WAV
numérotés et leurs fichiers JSON d'horodatage. Les fichiers `.part` ne sont jamais exportés.
Ne pas déplacer ces fichiers pendant une capture. Prévoir environ 346 Mo/heure par piste
mono 48 kHz, 691 Mo/heure en stéréo ; multiplier par le nombre de pistes.

Retour attendu : version Windows, périphériques/pilotes, résultat de chaque essai,
message exact en cas d'erreur, durée/dérive observée. Ne pas communiquer d'audio confidentiel.
