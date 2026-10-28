# MAJIMeeting 0.2.3 — horodatages aux limites des lots audio

Corrige l'arrêt « Horodatage de transcription invalide » lorsqu'un segment de Whisper
déborde de l'audio, notamment à la fin d'un dernier lot court.

- Intervalles bornés à la durée réelle du lot, sans temps au-delà de l'audio.
- Segments hors audio ou non exploitables écartés, sans interruption de toute la réunion.
- Audit persistant des ajustements/rejets et de leur texte brut ; compteurs, consultation
  dans l'interface et champ `timestamp_warnings` dans l'export JSON.
- Le texte rejeté ne figure pas comme transcription correctement horodatée ; vérification
  humaine des avertissements nécessaire. Aucune parole n'est reconstituée par ce contrôle.

Le test de régression couvre quatre lots de cinq minutes puis un lot court, avec temps
qui dépassent l'audio, padding et temps non finis. Cette chronologie synthétique utilise
un décodeur simulé ; les autres tests d'intégration font une vraie inférence tiny CPU,
y compris dans le programme Windows installé.

Installer cette version, conserver le modèle et la configuration CUDA existants, puis
relancer la transcription de la réunion. Les anciennes tentatives, l'audio et les réglages
sont conservés. Les performances/qualité sur la réunion utilisateur restent à confirmer.
