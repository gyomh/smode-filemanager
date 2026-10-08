# Smode Filemanager

*[Version française](README.fr.md)*

> **Experimental, not an official Smode tool.** Built by trial and error against the Oil API (see [smode-oil-reference](https://github.com/gyomh/smode-oil-reference)). Tested on Smode Compose R15. The script's messages and report are in French.

Smode has no relink function and no structured consolidate. This Script adds both, in one file:

- **Relocate**: finds the missing files of the project (`<Missing File>`) even when they were moved **and**
  reorganised differently on disk. Each file is searched by name; when several files share that name, the one whose
  folders best match the old path wins; a real tie is reported as ambiguous and left untouched. A file found outside
  any Media Directory can be relinked with an absolute path (option).
- **Consolidate**: copies every media the project uses into
  `Destination / <Scene name> / VIDEO | IMAGE | AUDIO | 3D`, puts files shared by several Scenes in `_COMMUN`, then
  relinks the project to the copies. Originals stay in place, an identical copy already present is reused, name
  collisions get a ` (2)` suffix, Smode's read-only packs are skipped.

Nothing is changed unless **Apply Changes** is ticked: a plain Execute only produces the report.

## Report

Every run writes an HTML page to `Documents\Smode Filemanager\` and opens it in the browser: clickable counter tiles
(filter), one colour per case (relinked, found, absolute path, ambiguous, not found, copied, waiting for Smode,
failed...), "copy path / copy folder" buttons on every file, the list of places where each file is used.

## Install

1. Drag `Smode_Filemanager.py` into your Smode project (Script, **Launch Mode = Manual**).
2. Pick a **Mode** (Relocate / Consolidate) and fill its section:
   - Relocate: **Search Folders** = folders to search, separated by `;` (empty = all your Media Directories).
     Quotes from Windows "Copy as path" are accepted.
   - Consolidate: **Consolidate Folder** = destination, which **must be inside a Media Directory** (add it in Smode
     first; Smode saves the Media Directories list a few seconds after you add one).
3. Execute to read the report, then tick **Apply Changes** and Execute again.

After a Consolidate, Smode indexes the freshly copied files with a delay: those are shown as *waiting for Smode*
(a reload is triggered). Run Execute once or twice more until everything is *already consolidated*.

## Limits

- Files referenced *inside* a 3D file (external FBX textures) and image sequences are not handled.
- Not tested yet: a real ambiguous case, a file shared by two Scenes (`_COMMUN`).

## License

MIT — see [LICENSE](LICENSE).
