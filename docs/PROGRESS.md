# Progression MAJIMeeting

Mise à jour : 28 octobre 2026.

## État global
Jalon 2 : vitesse et résultats de transcription validés par l'utilisateur sur la réunion
testée avec la configuration GPU de référence ci-dessous. Validation stable et essais
matériels reportés toujours à réaliser.
Première partie du jalon 3 (éditeur, noms manuels, historique et réécoute) validée
par retour utilisateur sur la version 0.2.4. Diarisation automatique à réaliser.
Jalon 1 : socle fonctionnel validé partiellement sur le PC utilisateur ; essais complémentaires
conservés à réaliser. Aucune release stable validée.
Le socle initial au commit `32caf8a` a été intégralement relu (neuf fichiers).
La branche `develop/recording-foundation` existante a été reprise sans réinitialisation.

## Réalisé
- Catalogue SQLite des réunions : titre, date UTC, état et erreur persistante.
- Interface PySide6 : sources multiples, démarrage/arrêt, historique, thèmes clair/sombre.
- Entrées WASAPI et sorties loopback via PyAudioWPatch ; aucune dépendance GPU.
- Pistes PCM 16 bits séparées aux fréquences et nombres de canaux des périphériques.
- Callbacks sans accès disque ; file bornée et worker d'écriture indépendant de Qt.
- Fragments WAV autonomes d'une seconde, écriture temporaire, fsync et renommage.
- Horodatage initial approximatif par piste ; métadonnées par fragment.
- Récupération du catalogue après interruption ; export des fragments finalisés en WAV.
- Verrou d'instance pour éviter deux captures sur le même catalogue.
- CI Linux/Windows, démarrage Qt, construction PyInstaller et installateur Inno Setup,
  essai d'installation et démarrage du binaire installé, artefact téléchargeable.

- J2 : import WAV/MP3/FLAC/M4A en streaming, conservation de l'original.
- J2 : transcription française locale faster-whisper par lots bornés, choix CPU/CUDA
  et quantification, modèle large-v3 via téléchargement explicite ou dossier local.
- J2 : historique des tentatives, sauvegarde incrémentale des segments horodatés,
  annulation coopérative, récupération de l'état après arrêt forcé et exports TXT/JSON.

## Jalons
- Réalisé avec validation partielle : J1 enregistrement ; essais complémentaires à réaliser.
- En cours : validation J2 et J3 éditeur, correction manuelle et lecture synchronisée.
- À réaliser : suite J3 diarisation automatique ; J4 comptes rendus ;
  J5 exports documentaires/sauvegardes ; J6 validation complète et release stable.

## Tests exécutés
- Socle : CI GitHub initiale réussie sur `32caf8a` (runs 40665214004 et 40665505399).
- Local Linux Python 3.12 : 12 tests réussis ; Ruff réussi ; démarrage Qt offscreen réussi.
- Tests : catalogue, interruption, export bit à bit, fragments partiels, deux sources,
  échec d'ouverture, incident audio, PCM invalide, conservation d'un export existant,
  récupération et changement de thème dans l'interface, saturation et disque plein simulés.
- Première CI Linux en échec : bibliothèque native Qt `libEGL.so.1` absente du runner.
  Correction : installation explicite de libegl1 et libopengl0 avant les tests.
- CI de la PR nº 1 réussie : run [40666516564](https://github.com/pigeonfou/MAJIMeeting/actions/runs/40666516564).
- CI de main réussie : run [40667024555](https://github.com/pigeonfou/MAJIMeeting/actions/runs/40667024555).
  Sous Windows et Linux : 12 tests, Ruff et démarrage Qt réussis. Construction Windows,
  démarrage du binaire empaqueté, compilation Inno Setup, installation silencieuse et
  démarrage du programme installé réussis. Publication de la préversion réussie.
- Retour utilisateur du 28 octobre 2026, sur la préversion v0.1.0-preview.9 :
  sélection microphone + loopback OK ; capture d'au moins deux minutes, silence inclus,
  interface réactive OK ; export/écoute des deux pistes distinctes, durée et intelligibilité OK ;
  arrêt forcé et récupération/export des fragments OK.
- À réaliser : débranchement, réunion longue, mesure de dérive/charge, fonctionnement sans
  réseau, désinstallation/conservation des données. Ces essais n'ont pas été déclarés réussis.
- Matériel confirmé par capture utilisateur : Windows x64, Intel i7-11800H,
  32 Go RAM et RTX 3080 Laptop 16 Go. Aucun identifiant matériel personnel conservé ici.
- J2 local Linux Python 3.12 : 25 tests réussis, Ruff et démarrage Qt offscreen réussis.
  Import réel WAV/MP3/FLAC/M4A testé ; moteur simulé pour les tests de persistance,
  annulation, horodatage et absence de téléchargement implicite.
- Inférence locale avec vrais poids tiny en CPU/int8, VAD et chaîne import/transcription
  avec HF_HUB_OFFLINE=1 : réussie. Incompatibilité PyAV 19/faster-whisper détectée puis
  corrigée par une contrainte av<16 ; résultat réussi avec PyAV 15.1.0.
- CI J2 de la [PR nº 2](https://github.com/pigeonfou/MAJIMeeting/pull/2) réussie :
  [run 40683437589](https://github.com/pigeonfou/MAJIMeeting/actions/runs/40683437589).
  25 tests sur Windows et Linux ; inférence CPU réelle et VAD hors ligne réussis ;
  construction, installation et inférence du programme Windows installé réussies.
  Premier passage Windows : test d’export corrigé pour relire explicitement UTF-8.
- Qualité de transcription large-v3 et exécution CUDA sur RTX : à réaliser.

## Limites connues
- Une coupure brutale perd les données non encore finalisées (tampon, file et fragment
  temporaire) ; les fragments déjà renommés restent utilisables. Aucune garantie contre
  la panne matérielle ou un système de fichiers endommagé.
- Les pistes utilisent des horloges indépendantes : pas de correction de dérive ni de
  synchronisation précise ; les décalages initiaux sont approximatifs.
- Toute alerte PortAudio ou saturation marque la réunion en échec ; les pistes sauvées
  restent exportables. Pas de reprise automatique d'un périphérique débranché.
- Export WAV classique limité à 4 Go ; conserver les fragments pour les très longues pistes.
- Test de démarrage/installation en CI sans matériel audio : ne valide pas la capture réelle.
- J2 : import local et transcription différée intégrés ; modèle large-v3 téléchargé séparément
  depuis le bouton dédié. Inférence exclusivement locale, CPU int8/float32 ou CUDA
  int8_float16/float16. Bibliothèques CUDA non incluses dans l'installateur.
- Transcription par lots audio de cinq minutes, pistes traitées successivement ; frontière
  de lot sans recouvrement, à évaluer sur la qualité des mots à la jonction.
- Annulation coopérative : attend le chargement modèle ou la fin du segment en cours.
  Téléchargement des poids annulable et reprenable depuis le bouton ; délais réseau explicites.
- Les imports conservent l'original et décodent la première piste audio en mono 16 kHz.
- Aucun locuteur détecté automatiquement : les noms track-XX désignent des sources, pas des personnes.
  Noms attribuables manuellement et corrections disponibles ; diarisation et compte rendu à venir.
- Prototype sans signature de code ; traitement CUDA observé sur le PC utilisateur,
  fin complète et qualité large-v3 encore à confirmer.

## Prochaines actions
1. Valider les corrections, la réécoute et la transcription complète sur le PC utilisateur.
2. Intégrer pyannote Community-1 et les attributions des locuteurs (suite J3).
3. Réaliser ultérieurement les essais J1 restants, sans bloquer la suite du développement.
4. Évaluer les frontières de lots et la dérive des sources avant validation stable.

## Références
- Base : `32caf8a0512db0a9629c5e53756630edc64917c9`.
- [PR nº 1](https://github.com/pigeonfou/MAJIMeeting/pull/1) fusionnée.
- Implémentation : `84becbb` ; tests/CI : `6731a18` ; publication : `bef068c`.
- Fusion main : `fcd1cd8f5fb47a4f62ba901ce81f58ecc7b11a35`.
- [Préversion v0.1.0-preview.9](https://github.com/pigeonfou/MAJIMeeting/releases/tag/v0.1.0-preview.9) : installateur disponible, 28 octobre 2026.
- Aucune release stable publiée ; essais audio matériels complémentaires toujours à réaliser.

## Références du jalon 2

- [PR nº 2](https://github.com/pigeonfou/MAJIMeeting/pull/2) fusionnée.
- Implémentation : `1ce4ccf` ; correction du test UTF-8 Windows : `0d8e9de`.
- Fusion : `1440a1af995acf168603d4271a42bf39f4212c71`.
- [CI main J2](https://github.com/pigeonfou/MAJIMeeting/actions/runs/40684183125) réussie :
  25 tests par système, Ruff, interface Qt, inférence CPU réelle/VAD hors ligne ;
  construction et installation Windows, puis inférence dans le programme installé réussies.
- [Préversion v0.2.0-preview.14](https://github.com/pigeonfou/MAJIMeeting/releases/tag/v0.2.0-preview.14)
  publiée le 28 octobre 2026. Poids de large-v3 à télécharger séparément.
- Le jalon 2 reste en validation utilisateur : qualité française large-v3, CUDA/RTX,
  longues réunions et frontières de lots encore à vérifier. Les essais J1 restants
  demeurent « à réaliser » ; ils ne sont pas assimilés à des succès.

## Correctif du téléchargement — 28 octobre 2026

- Signalement utilisateur : clic sur Télécharger sans activité réseau visible, application
  semblant bloquée. La cause exacte sur son PC n'est pas encore isolée.
- Lacune identifiée : aucun détail de progression et aucun test du téléchargement dans le
  programme installé ; le précédent test d'inférence utilisait des poids récupérés par Python.
- Remplacement du chemin SDK de téléchargement par HTTPS en streaming, sans charger
  le moteur IA ; connexion/lecture avec délais, progression en Mo/pourcentage, annulation,
  reprise HTTP Range, vérification SHA-256/Git blob et journal local `download.log`.
- Point d'entrée PyInstaller protégé par `multiprocessing.freeze_support()`.
- Local : 33 tests réussis, Ruff réussi ; vrai téléchargement tiny avec contrôle d'intégrité
  réussi et inférence CPU hors ligne avec les fichiers téléchargés réussie.
- CI : téléchargement réel depuis l'exécutable installé ajouté, puis inférence hors ligne.
  CI et publication réussies ; références ci-dessous.
- Les autres essais matériels précédemment marqués à réaliser conservent ce statut.

## Références du correctif 0.2.1

- [PR nº 3](https://github.com/pigeonfou/MAJIMeeting/pull/3) fusionnée.
- Implémentation : `638e9647b1eff4b0ea1d9ada8e63f2a6463da18e` ; fusion : `7fdddbbc4bf9fdb6a6ca6abaee68cdd06787cd33`.
- [CI de la PR](https://github.com/pigeonfou/MAJIMeeting/actions/runs/40692971389) et
  [CI main](https://github.com/pigeonfou/MAJIMeeting/actions/runs/40693974286) réussies.
- 33 tests sur Windows et Linux, Ruff, démarrage Qt, téléchargement tiny réel avec
  vérification d'intégrité et inférence CPU hors ligne réussis.
- Installation Windows, téléchargement réel par l'exécutable installé puis inférence
  hors ligne avec les mêmes fichiers réussis. Journaux de téléchargement conservés en artefacts CI.
- [Préversion v0.2.1-preview.17](https://github.com/pigeonfou/MAJIMeeting/releases/tag/v0.2.1-preview.17) publiée le 28 octobre 2026.
- À confirmer sur le PC utilisateur : téléchargement complet large-v3 avec ce correctif.
  Le signalement initial n'est pas déclaré résolu sur son matériel sans son retour.

## Correctif CUDA — 28 octobre 2026

- Capture utilisateur : `Library cublas64_12.dll is not found or cannot be loaded`.
  Le chargement de la bibliothèque CUDA échoue ; cela ne démontre pas un modèle corrompu.
- Vérification préalable des DLL NVIDIA et du pilote, découverte des dossiers CUDA 12/cuDNN 9
  et champ facultatif pour les bibliothèques déjà installées.
- Repli CPU/int8 autorisé par une case visible ; moteur GPU libéré avant reprise CPU.
  Les erreurs pendant l'itération des segments sont couvertes, sans duplication des
  résultats ni modification d'une tentative antérieure. Annuler ne relance pas le CPU.
- Historique enrichi avec appareil/quantification effectifs et raison du repli.
- Local : 42 tests réussis et Ruff réussi. Inférence réelle CPU et repli après DLL
  manquante simulée réussis avec le modèle tiny. CI et installateur Windows réussis ; références ci-dessous.
- Les DLL CUDA/cuDNN restent à installer séparément depuis NVIDIA si l'utilisateur veut
  activer le GPU. La reprise CPU n'est pas une validation de l'accélération RTX.
- Les autres essais matériels en attente restent à réaliser.


## Références du correctif CUDA 0.2.2

- [PR nº 4](https://github.com/pigeonfou/MAJIMeeting/pull/4) fusionnée.
- Implémentation : `f6498e2` ; priorité du dossier choisi : `d6aff7f` ;
  correction de la borne de dépendance PyAudioWPatch lors du changement de version : `eefec9f`.
- Fusion : `692773ff574d7cd7f0c7e7bc145341b57d7b5974`.
- [CI PR](https://github.com/pigeonfou/MAJIMeeting/actions/runs/40706044239) et
  [CI main](https://github.com/pigeonfou/MAJIMeeting/actions/runs/40707043390) réussies.
- 42 tests par système, Ruff, démarrage Qt, téléchargement et inférence CPU réels réussis.
  Installation Windows et reprise sur vrai moteur CPU après DLL manquante simulée réussies.
- [Préversion v0.2.2-preview.24](https://github.com/pigeonfou/MAJIMeeting/releases/tag/v0.2.2-preview.24) publiée le 28 octobre 2026.
- À confirmer sur le PC utilisateur : reprise CPU avec large-v3, puis chargement des
  bibliothèques NVIDIA et accélération réelle RTX. Le GPU n'est pas déclaré validé.

## Correctif des limites temporelles — 28 octobre 2026

- Retour utilisateur : la configuration CUDA a franchi l'erreur de bibliothèque et le
  traitement cuda/float16 affiche 1200 s traitées, puis échoue sur « Horodatage de
  transcription invalide ». Validation GPU partielle ; la réunion n'est pas encore validée.
- Contrôle précédent trop strict : un segment dépassant la durée du lot arrêtait la tâche.
  Les segments qui recoupent l'audio sont désormais bornés à sa durée réelle ; les sorties
  hors audio, sans durée ou aux temps non finis/inversés sont écartées et auditées.
- Avertissements persistants avec temps et texte bruts, compteurs et consultation dans
  l'interface ; audit complet exporté dans JSON. Aucune parole manquante n'est inventée.
- Les segments/tentatives précédents sont conservés. Le repli GPU vers CPU ne nettoie
  que les segments et avertissements de la tentative courante pour éviter les doublons.
- Local : 57 tests réussis, Ruff et démarrage Qt réussis. Régression synthétique reproduite
  après quatre lots de cinq minutes et un dernier lot court. Tests des bornes, NaN/infini,
  texte vide, migration additive de la base et affichage/export de l'audit réussis.
- Inférence CPU réelle avec tiny et contrôle de régression local réussis. CI et exécutable
  Windows installé validés ; références ci-dessous.
- À confirmer sur la réunion utilisateur : fin complète de la transcription et vérification
  des passages signalés. Les autres essais matériels en attente gardent leur statut.

## Références du correctif d'horodatage 0.2.3

- [PR nº 5](https://github.com/pigeonfou/MAJIMeeting/pull/5) fusionnée.
- Implémentation : `1772b46743159d3ba819fb4a5a89ecfd838a35b6` ; fusion : `c14faa05c89c305d706f5c20c278e3950daec81f`.
- [CI PR](https://github.com/pigeonfou/MAJIMeeting/actions/runs/40718027000) et
  [CI main](https://github.com/pigeonfou/MAJIMeeting/actions/runs/40719072803) réussies.
- 57 tests sur Windows et Linux, Ruff, démarrage Qt, vraie inférence tiny CPU et repli CPU
  après DLL manquante simulée réussis.
- Installation Windows et régression des limites après 1200 secondes, avec un décodeur
  simulé déterministe, réussies dans l'exécutable installé.
- [Préversion v0.2.3-preview.27](https://github.com/pigeonfou/MAJIMeeting/releases/tag/v0.2.3-preview.27) publiée le 28 octobre 2026.
- Les poids, réglages CUDA, pistes et tentatives précédentes sont conservés. Relancer une
  nouvelle tentative de la réunion existante ; elle repart du début, sans réimporter l'audio.
- À confirmer sur la réunion utilisateur : traitement complet et vérification des
  avertissements. Les tests automatisés ne prouvent pas l'exactitude des paroles reconnues.

## Jalon 3 — première partie, éditeur et réécoute

- Reprise sur main `742ab95e6a3fec48fd9c60d2a599d01e52c30c58`, sans portage de Biscotti.
- Corrections et noms saisis par passage, historique SQLite additif, original et temps
  conservés ; restauration auditable ; exports TXT/JSON utilisant la version corrigée.
- Lecteur Qt Multimedia : extrait local borné à 60 s, préparation dans un worker,
  conservation des décalages et des trous entre fragments. Aucune dépendance IA chargée.
- Local : 61 tests réussis ; Ruff réussi ; test réel du décodeur WAV Qt et de l'éditeur
  réussi sans sortie audio physique. Validation Windows automatisée obtenue, voir références.
- CI étendue au décodage Qt et au test de l'éditeur dans le programme Windows installé.
- À réaliser : écoute et corrections sur le PC utilisateur, tests matériels J1 restants,
  fin complète/qualité de la transcription de la réunion après correctif 0.2.3.
- Prochaine partie J3 : pyannote Community-1 local, gestion des locuteurs détectés et
  chevauchements. Aucun intervenant n'est détecté automatiquement dans cette préversion.
- Les comptes rendus sourcés, exports documentaires et validation stable restent à réaliser.

- Premier passage CI J3 : import de Qt Multimedia impossible sur le runner Linux
  faute de `libpulse.so.0`. Ajout explicite de `libpulse0` au workflow ; CI suivante réussie.

## Références de l'éditeur et de la réécoute 0.2.4

- [PR nº 6](https://github.com/pigeonfou/MAJIMeeting/pull/6) fusionnée.
- Implémentation : `351dedc3693dea93d0ee86c3469cbcf5ed21c8ff` ; correctif CI :
  `0de531a9f20de558136fa20d752d313579c64ba2` ; arrêt de lecture au changement de
  passage : `040c6cb327496f44004afced7f3e06915f49c56e`.
- Fusion main : `b16eedc334ee328ecee906e2ce73364224160797`.
- [CI PR](https://github.com/pigeonfou/MAJIMeeting/actions/runs/40729013896) réussie :
  61 tests Windows et Linux, Ruff, démarrage Qt, décodage WAV Qt et corrections persistantes,
  téléchargement réel du modèle tiny et inférence CPU hors ligne.
- Construction, installation, contrôles de l'éditeur/décodeur Qt et inférence CPU depuis
  le programme Windows installé réussis. Aucun test de sortie audio physique en CI.
- [CI main](https://github.com/pigeonfou/MAJIMeeting/actions/runs/40730116754) réussie :
  même validation Windows/Linux, installation et tests du programme installé réussis.
- [Préversion v0.2.4-preview.34](https://github.com/pigeonfou/MAJIMeeting/releases/tag/v0.2.4-preview.34)
  publiée le 28 octobre 2026 ; installateur Windows disponible.
- À confirmer sur le PC utilisateur : réécoute audible et correspondance texte/piste,
  corrections après mise à jour, fonctionnement hors réseau et fin de transcription large-v3.
  Les essais J1 reportés restent à réaliser. La diarisation automatique n'est pas intégrée.

## Retour utilisateur et optimisation GPU — 28 octobre 2026

- Utilisateur : « Les intégrations de la version 0.2.4 sont validées ». Éditeur, noms manuels,
  historique et réécoute considérés validés sur son PC. Ce retour ne valide pas à lui seul
  les essais J1 reportés, la qualité complète large-v3 ou la future diarisation automatique.
- Optimisation de transcription autorisée avant la suite J3 : traitement par lots GPU,
  taille 8 proposée, profil Qualité beam 5 conservé et profil Rapide beam 1 optionnel.
- Mode séquentiel conservé ; réduction graduelle des lots en cas d'erreur mémoire GPU,
  libération du pipeline avant reprise et remplacement des seuls résultats de cette tentative.
- Métriques enregistrées par reprise : chargement, préparation, inférence/VAD, écriture,
  durée totale et secondes-pistes terminées. Affichage et export JSON ; aucune estimation
  de performances antérieures ou de gain RTX non mesuré.
- Local : 70 tests réussis ; tests des paramètres, horodatages, annulation, erreurs non GPU,
  réduction mémoire, absence de doublons et libération avant reprise réussis. Ruff réussi.
- Test réel tiny CPU par lots (deux requêtes réellement encodées ensemble), VAD et chaîne
  de production hors ligne réussis en local ; éditeur/décodage Qt réussi. CI de PR et
  programme Windows installé validés ; références ci-dessous.
- Gain RTX 3080/large-v3, qualité française et comparaison float16/int8_float16 à réaliser.
- Les essais matériels J1 restants demeurent à réaliser. Suite J3 : pyannote Community-1.

## Références de l'optimisation 0.2.5

- [PR nº 7](https://github.com/pigeonfou/MAJIMeeting/pull/7) fusionnée.
- Implémentation : `36f1d6d5a65c89d924068ef028fff741d66964a4` ; fusion :
  `6a7fd68216f7a07b2f3d3ba5596eb3d2d2e1fdde`.
- [CI PR](https://github.com/pigeonfou/MAJIMeeting/actions/runs/40734280487) réussie :
  70 tests Windows/Linux, Ruff, démarrage Qt, décodage audio, vrai lot de deux requêtes
  tiny CPU et VAD hors ligne réussis.
- Construction, installation, téléchargement réel tiny et contrôles d'inférence par lots,
  éditeur et décodeur Qt depuis le programme installé réussis.
- Aucun benchmark de performance RTX ou de qualité large-v3 en CI. Aucun gain chiffré
  sur le PC utilisateur annoncé avant mesure.
- [CI main](https://github.com/pigeonfou/MAJIMeeting/actions/runs/40735297009) réussie :
  mêmes tests Windows/Linux et contrôles de l'application Windows installée réussis.
- [Préversion v0.2.5-preview.37](https://github.com/pigeonfou/MAJIMeeting/releases/tag/v0.2.5-preview.37)
  publiée le 28 octobre 2026 ; installateur Windows disponible et artefact vérifié présent.
- Prochain essai utilisateur : même réunion, CUDA et quantification identiques, comparer
  séquentiel puis lots de 8 en Qualité ; vérifier durée et passages. Rapide et float16 à
  comparer séparément. Les métriques ne certifient pas l'exactitude du texte reconnu.
## Revalidation 0.2.5 et mesures RTX fournies par l'utilisateur

Le 28 octobre 2026, nouvelles captures de la même durée source : 1504,4 secondes-pistes.
Réglages CUDA et profil relevés dans l'historique effectif, traitements terminés en une
tentative, sans repli CPU visible.

| Calcul effectif | Profil | Total (s) | Chargement (s) | Inférence/VAD (s) | Ajustements / rejets |
|---|---|---:|---:|---:|---|
| int8_float16, séquentiel | Qualité, beam 5 | 166,7 | 10,5 | 154,0 | 1 / 0 |
| int8_float16, lots 8 | Qualité, beam 5 | 92,6 | 11,6 | 74,2 | 2 / 0 |
| int8_float16, lots 16 | Qualité, beam 5 | 88,1 | 16,1 | 70,2 | 1 / 0 |
| float16, lots 16 | Qualité, beam 5 | 77,4 | 7,3 | 68,2 | 1 / 0 |
| float16, lots 16 | Rapide, beam 1 | 43,2 | 6,2 | 35,1 | 2 / 0 |

Mesures observées sur les captures utilisateur, non reproduites sur une RTX dans notre
environnement. Un seul résultat relevé par configuration ; variations de chargement et
de contexte non contrôlées. La comparaison n'est pas un score de qualité du français.
Le résultat le plus rapide représente environ 74 % de temps total en moins que le
séquentiel relevé ; vérifier texte et avertissements avant de le retenir par défaut.

À la demande de retest de la version actuelle :
- 21 fichiers source/tests/configuration comparés aux empreintes GitHub de main
  `36492c287cca45f572351d017de1cc855fdff3d3` : aucune différence.
- Revalidation locale Linux : 70 tests réussis, Ruff réussi, démarrage Qt et test de
  l'éditeur/décodage WAV Qt réussis.
- Nouveau téléchargement réel tiny avec contrôle d'intégrité réussi ; inférence CPU
  hors ligne, lot réel de deux requêtes, VAD et chaîne de production réussis.
- CI Windows/Linux de référence
  [40735297009](https://github.com/pigeonfou/MAJIMeeting/actions/runs/40735297009)
  revérifiée : succès sur `6a7fd68216f7a07b2f3d3ba5596eb3d2d2e1fdde`.
  Cette consultation ne constitue pas une nouvelle exécution Windows.
- CTranslate2 détecte zéro GPU CUDA ici. Aucun test Flash Attention ni de concurrence
  à deux workers GPU réalisé. Ces pistes ne sont pas intégrées dans 0.2.5.
- Aucun code ni installateur modifié pour cette revalidation. Les autres essais matériels
  reportés gardent leur statut.


## Préparation des essais GPU avancés — 0.2.6

- Clarification utilisateur : demande d'une nouvelle version à tester, pas d'un contrôle
  supplémentaire de 0.2.5. Base main `83a3234e6acd6be139c7c42eb552221ee5a567c4`.
- Options Flash Attention et deux workers désactivées par défaut ; deux workers natifs CT2
  partagent les mêmes poids, pipelines indépendants, requêtes réellement concurrentes.
- Deux fenêtres maximum, WAV isolés et nettoyage après fin des tâches ; retour prioritaire
  à un worker si VRAM insuffisante. Reprise sans Flash sur erreur explicitement liée à Flash.
- Fenêtres 5/10 minutes, lots jusqu'à 32, mesure des tailles natives et du remplissage.
  Temps cumulés des workers explicités ; mode effectif et adaptations visibles.
- Local : 75 tests réussis, Ruff, démarrage Qt et éditeur/décodage audio réussis.
  Vrais poids tiny : décodage concurrent sur deux workers CPU, VAD et chemin de production
  parallèle réussis. Les kernels Flash et le GPU RTX ne sont pas disponibles ici.
- Plantage Qt reproduit dans la suite au changement de thème ; nettoyage explicite des
  fenêtres natives entre tests ajouté. Suite complète réussie après correction.
- Interruption temporaire de l'environnement de développement pendant les notes de release,
  puis reprise des mêmes fichiers. Aucun résultat Windows présumé de ce fait.
- CI de PR Windows/Linux et tests du programme installé réussis ; références ci-dessous.
- À réaliser sur RTX : Flash/compatibilité, deux workers, remplissage, VRAM, stabilité,
  annulation et qualité des mêmes passages. Aucun gain RTX présumé.
- Essais J1 reportés et suite J3 pyannote à réaliser ; validations 0.2.4 conservées.

## Références des essais GPU avancés 0.2.6

- [PR nº 8](https://github.com/pigeonfou/MAJIMeeting/pull/8) fusionnée.
- Implémentation : `14f8786ceee9076cb974925dcf2a416593a958e9` ; fusion :
  `672a3d0656c661165b9df6678539a17b47f46c4d`.
- [CI PR](https://github.com/pigeonfou/MAJIMeeting/actions/runs/40748261712) réussie :
  75 tests Windows/Linux, Ruff, démarrage Qt, éditeur/décodage WAV, inférence tiny CPU
  et décodage natif concurrent sur deux workers réussis.
- Installateur construit et installé, puis contrôles d'éditeur, téléchargement réel tiny,
  inférence CPU hors ligne et deux workers depuis le programme installé réussis.
- Flash CUDA et performance RTX à mesurer par l'utilisateur ; aucun GPU disponible en CI.
- [CI main](https://github.com/pigeonfou/MAJIMeeting/actions/runs/40749010803) réussie :
  75 tests par système, construction et installation Windows, mêmes contrôles réels
  CPU/concurrence/éditeur depuis le programme installé réussis.
- [Préversion v0.2.6-preview.40](https://github.com/pigeonfou/MAJIMeeting/releases/tag/v0.2.6-preview.40)
  publiée le 28 octobre 2026 ; installateur présent et publié. Référence de comparaison :
  CUDA / float16 / lots 16 / Rapide / 1 worker / fenêtres 5 min / Flash non.
- À confirmer sur le PC utilisateur : activation Flash réellement acceptée, gain éventuel
  de deux workers et des grandes fenêtres, VRAM, annulation et qualité. Aucun résultat
  GPU expérimental déclaré réussi avant ce retour.

## Simplification des workflows — 28 octobre 2026

- Demande utilisateur : éviter les exécutions en double et publier l'installateur déjà testé.
- Push de branche supprimé des déclencheurs ; une seule chaîne complète par PR, anciennes
  révisions de PR annulées automatiquement. Cache pip ; téléchargement tiny inutilisé retiré
  du job de construction, téléchargement réel par le programme installé conservé.
- Manifeste après tests d'installation : arbre/commit source, run/attempt, version, SHA-256.
- Main réutilise un artefact de PR validé seulement si provenance, PR, CI et arbre Git
  fusionné correspondent. Sinon tests et construction complets. Publication vérifie les
  octets et le manifeste ; aucun script de l'artefact n'est exécuté pour promouvoir le fichier.
- Tag basé sur le numéro du run de construction ; publication idempotente sans écrasement.
- Local : 11 tests Node des contrôles de promotion réussis, YAML/structure du workflow
  vérifiés, Ruff et 75 tests Python réussis. Parcours PR puis promotion main à vérifier.
- Nouvelle capture utilisateur 0.2.6 : CUDA/float16, lots 16, Qualité/beam 5, 1 worker,
  Flash non, fenêtres 300 s : 1504,4 s-pistes en 84,9 s, 71,6 s inférence/VAD,
  6,9 s chargement ; 6 lots, 57 portions, remplissage 59,4 %, tailles 11×2, 12×2,
  10×1 et 1×1 ; un horodatage ajusté, aucun rejet. Ce n'est pas le profil Rapide à 43,2 s.
- Flash/two-workers/qualité restent en essais utilisateur ; aucun résultat supposé réussi.
- Capture suivante : Flash demandé mais refusé ; reprise CUDA sans Flash visible et
  calcul effectif Flash non. Profil Qualité/beam 5, 1 worker, fenêtres 300 s, lots 16 :
  85,6 s total, 71,6 s inférence/VAD, 11,9 s chargement, 2 tentatives ; même remplissage
  59,4 %, 6 lots et 57 portions. Aucun gain Flash mesuré puisque l'option a été désactivée.
  La cause native précise n'est pas déduite de ce seul message de reprise.
- Capture deux workers : CUDA/float16, lots 16, Qualité/beam 5, Flash non, fenêtres 300 s,
  workers effectifs 2 sans reprise ; 1504,4 s-pistes en 62,1 s (24,23×), chargement 6,2 s,
  préparation 0,9 s, inférence cumulée 94,8 s, écriture cumulée 1,2 s ; 6 lots, 57 portions,
  remplissage 59,4 %, un ajustement temporel, aucun rejet. Environ 27 % de temps total
  en moins que la référence 1 worker à 84,9 s, sur ce relevé unique en Qualité.
  Les temps d'inférence cumulés ne se comparent pas directement à la durée d'un worker.

## Validation de la publication sans reconstruction

- [PR nº 9](https://github.com/pigeonfou/MAJIMeeting/pull/9) fusionnée ; implémentation
  `7c26d7609f2785125f7ad99d40830769f1cc65ef`, lecture UTF-8/manifeste testé dans
  `667f1ae055597cd9be044489e88403ac8563da0e` ; fusion
  `17fde50506936bae9904d5f1786211f9d450c6ad`.
- [CI PR](https://github.com/pigeonfou/MAJIMeeting/actions/runs/40756745079) réussie :
  76 tests Python et 11 tests Node par système, contrôles Qt/inférence réels, construction,
  installation et contrôles de l'application installée réussis ; manifeste produit.
- Aucun workflow de push de branche observé. L'exécution obsolète 40756584503 a été
  annulée automatiquement à l'arrivée de la révision suivante.
- [CI main](https://github.com/pigeonfou/MAJIMeeting/actions/runs/40757819354) réussie :
  plan et publication réussis, jobs test et windows-package sautés. Durée du run main
  observée entre run_started_at et updated_at : 31 secondes. Une seule construction validée.
- [Préversion de vérification v0.2.6-preview.42](https://github.com/pigeonfou/MAJIMeeting/releases/tag/v0.2.6-preview.42)
  publiée depuis l'artefact du run de PR, avec son manifeste. SHA-256 de l'EXE publié
  identique à celui validé : `7a46119623dc4453895dbcb33c0845ae8142ca0aa81b7a85f7854523a18ebe5c`.
- Aucun changement fonctionnel de l'application ; aucune réinstallation nécessaire pour
  bénéficier de cette simplification des futurs builds. Les contrôles restent complets
  si l'arbre fusionné diffère ou si aucun artefact utilisable n'est disponible.


## Validation utilisateur de la configuration GPU — 28 octobre 2026

Retour explicite : « les résultats sont bons », après l'essai Rapide à deux workers
et fenêtres de dix minutes. Résultats jugés satisfaisants sur cette réunion ; aucune
mesure d'erreur de transcription ni validation universelle de toutes les réunions déduite.

Configuration de référence retenue pour ce PC :
- CUDA / float16 ; traitement par lots, taille maximale 16.
- Profil Rapide (beam 1), deux workers, fenêtres de 600 secondes.
- Flash Attention désactivé : le moteur installé l'a refusé lors de l'essai précédent.
- Référence utilisateur : 1504,4 secondes-pistes en 37,2 secondes ; une tentative,
  aucun avertissement d'horodatage, cinq lots natifs et 55 portions, remplissage 68,8 %.
  Chargement 5,5 s, préparation 1,0 s, inférence cumulée 33,5 s, écriture cumulée 1,6 s.
  Les temps d'inférence des deux workers restent cumulés et non comparables directement
  à ceux d'un worker unique.

Complément des mesures précédentes en float16, lots 16, Flash non :

| Profil | Workers | Fenêtres | Total | Inférence/VAD | Remplissage |
|---|---:|---:|---:|---:|---:|
| Qualité | 1 | 5 min | 84,9 s | 71,6 s | 59,4 % |
| Qualité | 1 | 10 min | 78,0 s | 70,7 s | 68,8 % |
| Qualité | 2 | 5 min | 62,1 s | 94,8 s cumulées | 59,4 % |
| Qualité | 2 | 10 min | 60,6 s | 98,7 s cumulées | 68,8 % |
| Rapide | 2 | 10 min | 37,2 s | 33,5 s cumulées | 68,8 % |

Les trois essais à fenêtres de dix minutes ci-dessus terminent sans avertissement temporel.
Un seul relevé par combinaison ; les écarts faibles ne sont pas considérés comme
statistiquement établis. Le gain du mode Rapide ne constitue pas à lui seul une preuve
d'exactitude ; le retour utilisateur valide l'acceptabilité du résultat sur cet audio.

Aucun réglage global imposé aux autres PC, aucun changement du code et aucun nouvel
installateur requis pour consigner ce retour. Réglages déjà mémorisés par l'application.
Prochaine fonctionnalité : suite du jalon 3, diarisation automatique Community-1 et
correction des locuteurs détectés. Les essais J1 reportés et les conditions de release
stable restent à réaliser.


## Tentative Flash Attention native Windows en cours

- Accord utilisateur du 28 octobre 2026 pour essayer une compilation personnalisée.
- Sources et workflow isolés dans [experiment/windows-flash](https://github.com/pigeonfou/MAJIMeeting/tree/experiment/windows-flash), sans remplacement de la distribution normale.
- Premier run [40770695390](https://github.com/pigeonfou/MAJIMeeting/actions/runs/40770695390) : configuration CMake en échec sur l'échappement du chemin Windows CUDA. Chemins normalisés dans `1df067293da8a9ffa558a5f7e31a099dbf83e382` et cache du compilateur ajouté.
- Deuxième run [40771641842](https://github.com/pigeonfou/MAJIMeeting/actions/runs/40771641842) : compilation native en cours au moment de cette note. Aucun moteur Flash ni installateur expérimental déclaré fonctionnel.
- CTranslate2 4.8.4 fixé au commit `5de572ef60b67a0276c5989ee73d0072808ff4c3`, CUDA 12.8.1, architecture 8.6, WITH_FLASH_ATTN=ON, CPU RUY. Sonde native ajoutée pour lire le flag réel de la DLL, sans modifier les kernels d'attention.
- 78 tests locaux avec le moteur standard réussis, Ruff et préparation des sources réussis. Les tests du moteur personnalisé, de son empaquetage et les essais sur RTX restent à réaliser.


## Flash expérimental Windows : installateur publié le 29 octobre 2026

- Compilation native réussie dans le run 40779226342 ; premier empaquetage bloqué par un import implicite de `majimeeting.__main__` non détecté par PyInstaller.
- Diagnostic conservé dans le lanceur (44e0e690), import explicite corrigé dans `24ebe0b1d3e7584b519bf065aece192e9369d953` sur `experiment/windows-flash`.
- [Run 40790610479](https://github.com/pigeonfou/MAJIMeeting/actions/runs/40790610479) intégralement réussi : moteur natif Flash vérifié, 78 tests Windows passés, Ruff réussi, inférence CPU réelle, construction/installation, sonde native dans l'EXE installé, démarrage Qt, éditeur/audio et inférence CPU de l'application installée réussis.
- [Préversion flash-v0.2.6-exp.6](https://github.com/pigeonfou/MAJIMeeting/releases/tag/flash-v0.2.6-exp.6) publiée avec installateur séparé et SHA-256.
- Version normale et moteur normal inchangés. Fermer l'application normale avant de lancer Flash expérimental : données et modèles partagés, verrou commun.
- À réaliser sur la RTX 3080 : même réunion et mêmes réglages avec Flash désactivé puis activé, vérifier le réglage réellement utilisé dans l'historique, qualité du texte, durée et VRAM. La CI sans GPU ne valide pas l'exécution CUDA des kernels Flash ni un gain de performance.


## Regroupement audio pour grands lots — fenêtres supplémentaires

- Référence matérielle utilisateur : version normale, CUDA/float16, lots 32, Rapide, deux workers, Flash désactivé, fenêtres 600 s : 34,6 s pour 1504,4 secondes-pistes ; remplissage 57,3 %, lots 32/21/12. Flash expérimental fonctionnel selon historique mais aucun gain démontré dans les comparaisons précédentes.
- Ajout demandé : fenêtres 15, 20, 25 et 30 minutes, en complément de 5 et 10. Choix mémorisé ; paramètres de génération et moteur standard inchangés.
- Objectif : réduire les fins de lots imposées par chaque fenêtre contiguë. Pas de mélange des pistes ni des coupures récupérées. Plus de RAM possible, moins de fenêtres pour les workers ; vitesse et qualité à comparer sur RTX.
- Tests locaux exécutés : 89 tests passés (suite normale, hors deux tests propres à la branche Flash), Ruff des fichiers modifiés réussi. Contrôles de conservation PCM, regroupement de 1250 s en une fenêtre, maintien des coupures et horodatages, modes un/deux workers et interface pour toutes les durées.
- Tests GitHub Windows/Linux et construction installateur : à exécuter avant publication. Essai GPU réel : à réaliser après installation, voir docs/GPU_BATCHING.md.


### Validation et publication des fenêtres 15/20/25/30 minutes

- [PR nº 10](https://github.com/pigeonfou/MAJIMeeting/pull/10) fusionnée dans `6234b2546d64d3d7932aa7526f5b16782097a9fa` ; source `c2c1d4a4614a738cda38eac92872d4f6476739fd`.
- [CI PR 40794119935](https://github.com/pigeonfou/MAJIMeeting/actions/runs/40794119935) réussie : tests Windows/Linux, contrôles Qt et inférence, construction et installation Windows. 89 tests Python Windows réussis, Ruff réussi.
- [Publication main 40794875450](https://github.com/pigeonfou/MAJIMeeting/actions/runs/40794875450) réussie ; [v0.2.6-preview.44](https://github.com/pigeonfou/MAJIMeeting/releases/tag/v0.2.6-preview.44) disponible avec le moteur standard et le manifeste de provenance.
- À réaliser : comparaison utilisateur sur RTX 3080 des fenêtres 10/15/20/25/30 minutes, lots 32 et Flash désactivé. Pas de gain GPU annoncé avant mesures.


## Reprise du jalon 3 — première intégration des interlocuteurs 0.2.7

- Optimisations conservées. Mesures utilisateur : lots32, fenêtres10min/deux workers 34,8 s (autre essai39,5s), 15min81,9s avec un ajustement, 20min36,4s, 25min38,4s avec un ajustement, 30min/deux workers39,2s et remplissage85,9%, 30min/un worker37,1s. Pas de changement automatique des réglages ; référence actuelle dix minutes/deux workers, Flash désactivé.
- Développé : lancement différé Community-1 CPU/CUDA dans un Python isolé ; préparation mono16kHz en streaming avec trous/origine conservés ; blocage des connexions pendant l'analyse, télémétries désactivées, annulation par arrêt du processus. Pas de modèle Torch résident avec Whisper.
- Tables additives : analyses/tours/attributions/noms historisés. Dernière analyse réussie affichée, erreurs/interruptions conservées, aucun remplacement partiel. Corrections manuelles prioritaires. Groupes indépendants par piste, passages multi-voix ou insuffisamment couverts signalés ; pas de découpage arbitraire du texte.
- Interface : configuration runtime/modèle, nombre de voix optionnel, renommage de groupe dans l'éditeur, provenance dans l'export JSON. Script et raccourci Windows de préparation du runtime utilisateur/modèle.
- Tests locaux : 102 tests normaux réussis, Ruff réussi ; smoke Qt éditeur/lecture incluant configuration et noms de groupe réussi. Aucun test avec poids réels Community-1 déclaré réussi.
- À exécuter : CI Windows/Linux, installation/import réel du runtime CPU, packaging/installation puis contrôles Qt/inférence. Validation Community-1 CUDA et hors ligne sur réunion représentative à réaliser après préparation autorisée du modèle. Limites initiales : 4h/piste, pas d'alignement mot à mot, noms non déduits automatiquement. Voir docs/DIARIZATION.md.


### Validation et publication de la première intégration J3

- [PR nº 11](https://github.com/pigeonfou/MAJIMeeting/pull/11) fusionnée dans `b25e8b8a886962478c3596bda0b0c1aea8d19ff9` ; source `3cae71879d7c4395a5148683fc90a4658ce624aa`.
- [CI PR 40842847791](https://github.com/pigeonfou/MAJIMeeting/actions/runs/40842847791) réussie : 102 tests Windows et suite Linux, Ruff, contrôle Qt éditeur/groupes/lecture, inférence Whisper CPU réelle, construction et installation Windows avec contrôles de l'EXE installé.
- Job diarization-runtime Windows réussi : installation réelle torch2.8.0+cpu/torchaudio2.8.0+cpu/torchcodec0.7.0/pyannote.audio4.0.7 et import Pipeline réussi. Aucun poids Community-1 utilisé ; CUDA absent sur le runner, ce qui est attendu.
- [Run main 40843827434](https://github.com/pigeonfou/MAJIMeeting/actions/runs/40843827434) réussi, [v0.2.7-preview.46](https://github.com/pigeonfou/MAJIMeeting/releases/tag/v0.2.7-preview.46) publiée.
- Prochaine validation utilisateur : installer0.2.7, préparer runtime/modèle via le raccourci fourni après acceptation HF, puis diarisation réelle CUDA/hors ligne d'une réunion à plusieurs voix ; consulter docs/DIARIZATION.md. Le jalon3 n'est pas déclaré terminé avant cet essai.


## Préparation intégrée de la diarisation 0.2.8

- Demande utilisateur après erreur NumPy manquant : deux boutons indépendants dans la configuration de diarisation, installation des dépendances et téléchargement de Community-1.
- Installation en arrière-plan du runtime géré, CPU ou CUDA selon le choix ; sélection automatique de son Python après validation. Aucune installation dans le Python externe sélectionné par erreur. Python3.11 x64 avec lanceur py reste requis.
- Téléchargement du modèle par HTTP borné/reprenable avec révision fixe, taille et SHA vérifiés, arborescence conservée, fichiers déjà vérifiés réutilisés. Jeton de lecture masqué, transmis en mémoire uniquement, sans stockage ni ligne de commande ; erreurs401/403 explicites.
- Progression/journal visible, chemins et lancement verrouillés pendant préparation, annulation du transfert ou de l'installation et de ses processus enfants, fermeture différée jusqu'à arrêt. Le téléchargement du modèle ne dépend pas du runtime.
- Script corrigé : sélection explicite des variantes torch/torchaudio CPU ou cu128 pour ne pas conserver par erreur une installation CPU lors du passage CUDA ; CUDA vérifié si demandé.
- Tests locaux : 108 tests normaux réussis, Ruff réussi ; smoke Qt éditeur/lecture réussi. Tests nouveaux : empreintes/arborescence/reprise Community-1, secrets absents des fichiers, refus gated, arguments d'installation, sortie/annulation processus, boutons asynchrones/chemins/fermeture.
- À vérifier : CI Windows/Linux, appel réel du même backend d'installation CPU sur Windows, installateur0.2.8. Téléchargement réel gated et exécution Community-1 CUDA sur PC utilisateur restent à réaliser.


- Première CI 40859979027 : tests Windows/Linux réussis ; échec du contrôle runtime sous Windows PowerShell 5, `SyntaxError: '(' was never closed` après troncature de la commande Python `-c`. Même problème confirmé sur la capture utilisateur0.2.7. Aucun installateur0.2.8 publié à ce stade.
- Correction : vérifications/téléchargement historique/validation déplacés dans un fichier Python auxiliaire livré avec le script ; plus de code Python passé dans les guillemets de PowerShell5. CI relancée sur le même backend utilisé par le bouton.


### Validation et publication des boutons de préparation

- [PR nº 12](https://github.com/pigeonfou/MAJIMeeting/pull/12) fusionnée dans `f31e243f9279c81b8fa584c9834da7a74c78f9bf`, source corrigée `d3b3789602aa87336f018c6ffb802b100a08d5a5`.
- [CI corrigée 40860556767](https://github.com/pigeonfou/MAJIMeeting/actions/runs/40860556767) réussie : 108 tests Windows et suite Linux, Ruff, installation réelle du runtime CPU par le backend du bouton sous Windows PowerShell5, import pyannote réussi. Absence CUDA normale sur ce runner CPU.
- Construction et installation0.2.8 réussies : scripts PowerShell/Python auxiliaire présents ; contrôles démarrage/éditeur/groupes/lecture et Whisper CPU réel de l'EXE installé réussis.
- [Publication main 40861550638](https://github.com/pigeonfou/MAJIMeeting/actions/runs/40861550638) réussie ; [v0.2.8-preview.49](https://github.com/pigeonfou/MAJIMeeting/releases/tag/v0.2.8-preview.49) disponible.
- À réaliser sur le PC utilisateur : bouton dépendances CUDA, téléchargement Community-1 autorisé ou sélection des fichiers manuels existants, puis diarisation réelle et essai hors ligne. Pas de résultat GPU ou téléchargement gated réel annoncé comme validé.


### 29 octobre 2026 — correction des bornes de diarisation (0.2.9)

- Retour utilisateur : runtime CUDA disponible et Community-1 chargé hors ligne ; première diarisation interrompue par « Tour de parole hors de la piste audio ». Transcription rapide CUDA terminée en 32,6 s pour 1504,4 s de pistes.
- Cause identifiée dans l'adaptateur : contrôle strict de 10 ms sur les sorties par trames du modèle. L'écart exact du cas utilisateur n'était pas inclus dans l'ancien message.
- Correction : intersection des tours de parole avec le support PCM réel, sans déplacement de la chronologie ni modification du texte. Tours sans intersection ignorés, intervalles non finis/inversés toujours rejetés. Compteurs et dépassements maximaux enregistrés dans les options de l'analyse et exportés dans son historique.
- Tests ajoutés : dépassements aux deux bornes, tours entièrement extérieurs, chevauchement conservé, valeurs invalides, intégration SQLite avec origine de piste et audit.
- Validation réelle sur le PC utilisateur et qualité de diarisation restent à réaliser après installation de la correction.

- Tests locaux : 115 tests réussis (dont 20 tests interlocuteurs), Ruff réussi sur les fichiers Python modifiés. CI Windows/Linux et installateur à contrôler.
