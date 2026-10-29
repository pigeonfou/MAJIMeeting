# Canal MAJIMeeting DEV — Windows sans compilation

## Première installation

1. Télécharger **MAJIMeeting-DEV-Setup.zip** depuis une release dont le nom commence par **MAJIMeeting DEV**. Extraire tout le ZIP dans un dossier, puis double-cliquer **Installer-DEV.cmd**. Ne pas lancer les fichiers depuis l'aperçu ZIP.
2. Python3.11 x64 avec le lanceur `py` est requis (déjà utilisé pour la préparation Community-1). Aucun administrateur requis. Le script crée un environnement permanent, télécharge le code validé et crée les raccourcis sur le Bureau et dans le menu Démarrer.
3. La première installation télécharge les bibliothèques Python/Qt/Whisper : elle peut prendre plusieurs minutes. Les modèles Whisper et Community-1 existants ne sont pas retéléchargés. La fenêtre affiche la préparation ; un message confirme la fin.
4. Pour retrouver les réunions existantes, fermer MAJIMeeting habituel ET DEV, puis lancer **Copier mes reunions vers DEV**. Le catalogue SQLite et les audios sont copiés dans un nouveau dossier DEV. Prévoir l'espace disque correspondant aux audios. Les originaux et les anciens jeux DEV ne sont ni écrasés ni supprimés.
5. Lancer **MAJIMeeting DEV**. Le titre affiche DEV et le commit réellement exécuté. Les chemins de modèles et paramètres GPU habituels sont repris une fois, puis les paramètres DEV évoluent indépendamment.

## Utilisation

- **MAJIMeeting DEV** : lance la version installée, sans recherche réseau de mise à jour. Les traitements restent locaux, sous réserve que leurs modèles soient présents.
- **Mettre a jour et lancer MAJIMeeting DEV** : fermer DEV, puis lancer le raccourci. Il récupère le dernier commit source publié par la CI et ouvre la nouvelle version après vérification. Aucune commande à saisir. La fenêtre de progression se ferme après le lancement. Une modification du code seul réutilise les dépendances ; aucun modèle téléchargé.
- **Revenir a la version DEV precedente** : fermer DEV, puis lancer le raccourci. La version précédente est vérifiée et contrôlée avant activation ; relancer DEV. Cela fonctionne sans téléchargement si cette version et son environnement sont toujours présents. Les versions doivent partager le format de données déclaré compatible.
- **Copier mes reunions vers DEV** : refaire une copie si nécessaire. Un nouveau dossier est créé à chaque copie ; le précédent reste disponible sur disque.

Une mise à jour, un retour arrière ou une copie est refusé si DEV est ouvert, même au repos. Ce choix empêche tout changement pendant un enregistrement, traitement ou une lecture. Le catalogue habituel doit également être fermé pendant sa copie. Les verrous système se libèrent après arrêt brutal ; les verrous de catalogue utilisent le même mécanisme Qt que l'application.

## Organisation locale

Par défaut, `%LOCALAPPDATA%\MAJIMeeting-DEV` contient :

| Emplacement | Rôle |
|---|---|
| `launcher.py` | Lanceur stable suivi par les raccourcis |
| `state.json` | Commit, environnement et catalogue actifs ; version précédente |
| `versions/<commit>` | Code vérifié d'une révision exacte |
| `runtimes/<préfixe16de-l’empreinte>` | Environnement Python permanent associé aux dépendances figées |
| `data` | Catalogue DEV initial vide |
| `datasets/copie-<identifiant>` | Copies indépendantes des réunions habituelles |
| `logs` et `dev-errors.log` | Journaux de lancement et d'erreurs |

Les modèles restent sous leurs chemins existants, généralement `%LOCALAPPDATA%\MAJIMeeting\models`. Le runtime Community-1 déjà préparé peut être lu pour les analyses. Si le bouton d'installation de dépendances est utilisé depuis DEV, il prépare un runtime séparé dans `%LOCALAPPDATA%\MAJIMeeting-DEV\diarization-runtime`, puis le sélectionne pour DEV ; il ne réinstalle pas le runtime habituel.

Le canal DEV utilise des paramètres Qt séparés. Les réglages de capture et les données de l'application habituelle ne sont pas modifiés. Les corrections et réunions créées dans DEV ne sont pas automatiquement fusionnées vers le catalogue habituel.

## Publication et validation

Le workflow **DEV source channel** exécute les tests Windows/Linux, Ruff, démarrage Qt, éditeur/lecture et WhisperCPU/alignement réel hors ligne. Il construit un ZIP source et son manifeste, sans PyInstaller ni Inno Setup. Si le bootstrap ou ses dépendances changent, il teste en plus une installation réelle depuis Windows PowerShell5, dans un chemin contenant des espaces, puis le lanceur DEV.

Une release `dev-<commit40caractères>` n'est publiée qu'après succès de la CI sur main. L'archive est liée au commit, aux empreintes SHA-256 des fichiers, à sa propre empreinte et à une liste de dépendances figées. Les mises à jour vérifient ces informations, refusent les chemins sortants/fichiers inattendus et n'activent la version qu'après un contrôle de démarrage. Une erreur laisse la sélection précédente active. La confiance repose sur le dépôt GitHub et sa connexion HTTPS ; il ne s'agit pas d'une signature éditeur Windows.

Les versions des dépendances sont fixées dans `requirements-dev-runtime.txt`. Leur empreinte détermine le dossier d'environnement : un simple changement du code ne réinstalle rien. Changer ce fichier déclenche la préparation d'un autre environnement, sans écraser le précédent. L'installation d'un environnement neuf nécessite une connexion aux index de paquets ; un lancement et un retour arrière compatibles n'en nécessitent pas.

Le workflow historique **CI** conserve les constructions d'installateurs pour les changements de packaging, version/dépendances du projet, scripts de promotion ou lancement manuel sur main. Les changements ordinaires de `src/` et `tests/` passent uniquement par le canal DEV. Cette livraison0.2.12 modifie la version et les workflows : la construction complète est donc exécutée une dernière fois pour valider la coexistence. Ne pas incrémenter la version de distribution à chaque correctif DEV : le commit identifie chaque essai.

## Délais et limites

La préparation initiale reste la phase lourde. Les livraisons suivantes portent sur un petit ZIP et un contrôle de démarrage ; les tests automatiques restent nécessaires avant publication. Aucun délai de quelques secondes entre demande et version validée n'est garanti. Le changement de canal ne modifie pas les performances des moteurs IA.

Le retour arrière restaure le code et l'environnement, pas une sauvegarde automatique du catalogue. Les migrations actuelles sont additives ; toute évolution destructive du format devra prévoir une migration/sauvegarde distincte et un changement du numéro de compatibilité. Aucune purge automatique des anciennes versions, environnements ou copies audio dans cette première version.
