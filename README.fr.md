# Smode Filemanager

*[English version](README.md)*

> **Expérimental, pas un outil officiel Smode.** Construit par essais et erreurs sur l'API Oil (voir [smode-oil-reference](https://github.com/gyomh/smode-oil-reference)). Testé sur Smode Compose R15.

Smode n'a ni fonction de relink ni consolidate structuré. Ce dépôt ajoute les deux :

- **Relocate** : retrouve les fichiers manquants du projet (`<Missing File>`) même s'ils ont été déplacés **et**
  répartis autrement sur le disque. Chaque fichier est cherché par son nom ; si plusieurs fichiers portent ce nom,
  celui dont les dossiers ressemblent le plus à l'ancien chemin gagne ; une vraie égalité est signalée comme ambiguë.
  Un fichier trouvé hors de tout Media Directory peut être rebranché en chemin absolu (option).
- **Consolidate** : copie tous les médias utilisés par le projet dans
  `Destination / <nom de la Scene> / VIDEO | IMAGE | AUDIO | 3D`, met les fichiers partagés entre plusieurs Scenes
  dans `_COMMUN`, puis rebranche le projet sur les copies. Les originaux restent en place, une copie identique déjà
  présente est réutilisée, deux fichiers différents de même nom reçoivent un suffixe ` (2)`, les packs Smode en
  lecture seule sont ignorés.

Deux versions du même outil :

| Fichier | Interface |
|---|---|
| `Smode_Filemanager_GUI.py` (**recommandé**) | Une vraie fenêtre d'application servie par le Script lui-même |
| `Smode_Filemanager.py` | Panneau de paramètres du Script + rapport HTML ouvert dans le navigateur |

## Smode_Filemanager_GUI.py

Le Script embarque un petit serveur web sur `127.0.0.1:8893` (cette machine seulement) et ouvre l'interface dans une
fenêtre d'application (Microsoft Edge en mode `--app`, sans barre d'adresse).

- Onglet **Medias** : tous les fichiers du projet avec leur état (OK, manquant, chemin absolu, pack Smode), filtres,
  recherche, Scenes, taille, boutons « Explorateur » et « Copier ».
- Onglet **Relocate** : dossiers de recherche (sélecteur de dossier Windows ou chemin collé, guillemets acceptés),
  Analyser, cocher ce qu'on applique, **choisir le bon candidat pour les fichiers ambigus**, appliquer la sélection.
- Onglet **Consolidate** : destination (sélecteur de dossier ou liste de vos Media Directories ; la liste affiche le
  Media Directory qui contient la destination), plan groupé par Scene / type avec la taille totale, **copie en
  arrière-plan avec barre de progression** (Smode ne gèle pas), bouton Annuler.
- Onglet **Media Directories** : la liste lue dans Smode.

Smode indexe les fichiers fraîchement copiés avec un délai : ils apparaissent *en attente Smode* et sont revérifiés
automatiquement jusqu'à être reconnus.

### Installation

1. Glisser `Smode_Filemanager_GUI.py` dans le projet Smode (Script) et régler **Launch Mode = At Every Update**.
2. La fenêtre s'ouvre toute seule (option **Auto Open**) ; sinon cocher **Open Interface**.
3. Tout le reste se fait dans la fenêtre. Changer le port dans le panneau du Script si 8893 est déjà pris.

La destination d'un Consolidate **doit être dans un Media Directory** : l'ajouter d'abord dans Smode, puis utiliser
le bouton « ↻ Media Directories » (Smode enregistre la liste quelques secondes après l'ajout ; la fenêtre la relit
aussi toute seule tant que la destination est refusée).

## Smode_Filemanager.py

Mêmes Relocate et Consolidate, pilotés depuis les paramètres du Script (sections GENERAL / RELOCATE / CONSOLIDATE /
RAPPORT) : choisir un **Mode**, remplir **Search Folders** ou **Consolidate Folder**, Execute pour obtenir le rapport
HTML, puis cocher **Apply Changes** et relancer Execute. Launch Mode = Manual. Après un Consolidate, relancer Execute
une ou deux fois jusqu'à ce que tout soit *déjà consolidé*.

## Limites

- Les fichiers référencés *à l'intérieur* d'un fichier 3D (textures externes d'un FBX) et les séquences d'images ne
  sont pas gérés.
- Windows uniquement (Edge, Explorateur et sélecteur de dossier PowerShell pour la GUI).

## Licence

MIT — voir [LICENSE](LICENSE).
