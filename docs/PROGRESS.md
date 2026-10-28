# Progression MAJIMeeting

Mise à jour : 28 octobre 2026.

## État global
Jalon 2 en cours, sur accord utilisateur après les essais de capture réussis.
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
- En cours : J2 import audio et transcription locale horodatée.
- À réaliser : J3 diarisation/éditeur ; J4 comptes rendus ;
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
- Aucun locuteur identifié : les noms track-XX désignent des sources, pas des personnes.
  Pas encore de diarisation, lecture synchronisée, correction ni compte rendu.
- Prototype sans signature de code ; aucune validation large-v3/CUDA à ce stade.

## Prochaines actions
1. Installer la préversion J2 et télécharger large-v3 pour les essais utilisateur.
2. Tester large-v3 sur audio français représentatif, en CPU puis sur RTX/CUDA.
3. Réaliser ultérieurement les essais J1 restants, sans bloquer J2 à la demande utilisateur.
4. Évaluer les frontières de lots et la dérive des sources avant diarisation/éditeur (J3).

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
