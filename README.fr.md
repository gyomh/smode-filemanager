# Smode Filemanager

*[English version](README.md)*

> **Expérimental, pas un outil officiel Smode.** Construit par essais et erreurs sur l'API Oil (voir [smode-oil-reference](https://github.com/gyomh/smode-oil-reference)). Testé sur Smode Compose R15.

Smode n'a ni fonction de relink ni consolidate structuré. Ce Script ajoute les deux, dans un seul fichier :

- **Relocate** : retrouve les fichiers manquants du projet (`<Missing File>`) même s'ils ont été déplacés **et**
  répartis autrement sur le disque. Chaque fichier est cherché par son nom ; si plusieurs fichiers portent ce nom,
  celui dont les dossiers ressemblent le plus à l'ancien chemin gagne ; une vraie égalité est signalée comme ambiguë
  et laissée telle quelle. Un fichier trouvé hors de tout Media Directory peut être rebranché en chemin absolu
  (option).
- **Consolidate** : copie tous les médias utilisés par le projet dans
  `Destination / <nom de la Scene> / VIDEO | IMAGE | AUDIO | 3D`, met les fichiers partagés entre plusieurs Scenes
  dans `_COMMUN`, puis rebranche le projet sur les copies. Les originaux restent en place, une copie identique déjà
  présente est réutilisée, deux fichiers différents de même nom reçoivent un suffixe ` (2)`, les packs Smode en
  lecture seule sont ignorés.

Rien n'est modifié tant que **Apply Changes** n'est pas coché : un simple Execute produit seulement le rapport.

## Rapport

Chaque passage écrit une page HTML dans `Documents\Smode Filemanager\` et l'ouvre dans le navigateur : tuiles de
compteurs cliquables (filtre), une couleur par cas (appliqué, retrouvé, chemin absolu, ambigu, introuvable, copié,
en attente Smode, échec...), boutons « copier le chemin / le dossier » sur chaque fichier, liste des endroits où
chaque fichier est utilisé.

## Installation

1. Glisser `Smode_Filemanager.py` dans le projet Smode (Script, **Launch Mode = Manual**).
2. Choisir un **Mode** (Relocate / Consolidate) et remplir sa section :
   - Relocate : **Search Folders** = dossiers où chercher, séparés par `;` (vide = tous vos Media Directories).
     Les guillemets de « Copier en tant que chemin d'accès » sont acceptés.
   - Consolidate : **Consolidate Folder** = destination, qui **doit être dans un Media Directory** (l'ajouter
     d'abord dans Smode ; Smode enregistre la liste quelques secondes après l'ajout).
3. Execute pour lire le rapport, puis cocher **Apply Changes** et relancer Execute.

Après un Consolidate, Smode indexe les fichiers fraîchement copiés avec un délai : ils apparaissent *en attente
Smode* (un rechargement est lancé). Relancer Execute une ou deux fois jusqu'à ce que tout soit *déjà consolidé*.

## Limites

- Les fichiers référencés *à l'intérieur* d'un fichier 3D (textures externes d'un FBX) et les séquences d'images ne
  sont pas gérés.
- Pas encore testés : un vrai cas ambigu, un fichier partagé entre deux Scenes (`_COMMUN`).

## Licence

MIT — voir [LICENSE](LICENSE).
