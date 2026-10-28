# MAJIMeeting Flash — compilation expérimentale Windows / RTX 3080

Tentative séparée de la distribution normale. Le moteur CTranslate2 4.8.4 est compilé
avec `WITH_FLASH_ATTN=ON` pour CUDA compute capability 8.6 (RTX 3080 Laptop).
Le commit amont est fixé à `5de572ef60b67a0276c5989ee73d0072808ff4c3`.

La première compilation installe les outils CUDA sur le runner GitHub sans pilote GPU,
puis compile le moteur et sa liaison Python. Elle peut être sensiblement plus longue
qu'une construction ordinaire. La roue produite est mise en cache pour les essais suivants.
Aucune compilation n'est demandée sur le PC utilisateur.

Le backend CPU expérimental est RUY, sans MKL/oneDNN. Le chemin CUDA conserve ses poids
et l'option cuBLAS dynamique. cuDNN n'est pas lié dans ce build ; la vérification préalable
de l'application continue à demander les bibliothèques NVIDIA déjà utilisées avec succès.
Les performances CPU peuvent différer de la distribution normale.

## Vérifications avant publication

- Compilation de tous les kernels Flash prévus par les sources amont, pas une simple case UI.
- Fonction native exportée ajoutée pour lire le macro de compilation depuis la DLL réelle.
- Import, sonde native et inférence CPU réelle tiny sur un autre runner Windows sans les
  outils de compilation, puis tests de l'application.
- Construction de l'installateur séparé, installation et sonde depuis l'EXE installé,
  démarrage, éditeur, lecture audio et inférence réelle CPU.
- Empreinte SHA-256 de l'installateur et diagnostics disponibles avec les artefacts.

La sonde vérifie le flag natif compilé, pas l'exécution des kernels sur la RTX. Aucun
résultat GPU ne peut être déclaré réussi dans la CI sans GPU. Une publication n'a lieu
que si la compilation et tous les contrôles précédents réussissent.

## Installation et essai, si un installateur est publié

L'installateur expérimental utilise un AppId et un dossier distincts :
`%LOCALAPPDATA%\Programs\MAJIMeeting-Flash`.
La version normale reste installée. Les réunions, modèles et réglages existants sont
partagés pour comparer la même réunion ; le verrou d'instance commun empêche deux
applications d'utiliser simultanément les données. Fermer la version normale avant l'essai.
La désinstallation expérimentale ne doit pas supprimer les données de réunion communes.

Ouvrir le raccourci « MAJIMeeting Flash expérimental ». Le titre de fenêtre mentionne
Flash expérimental. Aucun nouveau modèle à télécharger.

1. Dans cette version expérimentale, faire une référence Flash non : CUDA / float16 /
   lots 16 / Rapide / deux workers / fenêtres dix minutes.
2. Activer uniquement Flash Attention et transcrire la même réunion.
3. Vérifier dans l'historique Flash oui, pas simplement la case cochée. Si une reprise
   indique Flash non, exporter le JSON pour conserver l'erreur native exacte.
4. Comparer durées, VRAM et mêmes passages du texte. Les 37,2 s déjà observées avec le
   moteur normal sont une référence indicative ; comparer d'abord on/off dans ce build.
5. Vérifier noms, nombres et texte. Aucun gain n'est garanti.

Pour revenir, fermer l'application expérimentale et rouvrir le raccourci normal.
Cette branche et ce workflow n'altèrent pas le moteur de la release normale.
