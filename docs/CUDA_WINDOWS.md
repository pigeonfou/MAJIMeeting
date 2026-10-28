# Calcul NVIDIA sous Windows

## Pour transcrire immédiatement

Choisir **cpu**, puis **int8**, dans Import et transcription. Aucun téléchargement
supplémentaire de modèle n'est nécessaire si large-v3 est déjà installé.

Depuis 0.2.2, une case visible autorise aussi le repli automatique CUDA vers CPU/int8.
Le mode effectif et la raison du repli sont affichés dans l'historique. La case peut
être décochée si l'on souhaite arrêter le traitement quand CUDA n'est pas disponible.

## Pour activer CUDA

Le moteur faster-whisper/CTranslate2 utilisé demande **cuBLAS CUDA 12** et **cuDNN 9 pour
CUDA 12**, avec un pilote NVIDIA compatible. Ces bibliothèques ne sont pas incluses dans
l'installateur MAJIMeeting. La présence de la RTX seule ne valide pas leur chargement.

1. Utiliser les installateurs officiels NVIDIA : [archives CUDA Toolkit](https://developer.nvidia.com/cuda-toolkit-archive)
   pour choisir une version 12.x ; [installation cuDNN Windows](https://docs.nvidia.com/cudnn/installation/backend/windows/)
   pour cuDNN 9, en sélectionnant la variante CUDA 12 dans l'installateur graphique.
2. Redémarrer MAJIMeeting après installation. Les dossiers standard et les variables
   CUDA_PATH/CUDNN_PATH sont détectés. Aucune commande terminal n'est requise par l'application.
3. Si les DLL sont installées dans un dossier personnalisé, utiliser **Choisir le dossier
   CUDA / cuDNN…**. Le dossier lui-même et ses sous-dossiers bin sont pris en compte.
4. Choisir **cuda / int8_float16**, lancer une courte transcription et contrôler dans
   l'historique que le mode effectif est bien cuda, sans raison de repli CPU.

La vérification de chargement Windows couvre cublasLt64_12.dll, cublas64_12.dll et
cudnn64_9.dll. Un échec peut provenir du fichier ou de ses dépendances. L'inférence
intercepte également les erreurs CUDA tardives. La CI n'a pas de RTX et ne valide pas
l'accélération sur le PC utilisateur ; elle teste les erreurs simulées et la reprise sur
un vrai moteur CPU avec les poids tiny.

Référence moteur : [exigences faster-whisper](https://github.com/SYSTRAN/faster-whisper#gpu).
