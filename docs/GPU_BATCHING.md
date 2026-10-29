# Comparer le remplissage des lots GPU

Sur la version normale sans moteur Flash personnalisé, choisir CUDA / float16 / lots 32 / Rapide / deux workers / Flash désactivé. Comparer la même réunion avec des fenêtres de 10, 15, 20, 25 puis 30 minutes, en gardant les autres paramètres identiques. Les choix précédents de 5 et 10 minutes restent disponibles et les réglages existants sont conservés.

Chaque appel à faster-whisper termine ses propres lots. Agrandir la fenêtre contiguë d'une piste permet de réduire le nombre de lots terminaux incomplets. Les pistes distinctes et les interruptions ne sont jamais assemblées. La RAM et le délai avant le premier résultat peuvent augmenter ; les deux workers ont aussi moins de fenêtres à partager. Un meilleur remplissage ne garantit donc pas une meilleure durée totale.

Relever dans l'historique : fenêtre et lots réellement utilisés, nombre de tentatives, durée totale, chargement, inférence cumulée, tailles des lots et remplissage. Vérifier les noms, nombres, passages proches des anciennes limites de fenêtres et la synchronisation audio. Comparer plusieurs exécutions, idéalement avec la médiane de trois essais par durée.

Référence utilisateur du 29 octobre 2026 : lots 32, fenêtres 600 s, 1504,4 secondes-pistes traitées en 34,6 s ; trois lots (32, 21, 12), 55 portions, remplissage 57,3 %. Sur ce relevé, Flash est désactivé. Le nombre de portions peut changer avec les frontières VAD : aucune promesse de remplissage ou de gain fixe.
