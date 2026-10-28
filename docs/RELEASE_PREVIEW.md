# MAJIMeeting 0.2.1 — correctif du téléchargement du modèle

Le téléchargement affiche maintenant l'étape, le fichier, les Mo reçus et le pourcentage.
Il est annulable et reprenable, utilise des délais réseau explicites et vérifie l'intégrité
des fichiers avant installation. Les fichiers complets déjà présents sont reconnus.
Un diagnostic local est disponible dans `download.log` dans le dossier du modèle.

Le téléchargement utilise HTTPS directement sans charger le moteur d'inférence.
L'entrée PyInstaller est protégée pour les sous-processus d'une application Windows gelée.
La CI teste désormais un vrai téléchargement depuis le programme installé, suivi d'une
inférence CPU hors ligne avec ces mêmes fichiers ; l'interface et l'annulation sont testées.

Installer cette mise à jour puis relancer le bouton Télécharger large-v3. Les réunions et
transcriptions existantes sont conservées. Les anciens fichiers complets sont vérifiés ;
les caches partiels provenant du SDK précédent ne sont pas réutilisés.

Large-v3 reste un téléchargement séparé (~3 Go). CUDA/cuDNN ne sont pas inclus.
La cause exacte du blocage sur le PC utilisateur n'a pas été reproduite à distance :
le nouveau parcours doit encore y être confirmé. Les essais large-v3/CUDA, longue durée
et les autres tests matériels en attente ne sont pas déclarés réussis.
