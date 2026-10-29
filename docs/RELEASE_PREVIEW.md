# MAJIMeeting 0.2.9 — correction des bornes de diarisation

Les tours de parole Community-1 sont limités au support audio réel. Les sorties par trames dépassant le début ou la fin ne font plus échouer toute l'analyse. Les passages entièrement extérieurs sont ignorés ; les intervalles non finis ou inversés restent rejetés. Les ajustements sont conservés dans l'historique de l'analyse.

Installer par-dessus la version existante, puis relancer « Distinguer automatiquement les interlocuteurs » sur la transcription existante. Aucun nouveau téléchargement du modèle ni réinstallation des dépendances nécessaire.

Validation : 115 tests Windows et Linux, runtime CPU pyannote et contrôles de l'application installée réussis. Diarisation réelle et qualité sur le GPU utilisateur encore à vérifier.
