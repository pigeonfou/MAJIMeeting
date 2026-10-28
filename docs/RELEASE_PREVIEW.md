# MAJIMeeting 0.2.2 — CUDA indisponible et repli CPU

Corrige le blocage de transcription provoqué par une bibliothèque CUDA absente ou non
chargeable, notamment `cublas64_12.dll`.

- Vérification des DLL NVIDIA et du pilote avant l'inférence ; découverte des dossiers
  standard CUDA/cuDNN et champ facultatif pour une installation personnalisée.
- Case visible autorisant le repli CPU/int8. Le mode effectif et la raison sont conservés
  dans l'historique. La case peut être décochée pour exiger CUDA.
- Prise en charge des échecs GPU tardifs : libération du modèle puis reprise complète
  CPU, sans doublons de segments ni modification des transcriptions précédentes.

Pour transcrire immédiatement, choisir CPU/int8 avec le modèle déjà téléchargé.
Pour activer le GPU, installer cuBLAS CUDA 12 et cuDNN 9 pour CUDA 12 depuis NVIDIA ;
voir docs/CUDA_WINDOWS.md. L'installateur ne fournit pas ces bibliothèques.

La CI teste les erreurs CUDA simulées, l'annulation, l'affichage du repli et une vraie
inférence CPU après DLL manquante simulée, y compris dans le programme Windows installé.
La performance et le fonctionnement GPU sur la RTX utilisateur restent à confirmer.
