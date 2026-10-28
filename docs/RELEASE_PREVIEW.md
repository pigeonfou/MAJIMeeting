# MAJIMeeting — préversion du jalon 1

Installateur Windows x64 sans droits administrateur, avec raccourcis et désinstallation.

Fonctions : capture WASAPI de plusieurs entrées microphone/audio système loopback,
pistes séparées, fragments WAV récupérables, catalogue des réunions, export WAV,
interface native et thèmes clair/sombre.

Contrôles automatisés préalables : tests Python Linux/Windows, Ruff, démarrage Qt,
construction PyInstaller, installation silencieuse et démarrage du programme installé.

**Capture matérielle non validée.** Cette préversion sert aux essais sur Windows ;
elle n'est pas destinée à l'enregistrement irremplaçable de réunions. Pas de signature
de code. Transcription, diarisation et comptes rendus ne sont pas encore intégrés.
La synchronisation précise et la dérive entre périphériques restent à valider.

Installer le fichier `MAJIMeeting-0.1.0-preview-Setup.exe`. Suivre `docs/WINDOWS_TESTS.md`
dans le dépôt pour la validation microphone/loopback, interruption et réunion longue.
Les données locales sont conservées après désinstallation.
