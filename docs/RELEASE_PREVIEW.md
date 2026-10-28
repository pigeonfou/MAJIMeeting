# MAJIMeeting 0.2.6 — essais GPU avancés

- Option Flash Attention, reprise CUDA sans cette option si non prise en charge.
- Option deux workers natifs : fenêtres concurrentes partageant un seul modèle.
- Fenêtres de 5 ou 10 minutes et lots jusqu'à 32 sur choix explicite.
- Tailles réelles des lots, distribution et remplissage dans l'historique et le JSON.
- Temporaires isolés, annulation coopérative ; reprise à un worker prioritaire si VRAM insuffisante.

Installer par-dessus 0.2.5. Aucun nouveau modèle requis. Flash Attention et deux workers
restent désactivés par défaut ; données et réglages ordinaires conservés.

Comparer sur la même réunion : CUDA / float16 / lots 16 / Rapide, référence 1 worker /
5 min / Flash non, puis Flash seul, deux workers seuls, fenêtres de dix minutes seules.
Lire les paramètres effectifs et vérifier les mêmes passages audio. Le taux de remplissage
n'est pas une occupation GPU. Voir docs/GPU_EXPERIMENTS.md.

Les tests CPU et simulations ne valident pas Flash CUDA ni un gain sur RTX. La compatibilité
Flash de cette distribution et le gain réel sont à tester. Deux workers peuvent ralentir
le traitement. La diarisation automatique reste à intégrer.
