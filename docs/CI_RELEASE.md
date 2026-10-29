# Validation et publication sans reconstruction

La CI se déclenche sur les PR vers main, les push vers main et les demandes manuelles.
Un push sur une branche de développement ne lance plus une seconde chaîne en parallèle.
Une nouvelle révision de PR annule son ancienne exécution ; les publications main ne
sont pas annulées par ce mécanisme. Les dépendances téléchargées par pip sont mises en cache.

## PR

Une seule chaîne exécute les tests Windows/Linux, les contrôles Qt et les inférences
réelles CPU, puis construit l'application et l'installateur Windows. L'installateur est
installé et contrôlé avant création d'un manifeste comprenant commit, arbre Git, version,
run/attempt GitHub Actions et SHA-256 de l'EXE. Le manifeste est disponible séparément et
avec l'installateur. Les poids de test ne sont pas inclus dans l'artefact publié.

## Fusion dans main

Un job court cherche la CI réussie de la PR fusionnée, dans le même dépôt, avec le même
head de PR. Il vérifie les métadonnées et l'identité exacte des arbres Git du commit testé
et du commit fusionné, y compris workflows, tests et documentation. Les identifiants des
commits peuvent différer ; leur contenu doit être identique. Les artefacts de forks ne
sont pas promus par ce chemin. Le manifeste téléchargé est traité comme une donnée :
aucun programme ou script contenu dans l'artefact n'est exécuté par la publication.

Si l'artefact est utilisable et le contenu identique, tests et construction sont sautés
sur main. La publication télécharge l'installateur existant et vérifie son SHA-256, le run,
l'arbre source et l'identité du manifeste approuvé. Elle publie exactement ces octets.
Sinon, les contrôles et la construction complète sont effectués sur main avant publication.
Un push direct de code dans main utilise donc aussi ce chemin de validation complet.
Les commits de documentation avec [skip ci] ne publient pas de nouvelle préversion.

Le tag est `vVERSION-preview.NUMERO_RUN_DE_CONSTRUCTION` : en cas de promotion, c'est le
numéro de la CI de PR, pas celui du job court de publication. Le tag cible le commit main.
Le manifeste et les notes fournissent la référence du run ayant construit le fichier.
Une réexécution de publication vérifie le tag et les octets déjà publiés sans les écraser.
Si le fichier diffère, elle échoue au lieu de remplacer une release existante.

## Contrôles

`node --test .github/scripts/promotion.test.cjs` vérifie les refus pour arbre changé,
head obsolète, CI en échec, fork, autre workflow, tentative ou PR incohérente, source
arbitraire, chemin de fichier non autorisé et altération d'EXE/manifeste.
La validation de bout en bout doit montrer une seule construction sur la PR puis les jobs
test et windows-package sautés sur main, avec publication de l'empreinte issue de cette PR.
La première exécution sans cache n'est pas une mesure de gain des dépendances.

## Première validation de bout en bout

PR nº 9 : [construction validée 40756745079](https://github.com/pigeonfou/MAJIMeeting/actions/runs/40756745079),
76 tests Python et 11 tests Node par système, tests de l'installateur réussis.
Après fusion, [run main 40757819354](https://github.com/pigeonfou/MAJIMeeting/actions/runs/40757819354) :
plan et publication réussis en 31 secondes, test et windows-package sautés. La préversion
v0.2.6-preview.42 publie l'EXE de cette PR et son manifeste ; digest GitHub de l'asset
identique au SHA-256 enregistré et vérifié avant publication. Aucun changement des
fonctions de l'application ni besoin de réinstaller pour cette modification de CI.


## Canal source DEV (0.2.12)

Le workflow `dev-channel.yml` prend en charge les changements courants sans PyInstaller. Voir [DEV_CHANNEL.md](DEV_CHANNEL.md). Le workflow historique `ci.yml` ne démarre automatiquement que pour packaging, pyproject (version/dépendances), son propre YAML et les scripts de promotion/manifeste. Un lancement manuel sur main construit et publie aussi un installateur. Les corrections DEV gardent la version de distribution et sont identifiées par commit ; une montée de version reste une publication d'installateur volontaire.

Les dépendances du canal Windows sont figées séparément ; le bootstrap n'est réinstallé en CI que si les fichiers du gestionnaire/requirements changent. Les tests et vérifications source, interface et inférence réelle continuent sur chaque changement de code. Une mise à jour d'environnement sur PC se fait dans un nouveau dossier par empreinte, avec activation seulement après succès.
