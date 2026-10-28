# Progression MAJIMeeting

Mise à jour : 28 octobre 2026.

## État global
Jalon 1 en cours. Prototype de capture Windows ; aucune release stable validée.
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

## Jalons
- En cours : J1 enregistrement et validation matérielle.
- À réaliser : J2 transcription ; J3 diarisation/éditeur ; J4 comptes rendus ;
  J5 exports documentaires/sauvegardes ; J6 validation complète et release stable.

## Tests exécutés
- Socle : CI GitHub initiale réussie sur `32caf8a` (runs 40665214004 et 40665505399).
- Local Linux Python 3.12 : 12 tests réussis ; Ruff réussi ; démarrage Qt offscreen réussi.
- Tests : catalogue, interruption, export bit à bit, fragments partiels, deux sources,
  échec d'ouverture, incident audio, PCM invalide, conservation d'un export existant,
  récupération et changement de thème dans l'interface, saturation et disque plein simulés.
- Première CI Linux en échec : bibliothèque native Qt `libEGL.so.1` absente du runner.
  Correction : installation explicite de libegl1 et libopengl0 avant les tests.
- CI du développement et installateur Windows : résultats à consigner après exécution.
- Capture matérielle WASAPI, réunions longues et RTX : non testées dans cet environnement.

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
- Prototype sans signature de code, sans modèles IA ni fonctions des jalons 2 à 5.

## Prochaines actions
1. Contrôler les Actions et corriger toute erreur de build/installation.
2. Tester microphone + loopback, silence système, débranchement, fermeture forcée,
   puis une réunion longue sur Windows (voir WINDOWS_TESTS.md).
3. Mesurer décalage/dérive et charge disque ; décider du mécanisme de synchronisation.
4. Finaliser J1 avant intégration du traitement différé faster-whisper.

## Références
- Base : `32caf8a0512db0a9629c5e53756630edc64917c9`.
- Développement : branche `develop/recording-foundation`.
- Aucune release stable publiée.
