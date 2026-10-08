# Smode Filemanager

*[Version française](README.fr.md)*

> **Experimental, not an official Smode tool.** Built by trial and error against the Oil API (see [smode-oil-reference](https://github.com/gyomh/smode-oil-reference)). Tested on Smode Compose R15. The interface, messages and reports are in French.

Smode has no relink function and no structured consolidate. This repository adds both:

- **Relocate**: finds the missing files of the project (`<Missing File>`) even when they were moved **and**
  reorganised differently on disk. Each file is searched by name; when several files share that name, the one whose
  folders best match the old path wins; a real tie is reported as ambiguous. A file found outside any Media
  Directory can be relinked with an absolute path (option).
- **Consolidate**: copies every media the project uses into
  `Destination / <Scene name> / VIDEO | IMAGE | AUDIO | 3D`, puts files shared by several Scenes in `_COMMUN`, then
  relinks the project to the copies. Originals stay in place, an identical copy already present is reused, name
  collisions get a ` (2)` suffix, Smode's read-only packs are skipped.

Two versions of the same tool:

| File | Interface |
|---|---|
| `Smode_Filemanager_GUI.py` (**recommended**) | A real application window served by the Script itself |
| `Smode_Filemanager.py` | Script parameters panel + an HTML report opened in the browser |

## Smode_Filemanager_GUI.py

The Script embeds a small web server on `127.0.0.1:8893` (this machine only) and opens the interface in an
application window (Microsoft Edge `--app` mode, no address bar).

- **Medias** tab: every file of the project with its state (OK, missing, absolute path, Smode pack), filters,
  search, Scenes, size, "Explorer" and "Copy" buttons.
- **Relocate** tab: search folders (Windows folder picker or pasted path, quotes accepted), Analyse, tick what to
  apply, **pick the right candidate for ambiguous files**, apply the selection.
- **Consolidate** tab: destination (folder picker or your Media Directories; the list shows which Media Directory
  contains the destination), plan grouped by Scene / type with the total size, **copy in the background with a
  progress bar** (Smode does not freeze), cancel button.
- **Media Directories** tab: the list read from Smode.

Files freshly copied are indexed by Smode with a delay: they show as *waiting for Smode* and are re-checked
automatically until they resolve.

### Install

1. Drag `Smode_Filemanager_GUI.py` into your Smode project (Script) and set **Launch Mode = At Every Update**.
2. The window opens by itself (option **Auto Open**); otherwise tick **Open Interface**.
3. Everything else happens in the window. Change the port in the Script panel if 8893 is taken.

The destination of a Consolidate **must be inside a Media Directory**: add it in Smode first, then use the
"↻ Media Directories" button (Smode saves the list a few seconds after you add one; the window also re-reads it
automatically while the destination is refused).

## Smode_Filemanager.py

Same Relocate and Consolidate, driven from the Script parameters (sections GENERAL / RELOCATE / CONSOLIDATE /
RAPPORT): pick a **Mode**, fill **Search Folders** or **Consolidate Folder**, Execute to get the HTML report, then tick
**Apply Changes** and Execute again. Launch Mode = Manual. After a Consolidate, run Execute once or twice more until
everything is *already consolidated*.

## Limits

- Files referenced *inside* a 3D file (external FBX textures) and image sequences are not handled.
- Windows only (Edge, Explorer and PowerShell folder picker for the GUI).

## License

MIT — see [LICENSE](LICENSE).
