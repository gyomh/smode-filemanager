#    #########      ###         ###      #########      #########         ###############
# ###               ######   ######   ###         ###   ###      ###      ###
# ###               ###   ###   ###   ###         ###   ###         ###   ###
#    #########      ###   ###   ###   ###         ###   ###         ###   ############
#             ###   ###         ###   ###         ###   ###         ###   ###
#             ###   ###         ###   ###         ###   ###      ###      ###
# ############      ###         ###      #########      #########         ###############
#
# -------------------- "Guillaume Henrion aka [GYOMH]" "08/10/2026" --------------------
# __________________________________________ ___________________________________________
# |                                       | |                                         |
# |    SMODE FILEMANAGER GUI              | | Graphical interface of the Filemanager, |
# |       V0.13                           | | served by Smode (local HTTP server)     |
# |                                       | | in an application window.               |
# |_______________________________________| |_________________________________________|
# |    Instructions:                      | | - Media: list, states, filters          |
# | 1- Drag the script into the project   | | - Relocate: search, pick ambiguous      |
# | 2- Launch Mode = At Every Update      | |   candidates, selective apply           |
# | 3- The window opens by itself         | | - Consolidate: Scene / Type, copy       |
# |    (or tick Open Interface)           | |   in the background with progress       |
# | 4- Everything happens in the window   | | - Listens on 127.0.0.1 only             |
# |_______________________________________| |_________________________________________|
#
# HISTORY
# V0.1 - 08/10/2026 - First version: built-in HTTP server on 127.0.0.1 (queue + main thread for Oil,
#                      disk work in the background), Edge --app window, tabs
#                      Media / Relocate / Consolidate / Media Directories.
# V0.2 - 08/10/2026 - Consolidate: button to reload the Media Directories + automatic reload every 3 s
#                      while the destination is in no Media Directory (analysis rerun as soon as a new
#                      folder appears).
# V0.3 - 08/10/2026 - Consolidate: the list shows the Media Directory containing the destination
#                      ("Name > subfolder" for a subfolder, "Outside Media Directories" in orange).
# V0.4 - 08/10/2026 - Media: search with a scope (Name + Scene by default, Name, Scene, Paths,
#                      Everywhere), result counter, tiles recomputed on the search, highlighting.
# V0.5 - 08/10/2026 - Media: cross button left of the field to clear the search (or Esc).
# V0.6 - 08/10/2026 - Clear button: centred SVG cross, blue hover like the other buttons.
# V0.7 - 08/10/2026 - Drop-down lists: blue outline on hover / focus; blue checkboxes and radio buttons.
# V0.8 - 08/10/2026 - Drop-down lists drawn by the interface (app blue highlight instead of the Windows
#                      one), keyboard arrows / Enter / Esc, "Outside Media Directories" in orange.
# V0.9 - 08/10/2026 - Code review, fixes:
#                      - nested search folders: the same file is no longer counted twice
#                        (false "Ambiguous" with two identical paths);
#                      - Media Directory at a drive root (e.g. G:\) recognised;
#                      - port already taken: no more start attempt on every frame;
#                      - cancelled / failed copy: the partial .fmgpart file is deleted; disk space
#                        checked before copying (and shown in the plan);
#                      - POST-only API (a web page can no longer trigger Explorer / dialog / scan with
#                        a simple link), 404 for unknown paths;
#                      - orange dot when the Script no longer runs, immediate error instead of a
#                        2 min wait;
#                      - Relocate: missing search folders reported; absolute-path candidates dropped
#                        when absolute paths are disabled;
#                      - "Waiting for Smode" files never recognised: Failed after 40 s; a single
#                        project rescan at the end instead of one per file;
#                      - network errors handled (copy progress, Browse); reminder to save the project;
#                      - blue hover everywhere (folder crosses, Cancel, tiles, tabs);
#                      - Scene named CON, NUL, AUX, COM1...: folder prefixed with _ (Windows reserved).
# V0.10 - 08/10/2026 - Auto Open: the window also opens when the project is reopened (or the Script
#                      added) without restarting Smode (before: only on the 1st server start of the
#                      session). No 2nd window if one is already open: it reloads the project by
#                      itself. On a Script restart, Oil references of the old project are dropped and
#                      a running consolidate is cancelled.
# V0.11 - 08/10/2026 - Bilingual interface: FR / EN selector at the top right (remembered in the
#                      window, Windows language by default); server messages in the chosen language;
#                      French texts with accents. Pure ASCII .py file (accents as \u escapes).
# V0.12 - 08/10/2026 - All comments translated to English.
# V0.13 - 08/10/2026 - Favicon (white folder with an arrow on the app blue), shown in the window title bar.
#
# =============== OPTIONS (visible / editable in the Script panel) ===============
SERVEUR: Oil.String("----------------------------------------")
port: Oil.PositiveInteger(8893)          # local port of the interface (127.0.0.1 only)
openInterface: Oil.Boolean(False)        # tick = opens the window (unticks itself)
autoOpen: Oil.Boolean(True)              # opens the window when the Script starts (Smode launched, project reopened...)
restartServer: Oil.Boolean(False)        # tick = restarts the server (unticks itself)
ETAT: Oil.String("----------------------------------------")
status: Oil.String("")                   # interface address / errors

import os
import re
import glob
import json
import time
import queue
import shutil
import threading
import subprocess
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

FMG_VERSION = "0.13"
FMG_SKIP_CLASSES = ('String', 'SrgbColor', 'Boolean', 'PositiveReal', 'Real', 'Percentage',
                    'UnboundedPercentage', 'Integer', 'Matrix4d')
FMG_TYPE_FOLDERS = {"VideoFileContent": "VIDEO", "Color2dMipmaps": "IMAGE", "AudioFileContent": "AUDIO",
                    "Group3dLayer": "3D"}
FMG_EXT_FOLDERS = {"VIDEO": (".mov", ".mp4", ".avi", ".mxf", ".mkv", ".webm", ".hap"),
                   "IMAGE": (".png", ".jpg", ".jpeg", ".tif", ".tiff", ".exr", ".bmp", ".tga", ".dds", ".hdr", ".psd"),
                   "AUDIO": (".wav", ".mp3", ".aif", ".aiff", ".flac", ".ogg"),
                   "3D": (".fbx", ".obj", ".gltf", ".glb", ".abc", ".usd", ".usdz", ".3ds", ".dae")}
FMG_SHARED = "_COMMUN"
FMG_NO_SCENE = "_PROJET"

# State kept between frames (the Script runs on every update; globals are shared between Scripts,
# hence the _FMG / fmg_ prefix everywhere).
if "_FMG" not in globals():
    _FMG = {"queue": queue.Queue(), "servers": [], "version": None, "port": None,
            "refs": {}, "job": None, "lock": threading.Lock()}
_FMG.setdefault("tick", time.time())     # keys added in V0.9+ (an _FMG from a previous version may be in memory)
_FMG.setdefault("busy", False)
_FMG.setdefault("last_poll", 0.0)        # last /api/info request from an open window
_FMG.setdefault("session", 0)            # +1 on each Script (re)start (project reopened...)
_FMG.setdefault("tls", threading.local())  # language of the current request (per thread)

# Server messages in the language chosen in the interface (sent with each request)
FMG_MSG = {
    "fr": {"dead": "Smode ne traite plus les demandes : le Script Smode Filemanager GUI est-il toujours dans le projet "
                   "ouvert, actif, en Launch Mode 'At Every Update' ?",
           "timeout": "Smode ne r\u00e9pond pas (Script bien en Launch Mode 'At Every Update' ?)",
           "destEmpty": "Indiquer le dossier de destination.",
           "destNotMd": "Ce dossier n'est dans aucun Media Directory. L'ajouter dans Smode (panneau Media Directories), "
                        "attendre quelques secondes (Smode enregistre la liste en diff\u00e9r\u00e9) puis relancer l'analyse.",
           "destRo": "Ce dossier est dans un Media Directory en lecture seule.",
           "noSpace": "Espace insuffisant sur le disque de destination : %s \u00e0 copier, %s libres.",
           "cancelled": "annul\u00e9", "jobRunning": "un consolidate est d\u00e9j\u00e0 en cours",
           "notFound": "introuvable : %s", "unknown": "endpoint inconnu : %s",
           "units": ("o", "Ko", "Mo", "Go", "To")},
    "en": {"dead": "Smode no longer processes requests: is the Smode Filemanager GUI Script still in the open project, "
                   "active, in Launch Mode 'At Every Update'?",
           "timeout": "Smode is not responding (is the Script in Launch Mode 'At Every Update'?)",
           "destEmpty": "Enter the destination folder.",
           "destNotMd": "This folder is not inside any Media Directory. Add it in Smode (Media Directories panel), wait "
                        "a few seconds (Smode saves the list with a delay), then analyse again.",
           "destRo": "This folder is inside a read-only Media Directory.",
           "noSpace": "Not enough space on the destination drive: %s to copy, %s free.",
           "cancelled": "cancelled", "jobRunning": "a consolidate is already running",
           "notFound": "not found: %s", "unknown": "unknown endpoint: %s",
           "units": ("B", "KB", "MB", "GB", "TB")},
}


def fmg_lang():
    lang = getattr(_FMG["tls"], "lang", "fr")
    return lang if lang in FMG_MSG else "fr"


def fmg_t(key, *args):
    msg = FMG_MSG[fmg_lang()][key]
    return msg % args if args else msg


# ===================================== PATHS / DISK (no Oil) =====================================
def fmg_clean_path(p):
    return str(p).strip().strip('"\'').strip()


def fmg_media_dirs():
    """[(name, folder, read-only)] from %APPDATA%\\Smode Compose\\configurations\\Data_*.configuration."""
    conf_dir = os.path.join(os.environ.get("APPDATA", ""), "Smode Compose", "configurations")
    files = sorted(glob.glob(os.path.join(conf_dir, "Data_*.configuration")), key=os.path.getmtime)
    if not files:
        return []
    txt = open(files[-1], encoding="utf-8", errors="replace").read()
    out = []
    for block in re.findall(r"\{([^{}]*name\s*=[^{}]*)\}", txt):
        name = re.search(r'name\s*=\s*"((?:[^"\\]|\\.)*)"', block)
        dire = re.search(r'directory\s*=\s*"((?:[^"\\]|\\.)*)"', block)
        if name and dire:
            out.append((name.group(1).replace('\\\\', '\\'), dire.group(1).replace('\\\\', '\\'),
                        "readOnly = true" in block))
    return out


def fmg_root(d):
    """Normalised folder for path comparisons, without trailing separator (handles a drive root, e.g. G:\\)."""
    return os.path.normcase(os.path.abspath(d)).rstrip(os.sep)


def fmg_to_smode(abs_path, media_dirs):
    p = os.path.normcase(os.path.abspath(abs_path))
    best = None
    for name, d, _ in media_dirs:
        root = fmg_root(d)
        if p.startswith(root + os.sep) and (best is None or len(root) > len(best[1])):
            best = (name, root)
    if best is None:
        return None
    return best[0] + "/" + os.path.abspath(abs_path)[len(best[1]) + 1:].replace(os.sep, "/")


def fmg_from_smode(path, media_dirs):
    path = str(path).replace("\\", "/")
    if re.match(r"^[A-Za-z]:/", path):
        return os.path.abspath(path)
    for name, d, _ in sorted(media_dirs, key=lambda m: -len(m[0])):
        if path.startswith(name + "/"):
            return os.path.join(d, *path[len(name) + 1:].split("/"))
    return None


def fmg_in_readonly(abs_path, media_dirs):
    p = os.path.normcase(os.path.abspath(abs_path))
    return any(ro and p.startswith(fmg_root(d) + os.sep) for _, d, ro in media_dirs)


def fmg_build_index(folders):
    """file name (lower case) -> [paths]. A folder contained in another one of the list is walked only once,
    and the same file is never counted twice (otherwise a false "ambiguous" case with two identical paths)."""
    roots = []                                    # (normalised key, folder as typed: its case is kept)
    for f in sorted(folders, key=lambda x: len(fmg_root(x))):
        k = fmg_root(f)
        if not any(k == rk or k.startswith(rk + os.sep) for rk, _ in roots):
            roots.append((k, f))
    index, seen = {}, set()
    for _, root_dir in roots:
        for dirpath, _, filenames in os.walk(root_dir):
            for f in filenames:
                if f.lower().endswith(".meta"):
                    continue
                full = os.path.join(dirpath, f)
                key = os.path.normcase(os.path.abspath(full))
                if key not in seen:
                    seen.add(key)
                    index.setdefault(f.lower(), []).append(full)
    return index


def fmg_score(old_path, candidate):
    old_dirs = [s.lower() for s in old_path.replace("\\", "/").split("/")[:-1]]
    new_dirs = [s.lower() for s in os.path.dirname(candidate).split(os.sep)]
    n = 0
    for a, b in zip(reversed(old_dirs), reversed(new_dirs)):
        if a != b:
            break
        n += 1
    return (n, len(set(old_dirs) & set(new_dirs)))


def fmg_resolve(old_path, index):
    cands = index.get(old_path.replace("\\", "/").split("/")[-1].lower(), [])
    if not cands:
        return "notfound", None
    if len(cands) == 1:
        return "found", cands[0]
    ranked = sorted(cands, key=lambda c: fmg_score(old_path, c), reverse=True)
    if fmg_score(old_path, ranked[0]) > fmg_score(old_path, ranked[1]):
        return "found", ranked[0]
    return "ambiguous", ranked


def fmg_type_folder(cls, path):
    inner = cls[len("FileReference("):-1] if cls.startswith("FileReference(") else ""
    if inner in FMG_TYPE_FOLDERS:
        return FMG_TYPE_FOLDERS[inner]
    ext = os.path.splitext(path)[1].lower()
    for folder, exts in FMG_EXT_FOLDERS.items():
        if ext in exts:
            return folder
    return "AUTRES"


def fmg_safe_name(name):
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip().rstrip(".")
    if re.match(r"^(con|prn|aux|nul|com\d|lpt\d)(\..*)?$", name, re.I):   # names reserved by Windows
        name = "_" + name
    return name or "_SANS_NOM"


def fmg_same_file(a, b):
    try:
        return os.path.getsize(a) == os.path.getsize(b) and int(os.path.getmtime(a)) == int(os.path.getmtime(b))
    except OSError:
        return False


def fmg_size(p):
    try:
        return os.path.getsize(p)
    except OSError:
        return 0


def fmg_fmt_size(n):
    units = fmg_t("units")
    for i, unit in enumerate(units[:-1]):
        if n < 1024:
            return "%.0f %s" % (n, unit) if i == 0 else "%.1f %s" % (n, unit)
        n /= 1024.0
    return "%.1f %s" % (n, units[-1])


def fmg_free_space(path):
    """Free space on the drive of path (the folder may not exist yet: walk up to the existing parent)."""
    p = os.path.abspath(path)
    while not os.path.exists(p):
        parent = os.path.dirname(p)
        if parent == p:
            return None
        p = parent
    try:
        return shutil.disk_usage(p).free
    except OSError:
        return None


# ===================================== OIL TASKS (main thread) =====================================
def fmg_is_missing(ref):
    fo = ref.file.get()
    return fo is None or fo.getOilClassName() == "MissingFile"


def fmg_walk_refs(project):
    """[(labels, scene, ref)] for every FileReference of the project."""
    seen, refs = set(), []

    def kids(o):
        try:
            for i in range(o.getNumVariables()):
                yield o.getVariable(i)
        except Exception:
            pass
        try:
            for i in range(len(o)):
                yield o[i]
        except Exception:
            pass

    def walk(o, labels, depth, scene):
        if o is None or depth > 80:
            return
        try:
            cn = o.getOilClassName()
        except Exception:
            cn = "?"
        if cn in FMG_SKIP_CLASSES:
            return
        try:
            uid = o.getUniqueIdentifier()
        except Exception:
            uid = None
        if uid:
            if uid in seen:
                return
            seen.add(uid)
        try:
            lab = o.label.get()
            if lab:
                labels = labels + [str(lab)]
                if cn == "Scene" and scene is None:
                    scene = str(lab)
        except Exception:
            pass
        if cn.startswith("FileReference"):
            refs.append((" / ".join(labels), scene, o))
            return
        if "Pointer" in cn and "Owned" in cn:
            try:
                walk(o.get(), labels, depth + 1, scene)
            except Exception:
                pass
        for v in kids(o):
            walk(v, labels, depth + 1, scene)

    walk(project, [], 0, None)
    return refs


def fmg_task_scan(_arg):
    """All references, grouped by Smode path. Keeps the Oil refs for the writes."""
    project = script.project
    groups, refs_by_path = {}, {}
    for labels, scene, ref in fmg_walk_refs(project):
        path = str(ref.path.get())
        if not path:
            continue
        g = groups.get(path)
        if g is None:
            missing = fmg_is_missing(ref)
            abs_path = None
            if not missing:
                try:
                    abs_path = os.path.abspath(str(ref.file.get().nativeFile.get()))
                except Exception:
                    missing = True
            g = groups[path] = {"path": path, "abs": abs_path, "missing": missing, "cls": ref.getOilClassName(),
                                "scenes": [], "users": []}
        if (scene or FMG_NO_SCENE) not in g["scenes"]:
            g["scenes"].append(scene or FMG_NO_SCENE)
        g["users"].append(labels)
        refs_by_path.setdefault(path, []).append(ref)
    _FMG["refs"] = refs_by_path
    return {"project": project.getFriendlyName(), "items": list(groups.values())}


def fmg_task_set_paths(changes):
    """changes = [(old Smode path, new)] -> {old: 'ok' | 'pending' | 'failed'}."""
    out = {}
    for old, new in changes:
        refs = _FMG["refs"].get(old, [])
        if not refs:
            out[old] = "failed"
            continue
        for r in refs:
            r.path.set(new)
        still = [r for r in refs if fmg_is_missing(r)]
        if still:
            for r in still:
                r.reload.trig()
        out[old] = "ok" if not still else "pending"
        _FMG["refs"][new] = refs
    return out


def fmg_task_check(paths):
    """Current state of Smode paths; reloads the ones still missing."""
    out = {}
    for p in paths:
        refs = _FMG["refs"].get(p, [])
        if not refs:
            out[p] = "unknown"
            continue
        still = [r for r in refs if fmg_is_missing(r)]
        for r in still:
            r.reload.trig()
        out[p] = "ok" if not still else "pending"
    return out


FMG_TASKS = {"scan": fmg_task_scan, "set_paths": fmg_task_set_paths, "check": fmg_task_check}


def fmg_alive():
    """True if the Script still runs (recent frame, or an Oil task running on the main thread)."""
    return _FMG["busy"] or time.time() - _FMG["tick"] < 5


def fmg_main(task, arg=None, timeout=120):
    """Runs an Oil task on the main thread (Script in At Every Update) and waits for the result."""
    if not fmg_alive():
        raise RuntimeError(fmg_t("dead"))
    box = {"task": task, "arg": arg, "result": None, "error": None, "done": threading.Event()}
    _FMG["queue"].put(box)
    if not box["done"].wait(timeout):
        raise RuntimeError(fmg_t("timeout"))
    if box["error"]:
        raise RuntimeError(box["error"])
    return box["result"]


def fmg_process_queue():
    while not _FMG["queue"].empty():
        box = _FMG["queue"].get_nowait()
        _FMG["busy"] = True
        try:
            box["result"] = FMG_TASKS[box["task"]](box["arg"])
        except Exception as e:
            box["error"] = repr(e)
        finally:
            _FMG["busy"] = False
            _FMG["tick"] = time.time()
        box["done"].set()


# ===================================== LOGIC (HTTP thread, no Oil) =====================================
def fmg_items_view(scan, media_dirs):
    """Media list for the Media tab."""
    out = []
    for g in scan["items"]:
        if g["missing"]:
            state = "missing"
        elif g["abs"] and fmg_in_readonly(g["abs"], media_dirs):
            state = "pack"
        elif g["abs"] and fmg_to_smode(g["abs"], media_dirs) is None:
            state = "absolute"
        else:
            state = "ok"
        out.append({"path": g["path"], "abs": g["abs"], "state": state, "type": fmg_type_folder(g["cls"], g["path"]),
                    "scenes": g["scenes"], "users": g["users"], "size": fmg_size(g["abs"]) if g["abs"] else 0})
    out.sort(key=lambda x: x["path"].lower())
    return out


def fmg_relocate_analyze(folders, allow_absolute):
    media_dirs = fmg_media_dirs()
    folders = [fmg_clean_path(f) for f in folders if fmg_clean_path(f)]
    bad = [f for f in folders if not os.path.isdir(f)]            # typed by the user but not found
    if not folders:
        folders = [d for _, d, ro in media_dirs if not ro]
    folders = [f for f in folders if os.path.isdir(f)]
    scan = fmg_main("scan")
    missing = [g for g in scan["items"] if g["missing"]]
    index = fmg_build_index(folders) if missing else {}
    entries = []
    for g in missing:
        e = {"old": g["path"], "users": g["users"], "type": fmg_type_folder(g["cls"], g["path"])}
        on_disk = fmg_from_smode(g["path"], media_dirs)
        kind, cand = fmg_resolve(g["path"], index)
        if on_disk and os.path.isfile(on_disk):
            e.update(state="pending", new=g["path"], abs=on_disk)
        elif kind == "found":
            new = fmg_to_smode(cand, media_dirs)
            if new is None and not allow_absolute:
                e.update(state="outside", abs=cand, new=cand)
            else:
                e.update(state="found" if new else "found_abs", new=new or cand, abs=cand)
        elif kind == "ambiguous":
            # absolute paths disabled: drop the candidates outside the Media Directories
            ok = [c for c in cand if allow_absolute or fmg_to_smode(c, media_dirs) is not None]
            if not ok:
                e.update(state="outside", abs=cand[0], new=cand[0])
            elif len(ok) == 1:
                e.update(state="found", new=fmg_to_smode(ok[0], media_dirs), abs=ok[0])
            else:
                e.update(state="ambiguous", cands=[{"abs": c, "new": fmg_to_smode(c, media_dirs) or c,
                                                    "absolute": fmg_to_smode(c, media_dirs) is None} for c in ok])
        else:
            e["state"] = "notfound"
        entries.append(e)
    return {"project": scan["project"], "folders": folders, "badFolders": bad, "entries": entries}


def fmg_consolidate_plan(dest):
    media_dirs = fmg_media_dirs()
    dest = os.path.abspath(fmg_clean_path(dest)) if fmg_clean_path(dest) else ""
    error = ""
    if not dest:
        error = fmg_t("destEmpty")
    elif fmg_to_smode(os.path.join(dest, "x"), media_dirs) is None:
        error = fmg_t("destNotMd")
    elif fmg_in_readonly(os.path.join(dest, "x"), media_dirs):
        error = fmg_t("destRo")
    scan = fmg_main("scan")
    entries, used = [], {}
    for g in sorted(scan["items"], key=lambda g: g["path"].lower()):
        e = {"old": g["path"], "users": g["users"], "scenes": g["scenes"], "type": fmg_type_folder(g["cls"], g["path"])}
        entries.append(e)
        if g["missing"]:
            on_disk = fmg_from_smode(g["path"], media_dirs)
            e["state"] = "pending" if on_disk and os.path.isfile(on_disk) else "missing"
            continue
        src = g["abs"]
        e.update(src=src, size=fmg_size(src))
        if fmg_in_readonly(src, media_dirs):
            e["state"] = "pack"
            continue
        if dest and os.path.normcase(src).startswith(fmg_root(dest) + os.sep):
            e["state"] = "inplace"
            continue
        scene_dir = FMG_SHARED if len(g["scenes"]) > 1 else fmg_safe_name(g["scenes"][0])
        folder = os.path.join(dest or "<destination>", scene_dir, e["type"])
        base, ext = os.path.splitext(os.path.basename(src))
        target, n = os.path.join(folder, base + ext), 2
        while (os.path.normcase(target) in used and used[os.path.normcase(target)] != src) \
                or (os.path.exists(target) and not fmg_same_file(src, target)):
            target, n = os.path.join(folder, "%s (%d)%s" % (base, n, ext)), n + 1
        used[os.path.normcase(target)] = src
        e.update(state="planned", target=target, group=scene_dir + " / " + e["type"],
                 new=(fmg_to_smode(target, media_dirs) if dest else None) or target,
                 exists=os.path.exists(target))
    return {"project": scan["project"], "dest": dest, "error": error, "entries": entries,
            "free": fmg_free_space(dest) if dest else None}


def fmg_copy_with_progress(src, dst, job):
    """Chunked copy into a .fmgpart file renamed at the end; the partial file is deleted on error or
    cancellation (otherwise GBs of truncated file would stay on the disk)."""
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    tmp = dst + ".fmgpart"
    done0 = job["done_bytes"]
    try:
        with open(src, "rb") as fi, open(tmp, "wb") as fo:
            while True:
                if job.get("cancel"):
                    raise RuntimeError(fmg_t("cancelled"))
                buf = fi.read(8 * 1024 * 1024)
                if not buf:
                    break
                fo.write(buf)
                job["done_bytes"] += len(buf)
        shutil.copystat(src, tmp)
        os.replace(tmp, dst)
    except BaseException:
        job["done_bytes"] = done0
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def fmg_consolidate_job(dest, selected, lang="fr"):
    _FMG["tls"].lang = lang                   # copy-thread messages in the interface language
    job = _FMG["job"]
    try:
        plan = fmg_consolidate_plan(dest)
        if plan["error"]:
            raise RuntimeError(plan["error"])
        todo = [e for e in plan["entries"] if e["state"] == "planned" and (selected is None or e["old"] in selected)]
        job["total"] = len(todo)
        job["total_bytes"] = sum(e["size"] for e in todo if not e["exists"])
        free = fmg_free_space(plan["dest"])
        if free is not None and job["total_bytes"] > free:
            raise RuntimeError(fmg_t("noSpace", fmg_fmt_size(job["total_bytes"]), fmg_fmt_size(free)))
        for i, e in enumerate(todo):
            if job.get("cancel"):
                break
            job["current"] = os.path.basename(e["src"])
            job["index"] = i + 1
            res = {"old": e["old"], "new": e["new"], "target": e["target"], "group": e["group"],
                   "type": e["type"], "size": e["size"], "users": e["users"]}
            try:
                reused = e["exists"]
                if not reused:
                    fmg_copy_with_progress(e["src"], e["target"], job)
                state = fmg_main("set_paths", [(e["old"], e["new"])])[e["old"]]
                res["state"] = {"ok": "reused" if reused else "copied", "pending": "pending"}.get(state, "failed")
            except Exception as ex:
                res["state"], res["error"] = "failed", str(ex)
            job["results"].append(res)
    except Exception as ex:
        job["error"] = str(ex)
    job["running"] = False
    job["current"] = ""


# ===================================== SYSTEM TOOLS =====================================
def fmg_browse_folder(initial=""):
    """Windows folder picker dialog (PowerShell, outside the Smode process)."""
    ps = ("Add-Type -AssemblyName System.Windows.Forms;"
          "$f = New-Object System.Windows.Forms.FolderBrowserDialog;"
          "$f.Description = 'Smode Filemanager';$f.ShowNewFolderButton = $true;"
          "$f.SelectedPath = '%s';"
          "$o = New-Object System.Windows.Forms.Form -Property @{TopMost=$true};"
          "if ($f.ShowDialog($o) -eq 'OK') { [Console]::OutputEncoding=[Text.Encoding]::UTF8; $f.SelectedPath }"
          % initial.replace("'", "''"))
    r = subprocess.run(["powershell", "-NoProfile", "-STA", "-Command", ps], capture_output=True,
                       creationflags=0x08000000)
    return r.stdout.decode("utf-8", "replace").strip()


def fmg_reveal(path):
    path = os.path.abspath(path)
    if os.path.isfile(path):
        subprocess.Popen(["explorer", "/select,", path])
    elif os.path.isdir(path):
        subprocess.Popen(["explorer", path])
    else:
        raise RuntimeError(fmg_t("notFound", path))


def fmg_open_window(url):
    for edge in (r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
                 r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"):
        if os.path.isfile(edge):
            subprocess.Popen([edge, "--app=" + url, "--window-size=1400,900"])
            return
    os.startfile(url)


# ===================================== HTTP SERVER =====================================
class FmgHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def do_GET(self):
        self._route("GET")

    def do_POST(self):
        self._route("POST")

    def _route(self, method):
        host = (self.headers.get("Host") or "").rsplit(":", 1)[0].lower()
        origin = self.headers.get("Origin")
        port_ = self.server.server_address[1]
        if host not in ("127.0.0.1", "localhost") or (
                origin and origin not in ("http://127.0.0.1:%d" % port_, "http://localhost:%d" % port_)):
            return self._send(403, {"error": "acces refuse"})
        path = urllib.parse.urlparse(self.path).path
        # The API only accepts POST: a foreign web page can trigger a GET (<img src=...>) without an Origin
        # header, but a POST from it always carries its Origin (refused above).
        if path.startswith("/api/") and method != "POST":
            return self._send(405, {"error": "methode non autorisee"})
        if method == "GET" and path not in ("/", "/index.html"):
            return self._send(404, {"error": "introuvable"})
        if method == "GET" and path in ("/", "/index.html"):
            body = FMG_HTML.replace("__VERSION__", FMG_VERSION).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
            return
        try:
            length = int(self.headers.get("Content-Length", 0))
            data = json.loads(self.rfile.read(length).decode("utf-8")) if length else {}
            _FMG["tls"].lang = data.get("lang") if data.get("lang") in FMG_MSG else "fr"
            self._send(200, fmg_api(path, data))
        except Exception as ex:
            self._send(500, {"error": str(ex)})

    def _send(self, code, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)


def fmg_api(path, data):
    if path == "/api/info":
        _FMG["last_poll"] = time.time()
        return {"version": FMG_VERSION, "alive": fmg_alive(), "session": _FMG["session"],
                "mediaDirs": [{"name": n, "dir": d, "readOnly": ro} for n, d, ro in fmg_media_dirs()]}
    if path == "/api/scan":
        scan = fmg_main("scan")
        return {"project": scan["project"], "items": fmg_items_view(scan, fmg_media_dirs())}
    if path == "/api/relocate/analyze":
        return fmg_relocate_analyze(data.get("folders") or [], bool(data.get("allowAbsolute", True)))
    if path == "/api/relocate/apply":
        changes = [(c["old"], c["new"]) for c in data.get("changes", [])]
        fmg_main("scan")                       # fresh references
        return {"results": fmg_main("set_paths", changes)}
    if path == "/api/consolidate/plan":
        return fmg_consolidate_plan(data.get("dest", ""))
    if path == "/api/consolidate/start":
        with _FMG["lock"]:
            if _FMG["job"] and _FMG["job"]["running"]:
                raise RuntimeError(fmg_t("jobRunning"))
            _FMG["job"] = {"running": True, "total": 0, "index": 0, "total_bytes": 0, "done_bytes": 0,
                           "current": "", "results": [], "error": "", "cancel": False}
        sel = data.get("selected")
        threading.Thread(target=fmg_consolidate_job, args=(data.get("dest", ""), set(sel) if sel is not None else None,
                                                           fmg_lang()), daemon=True).start()
        return {"started": True}
    if path == "/api/consolidate/cancel":
        if _FMG["job"]:
            _FMG["job"]["cancel"] = True
        return {"ok": True}
    if path == "/api/job":
        return _FMG["job"] or {}
    if path == "/api/check":
        return fmg_main("check", data.get("paths", []))
    if path == "/api/browse":
        return {"path": fmg_browse_folder(fmg_clean_path(data.get("initial", "")))}
    if path == "/api/reveal":
        fmg_reveal(fmg_clean_path(data.get("path", "")))
        return {"ok": True}
    raise RuntimeError(fmg_t("unknown", path))


def fmg_start_server(p):
    for s in _FMG["servers"]:
        try:
            s.shutdown()
            s.server_close()
        except Exception:
            pass
    _FMG["servers"] = []
    try:
        srv = ThreadingHTTPServer(("127.0.0.1", p), FmgHandler)
        srv.daemon_threads = True
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        _FMG["servers"] = [srv]
        _FMG["port"], _FMG["version"] = p, FMG_VERSION
        return "http://127.0.0.1:%d" % p
    except Exception as ex:
        _FMG["port"], _FMG["version"] = p, FMG_VERSION
        return "ERREUR port %d : %s" % (p, ex)


# ===================================== INTERFACE (HTML/CSS/JS) =====================================
FMG_HTML = r"""<!doctype html>
<html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Smode Filemanager</title>
<link rel="icon" type="image/svg+xml" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Crect width='32' height='32' rx='7' fill='%234f8cff'/%3E%3Cpath d='M5.5 10.5a2 2 0 0 1 2-2h5.2l2.2 2.6h9.6a2 2 0 0 1 2 2v9.4a2 2 0 0 1-2 2h-17a2 2 0 0 1-2-2z' fill='%23fff'/%3E%3Cpath d='M11.5 17.6h8.2m-3-3.1 3.1 3.1-3.1 3.1' fill='none' stroke='%232f6fde' stroke-width='2.2' stroke-linecap='round' stroke-linejoin='round'/%3E%3C/svg%3E">
<style>
:root{--bg:#121418;--panel:#1a1d23;--card:#20242b;--card2:#262b33;--fg:#e7e9ee;--mut:#9097a6;--line:#2e333c;
--acc:#4f8cff;--acc2:#3a6fd8;--ok:#1fae63;--blue:#3b82f6;--amber:#d39b12;--orange:#e0702f;--violet:#9b5bd1;
--red:#e04848;--dred:#b02a2a;--teal:#159a90;--cyan:#2aa6d1;--grey:#7b818c;--code:#171a1f}
@media (prefers-color-scheme:light){:root{--bg:#eef0f4;--panel:#fff;--card:#fff;--card2:#f5f6f9;--fg:#1c2230;
--mut:#667085;--line:#dfe3ea;--code:#f1f3f6}}
*{box-sizing:border-box}html,body{height:100%}
body{margin:0;background:var(--bg);color:var(--fg);font:14px/1.45 "Segoe UI",system-ui,sans-serif;display:flex;flex-direction:column}
button{font:inherit;cursor:pointer}
header{display:flex;align-items:center;gap:16px;padding:12px 20px;background:var(--panel);border-bottom:1px solid var(--line)}
.logo{font-weight:700;letter-spacing:.06em}.logo small{color:var(--mut);font-weight:400;margin-left:6px;letter-spacing:0}
.proj{color:var(--mut)}.proj b{color:var(--fg)}
.dot{width:9px;height:9px;border-radius:50%;background:var(--grey);display:inline-block;margin-right:6px}
.dot.on{background:var(--ok)}.dot.off{background:var(--red)}.dot.warn{background:var(--amber)}
.sp{flex:1}
nav{display:flex;gap:4px;padding:0 20px;background:var(--panel);border-bottom:1px solid var(--line)}
nav button{background:none;border:0;color:var(--mut);padding:11px 16px;border-bottom:2px solid transparent;font-weight:600}
nav button.on{color:var(--fg);border-bottom-color:var(--acc)}nav button:hover{color:var(--fg)}
main{flex:1;overflow:auto;padding:20px}
.tab{display:none;max-width:1250px;margin:0 auto}.tab.on{display:block}
.btn{background:var(--card2);color:var(--fg);border:1px solid var(--line);border-radius:7px;padding:7px 14px}
.btn:hover{border-color:var(--acc)}.btn.pri{background:var(--acc);border-color:var(--acc);color:#fff}
.btn.pri:hover{background:var(--acc2)}.btn:disabled{opacity:.45;cursor:default}
.btn.sm{padding:2px 9px;font-size:12px;border-radius:5px}
.box{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:16px;margin-bottom:16px}
.box h2{margin:0 0 4px;font-size:15px}.box p.help{margin:0 0 12px;color:var(--mut);font-size:13px}
.row{display:flex;gap:10px;align-items:center;flex-wrap:wrap}
input[type=text]{flex:1;min-width:260px;background:var(--code);color:var(--fg);border:1px solid var(--line);
border-radius:7px;padding:8px 10px;font:13px Consolas,monospace}
input[type=text]:focus{outline:none;border-color:var(--acc)}
select{background:var(--code);color:var(--fg);border:1px solid var(--line);border-radius:7px;padding:7px;cursor:pointer}
select:hover,select:focus{outline:none;border-color:var(--acc)}
.dd{position:relative;display:inline-block}
.dd-btn{display:inline-flex;align-items:center;justify-content:space-between;gap:12px;min-width:220px;background:var(--code);
color:var(--fg);border:1px solid var(--line);border-radius:7px;padding:7px 11px;text-align:left}
.dd-btn:hover,.dd-btn:focus,.dd.open .dd-btn{outline:none;border-color:var(--acc)}
.dd-btn svg{color:var(--mut);flex:none;transition:transform .15s}.dd.open .dd-btn svg{transform:rotate(180deg)}
.dd-btn.warn{color:var(--orange)}
.dd-list{display:none;position:absolute;z-index:50;top:calc(100% + 4px);left:0;min-width:100%;max-height:320px;overflow:auto;
background:var(--card2);border:1px solid var(--line);border-radius:8px;padding:4px;box-shadow:0 10px 30px rgba(0,0,0,.35)}
.dd.open .dd-list{display:block}
.dd-opt{padding:7px 11px;border-radius:5px;cursor:pointer;white-space:nowrap}.dd-opt.sel{font-weight:600}
.dd-opt.act{background:var(--acc);color:#fff}.dd-empty{padding:7px 11px;color:var(--mut)}
.btn:focus-visible{outline:none;border-color:var(--acc)}
input[type=checkbox],input[type=radio]{accent-color:var(--acc)}
label.chk{display:inline-flex;gap:7px;align-items:center;color:var(--fg);cursor:pointer;user-select:none}
.chips{display:flex;gap:6px;flex-wrap:wrap}
.chip{display:inline-flex;align-items:center;gap:6px;background:var(--code);border:1px solid var(--line);
border-radius:999px;padding:3px 6px 3px 11px;font:12px Consolas,monospace}
.chip button{background:none;border:0;color:var(--mut);padding:0 4px;font-size:14px}.chip button:hover{color:var(--acc)}
.tiles{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:14px}
.tile{background:var(--card);border:1px solid var(--line);border-left:4px solid var(--c);border-radius:9px;
padding:9px 14px;min-width:116px;text-align:left;color:var(--fg)}
.tile b{display:block;font-size:21px;color:var(--c);line-height:1.2}.tile span{color:var(--mut);font-size:12px}
.tile.off{opacity:.35}.tile:hover{border-color:var(--acc);border-left-color:var(--c)}
.toolbar{display:flex;gap:10px;align-items:center;margin-bottom:12px;flex-wrap:wrap}
.toolbar input[type=text]{flex:0 1 340px;min-width:200px}
.list .it{background:var(--card);border:1px solid var(--line);border-left:4px solid var(--c);border-radius:9px;
padding:10px 14px;margin-bottom:8px}
.it .hd{display:flex;align-items:center;gap:10px;flex-wrap:wrap}
.badge{background:var(--c);color:#fff;font-size:10.5px;font-weight:700;letter-spacing:.05em;text-transform:uppercase;
padding:2px 8px;border-radius:999px;white-space:nowrap}
.type{font-size:10.5px;color:var(--mut);border:1px solid var(--line);border-radius:4px;padding:1px 6px}
.name{font-weight:600}.expl{color:var(--mut);font-size:12px}.size{color:var(--mut);font-size:12px;margin-left:auto}
.p{display:flex;gap:8px;align-items:baseline;margin:4px 0 0;flex-wrap:wrap;min-width:0}
.k{color:var(--mut);font-size:11px;width:44px;flex:none;text-align:right}
code{font:12px Consolas,monospace;background:var(--code);padding:2px 6px;border-radius:4px;overflow-wrap:anywhere}
.p.old code{color:var(--mut)}.p.new code{border-left:3px solid var(--c)}
.cand{display:flex;gap:8px;align-items:center;margin:4px 0 0 52px;flex-wrap:wrap}
details{margin-top:6px;color:var(--mut);font-size:12px}summary{cursor:pointer}details ul{margin:4px 0 0;padding-left:20px}
.hint{margin:8px 0 0 52px;padding:6px 10px;border-radius:6px;font-size:12px;border:1px dashed var(--c);
background:color-mix(in srgb,var(--c) 10%,transparent)}
.err{background:color-mix(in srgb,var(--red) 18%,transparent);border:1px solid var(--red);border-radius:8px;padding:10px 14px;margin-bottom:14px}
.empty{padding:40px;text-align:center;color:var(--mut)}
.grp{margin:16px 0 6px;font-weight:700;font-size:13px;color:var(--mut);letter-spacing:.03em}
.prog{height:10px;background:var(--code);border-radius:999px;overflow:hidden;border:1px solid var(--line)}
.prog i{display:block;height:100%;width:0;background:var(--acc);transition:width .3s}
.mono{font:12px Consolas,monospace}
.btn.clr{width:34px;height:34px;padding:0;display:inline-flex;align-items:center;justify-content:center;color:var(--mut)}
.btn.clr:hover{color:var(--fg)}.btn.clr svg{display:block}
mark{background:color-mix(in srgb,var(--amber) 45%,transparent);color:inherit;border-radius:2px;padding:0 1px}
table{width:100%;border-collapse:collapse}td,th{padding:7px 10px;border-bottom:1px solid var(--line);text-align:left}
th{color:var(--mut);font-weight:600;font-size:12px}
#toast{position:fixed;right:18px;bottom:18px;background:var(--card2);border:1px solid var(--line);border-radius:8px;
padding:10px 16px;opacity:0;transform:translateY(8px);transition:.25s;pointer-events:none;max-width:520px}
#toast.on{opacity:1;transform:none}#toast.bad{border-color:var(--red)}
.spin{display:inline-block;width:14px;height:14px;border:2px solid var(--mut);border-top-color:transparent;border-radius:50%;
animation:sp 0.8s linear infinite;vertical-align:-2px}@keyframes sp{to{transform:rotate(360deg)}}
.lang{display:inline-flex;border:1px solid var(--line);border-radius:7px;overflow:hidden}
.lang button{background:var(--card2);color:var(--mut);border:0;padding:6px 11px;font-weight:600;font-size:12px}
.lang button+button{border-left:1px solid var(--line)}.lang button:hover{color:var(--fg)}
.lang button.on{background:var(--acc);color:#fff}
</style></head><body>
<header>
  <div class="logo">SMODE FILEMANAGER<small>v__VERSION__</small></div>
  <div class="proj"><span class="dot" id="dot"></span><span data-i18n="proj">Project</span> <b id="proj">...</b></div>
  <div class="sp"></div>
  <button class="btn" id="rescan" data-i18n="rescan">Rescan</button>
  <div class="lang" id="lang" data-i18n-title="langTitle"><button data-l="fr">FR</button><button data-l="en">EN</button></div>
</header>
<nav>
  <button data-t="medias" class="on" data-i18n="tabMedias">Media</button>
  <button data-t="relocate">Relocate</button>
  <button data-t="consolidate">Consolidate</button>
  <button data-t="dirs">Media Directories</button>
</nav>
<main>
<section class="tab on" id="t-medias">
  <div class="tiles" id="m-tiles"></div>
  <div class="toolbar"><button class="btn clr" id="m-clear" data-i18n-title="clearTitle"><svg width="12" height="12" viewBox="0 0 12 12" aria-hidden="true"><path d="M2 2L10 10M10 2L2 10" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg></button><input type="text" id="m-q" data-i18n-ph="searchPh">
    <select id="m-scope" data-i18n-title="scopeTitle">
      <option value="ns" data-i18n="scopeNs"></option><option value="name" data-i18n="scopeName"></option>
      <option value="scene" data-i18n="scopeScene"></option><option value="path" data-i18n="scopePath"></option>
      <option value="all" data-i18n="scopeAll"></option></select>
    <span class="expl" id="m-count"></span></div>
  <div class="list" id="m-list"></div>
</section>

<section class="tab" id="t-relocate">
  <div class="box">
    <h2 data-i18n="rH2"></h2>
    <p class="help" data-i18n="rHelp"></p>
    <div class="chips" id="r-folders" style="margin-bottom:10px"></div>
    <div class="row"><input type="text" id="r-add" data-i18n-ph="rAddPh">
      <button class="btn" id="r-addbtn" data-i18n="add"></button><button class="btn" id="r-browse" data-i18n="browse"></button></div>
    <div class="row" style="margin-top:12px">
      <label class="chk"><input type="checkbox" id="r-abs" checked> <span data-i18n="rAbs"></span></label>
      <div class="sp"></div><button class="btn pri" id="r-run" data-i18n="analyse"></button></div>
  </div>
  <div id="r-out"></div>
</section>

<section class="tab" id="t-consolidate">
  <div class="box">
    <h2 data-i18n="cH2"></h2>
    <p class="help" data-i18n="cHelp"></p>
    <div class="row"><input type="text" id="c-dest" data-i18n-ph="destPh">
      <select id="c-md"><option value=""></option></select>
      <button class="btn" id="c-mdref" data-i18n-title="mdRefTitle">&#8635; Media Directories</button>
      <button class="btn" id="c-browse" data-i18n="browse"></button><button class="btn pri" id="c-run" data-i18n="analyse"></button></div>
  </div>
  <div id="c-out"></div>
</section>

<section class="tab" id="t-dirs">
  <div class="box"><h2>Media Directories</h2>
    <p class="help" data-i18n="dHelp"></p>
    <div id="d-list"></div><div style="margin-top:10px"><button class="btn" id="d-refresh" data-i18n="refresh"></button></div></div>
</section>
</main>
<div id="toast"></div>
<script>
/* ---------------- languages ---------------- */
var I18N={
fr:{proj:'Projet',rescan:'Rescanner le projet',tabMedias:'M\u00e9dias',langTitle:'Langue de l\'interface',
 clearTitle:'Effacer la recherche (\u00c9chap)',searchPh:'Rechercher...',scopeTitle:'O\u00f9 chercher',scopeNs:'Nom du fichier + Scene',
 scopeName:'Nom du fichier',scopeScene:'Scene',scopePath:'Chemins (Smode + disque)',scopeAll:'Partout (y compris Compos / calques)',
 scanning:'Scan du projet...',rH2:'Dossiers o\u00f9 chercher',
 rHelp:'Les fichiers manquants sont cherch\u00e9s par leur nom dans ces dossiers (sous-dossiers compris). Sans dossier : tous les Media Directories modifiables. Un dossier parent large (ex. le dossier du projet) trouve plus.',
 rAddPh:'Coller un chemin (les guillemets sont accept\u00e9s)',add:'Ajouter',browse:'Parcourir...',
 rAbs:'Autoriser les chemins absolus (fichier hors Media Directory, non portable)',analyse:'Analyser',cH2:'Destination',
 cHelp:'Les m\u00e9dias sont copi\u00e9s dans Destination / Scene / Type (VIDEO, IMAGE, AUDIO, 3D). Un fichier utilis\u00e9 dans plusieurs Scenes va dans _COMMUN. Les originaux restent en place. La destination doit \u00eatre dans un Media Directory.',
 destPh:'Dossier de destination',mdPh:'Media Directories...',mdRefTitle:'Relire la liste des Media Directories (apr\u00e8s en avoir ajout\u00e9 un dans Smode)',
 dHelp:'Lus dans la configuration de Smode. Pour en ajouter : panneau Media Directories de Smode, puis Rafra\u00eechir (Smode enregistre la liste quelques secondes apr\u00e8s l\'ajout).',
 refresh:'Rafra\u00eechir',thName:'Nom',thDir:'Dossier',readOnly:'lecture seule',outsideMd:'Hors Media Directory',ddEmpty:'Aucun \u00e9l\u00e9ment',
 all:'Tout',count:'{0} / {1} m\u00e9dia(s)',noMatch:'Aucun m\u00e9dia ne correspond \u00e0 \u00ab {0} \u00bb.',noMedia:'Aucun m\u00e9dia.',
 kDisk:'disque',kBefore:'avant',kAfter:'apr\u00e8s',explorer:'Explorateur',copyBtn:'Copier',copied:'Copi\u00e9 : {0}',
 use1:'utilisation',useN:'utilisations',root:'(racine)',
 noFolder:'Aucun dossier : tous les Media Directories modifiables seront fouill\u00e9s.',remove:'Retirer',
 searching:'Recherche des fichiers manquants...',rSummary:'{0} fichier(s) manquant(s) \u00b7 dossiers fouill\u00e9s :',
 applySel:'Appliquer la s\u00e9lection ({0})',
 badFolders:'Dossier(s) introuvable(s), ignor\u00e9(s) : {0}. V\u00e9rifier le chemin (faute de frappe, disque d\u00e9connect\u00e9 ?).',
 noMissing:'Aucun fichier manquant dans le projet.',absTag:'absolu',
 notfoundHint:'Ajouter en haut le dossier o\u00f9 ce fichier se trouve probablement (ou un dossier parent), puis Analyser.',
 refGone:'R\u00e9f\u00e9rence introuvable dans le projet (d\u00e9j\u00e0 modifi\u00e9e ?) : relancer Analyser.',applying:'Application...',
 relinked:'{0} fichier(s) rebranch\u00e9(s) - penser \u00e0 enregistrer le projet Smode (Ctrl+S)',analysing:'Analyse...',
 noSpace:'Espace insuffisant sur le disque de destination : {0} \u00e0 copier, {1} libres.',
 cSummary:'Destination {0} \u00b7 {1} fichier(s), {2} \u00e0 copier',free:'{0} libres',consolidateSel:'Consolider la s\u00e9lection',
 notConcerned:'Non concern\u00e9s',identical:'Copie identique d\u00e9j\u00e0 pr\u00e9sente',
 missingHint:'Lancer d\'abord un Relocate pour retrouver ce fichier.',copying:'Copie en cours',done:'Termin\u00e9',cancel:'Annuler',
 jobDone:'Consolidate termin\u00e9 - penser \u00e0 enregistrer le projet Smode (Ctrl+S)',jobErr:'Consolidate interrompu : {0}',
 retry:'Smode ne r\u00e9pond pas, nouvel essai...',
 neverIndexed:'Smode ne reconna\u00eet toujours pas ce fichier : v\u00e9rifier qu\'il est lisible (format, droits), puis relancer Analyser.',
 reloaded:'Projet recharg\u00e9 dans Smode : liste mise \u00e0 jour',mdCount:'{0} Media Directories',mdNew:' ({0} nouveau(x))',
 mdDetected:'Nouveau Media Directory d\u00e9tect\u00e9',noResp:'Smode ne r\u00e9pond pas (serveur arr\u00eat\u00e9 ?)',
 dotOff:'Serveur injoignable',dotOn:'Connect\u00e9 \u00e0 Smode',dotWarn:'Le Script ne tourne plus dans Smode (projet ferm\u00e9, Script supprim\u00e9 ou inactif ?)',
 units:['o','Ko','Mo','Go','To'],
 LAB:{ok:'OK',missing:'Manquant',absolute:'Chemin absolu',pack:'Pack Smode',found:'Retrouv\u00e9',found_abs:'Retrouv\u00e9 (absolu)',
  outside:'Hors Media Directory',ambiguous:'Ambigu',notfound:'Introuvable',pending:'En attente Smode',applied:'Appliqu\u00e9',
  applied_abs:'Appliqu\u00e9 (absolu)',failed:'\u00c9chec',planned:'\u00c0 copier',copied:'Copi\u00e9',reused:'D\u00e9j\u00e0 copi\u00e9',inplace:'D\u00e9j\u00e0 consolid\u00e9'},
 EXPL:{ok:'Fichier trouv\u00e9 dans un Media Directory',missing:'Introuvable pour Smode : utiliser Relocate',
  absolute:'Trouv\u00e9 hors de tout Media Directory (non portable)',pack:'M\u00e9dia d\'un pack Smode en lecture seule',
  found:'Pr\u00eat \u00e0 appliquer',found_abs:'Hors Media Directory : sera rebranch\u00e9 en chemin absolu',
  outside:'Trouv\u00e9 mais les chemins absolus sont d\u00e9sactiv\u00e9s',ambiguous:'Plusieurs candidats \u00e0 \u00e9galit\u00e9 : choisir le bon',
  notfound:'Aucun fichier de ce nom : ajouter un dossier o\u00f9 chercher (un dossier parent large marche bien)',
  pending:'Fichier pr\u00e9sent sur le disque, Smode ne l\'a pas encore index\u00e9 : v\u00e9rification automatique',
  applied:'Rebranch\u00e9 et v\u00e9rifi\u00e9',applied_abs:'Rebranch\u00e9 en chemin absolu',failed:'Erreur',planned:'Sera copi\u00e9 puis rebranch\u00e9',
  copied:'Copi\u00e9, rebranch\u00e9 et v\u00e9rifi\u00e9',reused:'Copie identique d\u00e9j\u00e0 pr\u00e9sente : rebranch\u00e9 sans recopier',inplace:'D\u00e9j\u00e0 dans la destination'}},
en:{proj:'Project',rescan:'Rescan project',tabMedias:'Media',langTitle:'Interface language',
 clearTitle:'Clear search (Esc)',searchPh:'Search...',scopeTitle:'Search in',scopeNs:'File name + Scene',
 scopeName:'File name',scopeScene:'Scene',scopePath:'Paths (Smode + disk)',scopeAll:'Everywhere (including Compos / layers)',
 scanning:'Scanning the project...',rH2:'Folders to search',
 rHelp:'Missing files are searched by name in these folders (subfolders included). No folder: all writable Media Directories. A broad parent folder (e.g. the project folder) finds more.',
 rAddPh:'Paste a path (quotes are accepted)',add:'Add',browse:'Browse...',
 rAbs:'Allow absolute paths (file outside any Media Directory, not portable)',analyse:'Analyse',cH2:'Destination',
 cHelp:'Media are copied to Destination / Scene / Type (VIDEO, IMAGE, AUDIO, 3D). A file used in several Scenes goes to _COMMUN. Originals stay in place. The destination must be inside a Media Directory.',
 destPh:'Destination folder',mdPh:'Media Directories...',mdRefTitle:'Reload the Media Directories list (after adding one in Smode)',
 dHelp:'Read from the Smode configuration. To add one: Media Directories panel in Smode, then Refresh (Smode saves the list a few seconds after the addition).',
 refresh:'Refresh',thName:'Name',thDir:'Folder',readOnly:'read-only',outsideMd:'Outside Media Directories',ddEmpty:'No item',
 all:'All',count:'{0} / {1} media',noMatch:'No media matches "{0}".',noMedia:'No media.',
 kDisk:'disk',kBefore:'before',kAfter:'after',explorer:'Explorer',copyBtn:'Copy',copied:'Copied: {0}',
 use1:'use',useN:'uses',root:'(root)',
 noFolder:'No folder: all writable Media Directories will be searched.',remove:'Remove',
 searching:'Searching for missing files...',rSummary:'{0} missing file(s) \u00b7 searched folders:',
 applySel:'Apply selection ({0})',
 badFolders:'Folder(s) not found, ignored: {0}. Check the path (typo, disconnected drive?).',
 noMissing:'No missing file in the project.',absTag:'absolute',
 notfoundHint:'Add above the folder where this file probably is (or a parent folder), then Analyse.',
 refGone:'Reference not found in the project (already changed?): run Analyse again.',applying:'Applying...',
 relinked:'{0} file(s) relinked - remember to save the Smode project (Ctrl+S)',analysing:'Analysing...',
 noSpace:'Not enough space on the destination drive: {0} to copy, {1} free.',
 cSummary:'Destination {0} \u00b7 {1} file(s), {2} to copy',free:'{0} free',consolidateSel:'Consolidate selection',
 notConcerned:'Not concerned',identical:'Identical copy already there',
 missingHint:'Run a Relocate first to find this file.',copying:'Copying',done:'Done',cancel:'Cancel',
 jobDone:'Consolidate done - remember to save the Smode project (Ctrl+S)',jobErr:'Consolidate stopped: {0}',
 retry:'Smode is not responding, retrying...',
 neverIndexed:'Smode still does not recognise this file: check it is readable (format, permissions), then run Analyse again.',
 reloaded:'Project reloaded in Smode: list updated',mdCount:'{0} Media Directories',mdNew:' ({0} new)',
 mdDetected:'New Media Directory detected',noResp:'Smode is not responding (server stopped?)',
 dotOff:'Server unreachable',dotOn:'Connected to Smode',dotWarn:'The Script no longer runs in Smode (project closed, Script removed or inactive?)',
 units:['B','KB','MB','GB','TB'],
 LAB:{ok:'OK',missing:'Missing',absolute:'Absolute path',pack:'Smode pack',found:'Found',found_abs:'Found (absolute)',
  outside:'Outside Media Directories',ambiguous:'Ambiguous',notfound:'Not found',pending:'Waiting for Smode',applied:'Applied',
  applied_abs:'Applied (absolute)',failed:'Failed',planned:'To copy',copied:'Copied',reused:'Already copied',inplace:'Already consolidated'},
 EXPL:{ok:'File found in a Media Directory',missing:'Not found by Smode: use Relocate',
  absolute:'Found outside any Media Directory (not portable)',pack:'Media from a read-only Smode pack',
  found:'Ready to apply',found_abs:'Outside Media Directories: will be relinked with an absolute path',
  outside:'Found, but absolute paths are disabled',ambiguous:'Several candidates tie: pick the right one',
  notfound:'No file with this name: add a folder to search (a broad parent folder works well)',
  pending:'File on disk, not indexed by Smode yet: checking automatically',
  applied:'Relinked and verified',applied_abs:'Relinked with an absolute path',failed:'Error',planned:'Will be copied then relinked',
  copied:'Copied, relinked and verified',reused:'Identical copy already there: relinked without copying',inplace:'Already in the destination'}}};
function initialLang(){var l=null;try{l=localStorage.getItem('fmg_lang')}catch(e){}
 if(l!=='fr'&&l!=='en')l=(navigator.language||'').toLowerCase().indexOf('fr')===0?'fr':'en';return l}
var S={items:[],mfilter:'*',rFolders:[],reloc:null,rFilter:'*',plan:null,cFilter:'*',dirs:[],job:null,session:null,
 lang:initialLang(),scanning:false,alive:undefined};
/* t('key', a, b...): text in the chosen language, {0} {1}... replaced by the arguments */
function t(k){var v=I18N[S.lang][k];if(v==null)v=I18N.fr[k];if(v==null)v=k;var a=arguments;
 return String(v).replace(/\{(\d+)\}/g,function(m,i){return a[+i+1]!=null?a[+i+1]:''})}
function LAB(s){return I18N[S.lang].LAB[s]||s}
function EXPL(s){return I18N[S.lang].EXPL[s]||''}
function applyStatic(){document.documentElement.lang=S.lang;
 document.querySelectorAll('[data-i18n]').forEach(function(el){el.textContent=t(el.dataset.i18n)});
 document.querySelectorAll('[data-i18n-ph]').forEach(function(el){el.placeholder=t(el.dataset.i18nPh)});
 document.querySelectorAll('[data-i18n-title]').forEach(function(el){el.title=t(el.dataset.i18nTitle)});
 document.querySelectorAll('#lang button').forEach(function(b){b.classList.toggle('on',b.dataset.l===S.lang)})}
function setLang(l){if(l!=='fr'&&l!=='en')return;S.lang=l;try{localStorage.setItem('fmg_lang',l)}catch(e){}
 applyStatic();ddRefresh($('m-scope'));renderMedias();renderFolders();renderDirs();syncMd();setDot(S.alive);
 if(S.reloc)renderReloc();if(S.plan)renderPlan()}
document.querySelectorAll('#lang button').forEach(function(b){b.onclick=function(){setLang(b.dataset.l)}});

var COL={ok:'--ok',missing:'--red',absolute:'--amber',pack:'--grey',found:'--blue',found_abs:'--amber',outside:'--orange',
 ambiguous:'--violet',notfound:'--red',pending:'--cyan',applied:'--ok',applied_abs:'--amber',failed:'--dred',
 planned:'--blue',copied:'--ok',reused:'--teal',inplace:'--grey'};
function $(id){return document.getElementById(id)}
function esc(t){return String(t==null?'':t).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;')}
function col(s){return 'var('+(COL[s]||'--grey')+')'}
function base(p){p=String(p||'').replace(/\\/g,'/');return p.split('/').pop()}
function fmt(n){if(!n)return '';var u=I18N[S.lang].units,i=0;while(n>=1024&&i<4){n/=1024;i++}return n.toFixed(i?1:0)+' '+u[i]}
function fmt0(n){return fmt(n)||('0 '+I18N[S.lang].units[0])}
function toast(m,bad){var e=$('toast');e.textContent=m;e.className='on'+(bad?' bad':'');clearTimeout(e._h);e._h=setTimeout(function(){e.className=''},3500)}
function api(path,data){var d=data||{};d.lang=S.lang;
 return fetch(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(d)})
 .then(function(r){return r.json().then(function(j){if(!r.ok)throw new Error(j.error||r.status);return j})},
 function(e){setDot(null);throw new Error(t('noResp'))})}
/* status dot: green = Smode processes requests, orange = server reachable but Script inactive, red = server unreachable */
function setDot(alive){S.alive=alive;if(alive===undefined)return;var d=$('dot');d.className='dot '+(alive===null?'off':alive?'on':'warn');
 d.title=alive===null?t('dotOff'):alive?t('dotOn'):t('dotWarn')}
function copy(x){if(navigator.clipboard)navigator.clipboard.writeText(x);toast(t('copied',x))}
function tools(abs){if(!abs)return '';var a=esc(abs);return ' <button class="btn sm" data-reveal="'+a+'">'+t('explorer')+'</button>'+
 ' <button class="btn sm" data-copy="'+a+'">'+t('copyBtn')+'</button>'}
function uses(u){if(!u||!u.length)return '';return '<details><summary>'+u.length+' '+(u.length>1?t('useN'):t('use1'))+' &middot; '+esc(u[0]||t('root'))+
 '</summary><ul>'+u.map(function(x){return '<li>'+esc(x||t('root'))+'</li>'}).join('')+'</ul></details>'}
function tiles(el,list,order,cur,cb){var c={};list.forEach(function(e){c[e.state]=(c[e.state]||0)+1});
 var h='<button class="tile'+(cur==='*'?'':' off')+'" data-f="*" style="--c:var(--fg)"><b>'+list.length+'</b><span>'+t('all')+'</span></button>';
 order.forEach(function(k){if(c[k])h+='<button class="tile'+(cur==='*'||cur===k?'':' off')+'" data-f="'+k+'" style="--c:'+col(k)+'"><b>'+c[k]+'</b><span>'+LAB(k)+'</span></button>'});
 el.innerHTML=h;el.querySelectorAll('.tile').forEach(function(b){b.onclick=function(){cb(b.dataset.f)}})}
document.addEventListener('click',function(ev){var b=ev.target.closest('[data-reveal],[data-copy]');if(!b)return;
 if(b.dataset.copy!=null)copy(b.dataset.copy);else api('/api/reveal',{path:b.dataset.reveal}).catch(function(e){toast(e.message,1)})});
document.querySelectorAll('nav button').forEach(function(b){b.onclick=function(){
 document.querySelectorAll('nav button').forEach(function(x){x.classList.toggle('on',x===b)});
 document.querySelectorAll('.tab').forEach(function(x){x.classList.toggle('on',x.id==='t-'+b.dataset.t)})}});

/* ---------------- MEDIA ---------------- */
function scan(){S.scanning=true;renderMedias();
 return api('/api/scan').then(function(r){S.items=r.items;S.scanning=false;$('proj').textContent=r.project;renderMedias()})
 .catch(function(e){S.scanning=false;$('m-list').innerHTML='<div class="err">'+esc(e.message)+'</div>'})}
/* highlights q in x (plain text -> escaped HTML) */
function hl(x,q){x=String(x==null?'':x);if(!q)return esc(x);var lo=x.toLowerCase(),out='',i=0,j;
 while((j=lo.indexOf(q,i))>=0){out+=esc(x.slice(i,j))+'<mark>'+esc(x.slice(j,j+q.length))+'</mark>';i=j+q.length}return out+esc(x.slice(i))}
/* fields searched for the chosen scope */
function mFields(e,sc){var name=base(e.path),scenes=e.scenes.join(' ');
 if(sc==='name')return name;if(sc==='scene')return scenes;if(sc==='path')return e.path+' '+(e.abs||'');
 if(sc==='all')return name+' '+scenes+' '+e.path+' '+(e.abs||'')+' '+e.users.join(' ');return name+' '+scenes}
function renderMedias(){if(S.scanning&&!S.items.length){$('m-list').innerHTML='<div class="empty"><span class="spin"></span> '+t('scanning')+'</div>';return}
 var q=$('m-q').value.trim().toLowerCase(),sc=$('m-scope').value;
 var hit=S.items.filter(function(e){return !q||mFields(e,sc).toLowerCase().indexOf(q)>=0});
 tiles($('m-tiles'),hit,['missing','absolute','ok','pack'],S.mfilter,function(f){S.mfilter=f;renderMedias()});
 var l=hit.filter(function(e){return S.mfilter==='*'||e.state===S.mfilter});
 $('m-count').textContent=q?t('count',hit.length,S.items.length):'';
 var qn=(sc==='ns'||sc==='name'||sc==='all')?q:'',qs=(sc==='ns'||sc==='scene'||sc==='all')?q:'',qp=(sc==='path'||sc==='all')?q:'';
 $('m-list').innerHTML=l.length?l.map(function(e){return '<div class="it" style="--c:'+col(e.state)+'"><div class="hd"><span class="badge">'+LAB(e.state)+
  '</span><span class="type">'+e.type+'</span><span class="name">'+hl(base(e.path),qn)+'</span><span class="expl">'+hl(e.scenes.join(', '),qs)+
  '</span><span class="size">'+fmt(e.size)+'</span></div><div class="p"><span class="k">Smode</span><code>'+hl(e.path,qp)+'</code></div>'+
  (e.abs?'<div class="p"><span class="k">'+t('kDisk')+'</span><code>'+hl(e.abs,qp)+'</code>'+tools(e.abs)+'</div>':'')+uses(e.users)+'</div>'}).join('')
  :'<div class="empty">'+(q?esc(t('noMatch',q)):t('noMedia'))+'</div>'}
$('m-q').oninput=renderMedias;$('m-scope').onchange=renderMedias;
$('m-clear').onclick=function(){$('m-q').value='';renderMedias();$('m-q').focus()};
$('m-q').onkeydown=function(e){if(e.key==='Escape')$('m-clear').onclick()};$('rescan').onclick=function(){scan();loadInfo()};

/* ---------------- RELOCATE ---------------- */
function renderFolders(){$('r-folders').innerHTML=S.rFolders.length?S.rFolders.map(function(f,i){return '<span class="chip">'+esc(f)+
 '<button data-i="'+i+'" title="'+esc(t('remove'))+'">&times;</button></span>'}).join(''):'<span class="expl">'+t('noFolder')+'</span>';
 $('r-folders').querySelectorAll('button').forEach(function(b){b.onclick=function(){S.rFolders.splice(+b.dataset.i,1);renderFolders()}})}
function addFolder(p){p=String(p||'').trim().replace(/^["']|["']$/g,'');if(p&&S.rFolders.indexOf(p)<0)S.rFolders.push(p);renderFolders()}
$('r-addbtn').onclick=function(){addFolder($('r-add').value);$('r-add').value=''};
$('r-add').onkeydown=function(e){if(e.key==='Enter')$('r-addbtn').onclick()};
$('r-browse').onclick=function(){api('/api/browse',{initial:S.rFolders[0]||''}).then(function(r){if(r.path)addFolder(r.path)})
 .catch(function(e){toast(e.message,1)})};
$('r-run').onclick=function(){$('r-out').innerHTML='<div class="empty"><span class="spin"></span> '+t('searching')+'</div>';
 api('/api/relocate/analyze',{folders:S.rFolders,allowAbsolute:$('r-abs').checked}).then(function(r){
  r.entries.forEach(function(e){e.sel=(e.state==='found'||e.state==='found_abs');e.pick=-1});S.reloc=r;S.rFilter='*';renderReloc();
  var pend=r.entries.filter(function(e){return e.state==='pending'}).map(function(e){return e.old});if(pend.length)watchPending(pend,'reloc')})
 .catch(function(e){$('r-out').innerHTML='<div class="err">'+esc(e.message)+'</div>'})};
function renderReloc(){var r=S.reloc;if(!r)return;var order=['failed','notfound','ambiguous','outside','found_abs','found','pending','applied_abs','applied'];
 var n=r.entries.filter(function(e){return e.sel&&(e.new||e.pick>=0)}).length;
 var h='<div class="tiles" id="r-tiles"></div><div class="toolbar"><span class="expl">'+esc(t('rSummary',r.entries.length))+' '+
  r.folders.map(esc).join(' ; ')+'</span><div class="sp"></div><button class="btn pri" id="r-apply"'+(n?'':' disabled')+'>'+esc(t('applySel',n))+'</button></div>';
 if(r.badFolders&&r.badFolders.length)h='<div class="err">'+esc(t('badFolders',r.badFolders.join(' ; ')))+'</div>'+h;
 if(!r.entries.length)h+='<div class="empty">'+t('noMissing')+'</div>';
 h+='<div class="list">';
 r.entries.forEach(function(e,i){if(S.rFilter!=='*'&&e.state!==S.rFilter)return;
  var canSel=(e.state==='found'||e.state==='found_abs'||(e.state==='ambiguous'&&e.pick>=0));
  h+='<div class="it" style="--c:'+col(e.state)+'"><div class="hd">'+
   ((e.state==='found'||e.state==='found_abs'||e.state==='ambiguous')?'<input type="checkbox" data-sel="'+i+'"'+(e.sel&&canSel?' checked':'')+(canSel?'':' disabled')+'>':'')+
   '<span class="badge">'+LAB(e.state)+'</span><span class="type">'+e.type+'</span><span class="name">'+esc(base(e.old))+'</span><span class="expl">'+EXPL(e.state)+'</span></div>'+
   '<div class="p old"><span class="k">'+t('kBefore')+'</span><code>'+esc(e.old)+'</code></div>'+
   (e.new&&e.state!=='pending'?'<div class="p new"><span class="k">'+t('kAfter')+'</span><code>'+esc(e.new)+'</code>'+tools(e.abs)+'</div>':'')+
   (e.state==='pending'?'<div class="p"><span class="k">'+t('kDisk')+'</span><code>'+esc(e.abs)+'</code>'+tools(e.abs)+'</div>':'');
  if(e.cands)e.cands.forEach(function(c,j){h+='<label class="cand"><input type="radio" name="pk'+i+'" data-pick="'+i+'" value="'+j+'"'+(e.pick===j?' checked':'')+
   '><code>'+esc(c.abs)+'</code>'+(c.absolute?'<span class="type">'+t('absTag')+'</span>':'')+tools(c.abs)+'</label>'});
  if(e.state==='notfound')h+='<div class="hint">'+t('notfoundHint')+'</div>';
  if(e.err)h+='<div class="hint">'+esc(t(e.err))+'</div>';
  h+=uses(e.users)+'</div>'});
 $('r-out').innerHTML=h+'</div>';
 tiles($('r-tiles'),r.entries,order,S.rFilter,function(f){S.rFilter=f;renderReloc()});
 $('r-out').querySelectorAll('[data-sel]').forEach(function(c){c.onchange=function(){r.entries[+c.dataset.sel].sel=c.checked;renderReloc()}});
 $('r-out').querySelectorAll('[data-pick]').forEach(function(c){c.onchange=function(){var e=r.entries[+c.dataset.pick];e.pick=+c.value;e.sel=true;renderReloc()}});
 var ab=$('r-apply');if(ab)ab.onclick=applyReloc}
function applyReloc(){var r=S.reloc,ch=[],map={};
 r.entries.forEach(function(e){if(!e.sel)return;var nw=e.state==='ambiguous'?(e.pick>=0?e.cands[e.pick].new:null):e.new;
  if(nw&&(e.state==='found'||e.state==='found_abs'||e.state==='ambiguous')){ch.push({old:e.old,new:nw});map[e.old]=e}});
 if(!ch.length)return;$('r-apply').disabled=true;$('r-apply').innerHTML='<span class="spin"></span> '+t('applying');
 api('/api/relocate/apply',{changes:ch}).then(function(res){var pend=[];
  Object.keys(res.results).forEach(function(old){var e=map[old],s=res.results[old];var abs=e.state==='found_abs'||(e.state==='ambiguous'&&e.cands[e.pick].absolute);
   if(e.state==='ambiguous'){e.abs=e.cands[e.pick].abs;e.new=e.cands[e.pick].new;e.cands=null}
   e.isAbs=abs;e.sel=false;e.state=s==='ok'?(abs?'applied_abs':'applied'):s==='pending'?'pending':'failed';
   if(s==='failed')e.err='refGone';if(s==='pending')pend.push(e.new)});
  renderReloc();toast(t('relinked',ch.length));scan();
  if(pend.length)watchPending(pend,'reloc')})
 .catch(function(e){toast(e.message,1);renderReloc()})}

/* ---------------- CONSOLIDATE ---------------- */
function normP(p){return String(p||'').trim().replace(/^["']|["']$/g,'').replace(/\//g,'\\').replace(/\\+$/,'').toLowerCase()}
/* the list shows the Media Directory containing the destination (or "outside Media Directories") */
function syncMd(){syncMd0();ddRefresh($('c-md'))}
function syncMd0(){var d=normP($('c-dest').value),sel=$('c-md'),best=null;
 S.dirs.forEach(function(m){if(m.readOnly)return;var r=normP(m.dir);if((d===r||d.indexOf(r+'\\')===0)&&(!best||r.length>normP(best.dir).length))best=m});
 var x=sel.querySelector('option[data-sub]');if(x)x.remove();
 sel.options[0].textContent=t('mdPh');sel.dataset.warn='';
 if(!d){sel.value='';return}
 if(best&&normP(best.dir)===d){sel.value=best.dir}
 else if(best){var o=document.createElement('option');o.dataset.sub='1';o.value='__sub';
  o.textContent=best.name+' \u203a '+$('c-dest').value.trim().replace(/^["']|["']$/g,'').slice(best.dir.length).replace(/^[\\\/]+/,'');
  sel.appendChild(o);sel.value='__sub'}
 else{sel.value='';sel.options[0].textContent=t('outsideMd');sel.dataset.warn='1'}}
$('c-md').onchange=function(){if(this.value&&this.value!=='__sub')$('c-dest').value=this.value;syncMd()};
$('c-dest').oninput=syncMd;
function mdRefresh(silent){var before=S.dirs.length;return loadInfo().then(function(){
 if(!silent)toast(t('mdCount',S.dirs.length)+(S.dirs.length>before?t('mdNew',S.dirs.length-before):''));
 if(S.plan&&S.plan.error&&$('c-dest').value)$('c-run').onclick()})}
$('c-mdref').onclick=function(){mdRefresh(false)};
/* destination outside Media Directories: reload the list every 3 s (Smode saves it with a delay) */
setInterval(function(){if(S.plan&&S.plan.error&&$('c-dest').value&&!(S.job&&S.job.running)){var n=S.dirs.length;
 loadInfo().then(function(){if(S.dirs.length!==n){toast(t('mdDetected'));$('c-run').onclick()}})}},3000);
$('c-browse').onclick=function(){api('/api/browse',{initial:$('c-dest').value}).then(function(r){if(r.path){$('c-dest').value=r.path;syncMd()}})
 .catch(function(e){toast(e.message,1)})};
$('c-run').onclick=function(){$('c-out').innerHTML='<div class="empty"><span class="spin"></span> '+t('analysing')+'</div>';
 api('/api/consolidate/plan',{dest:$('c-dest').value}).then(function(r){r.entries.forEach(function(e){e.sel=e.state==='planned'});S.plan=r;S.cFilter='*';renderPlan()})
 .catch(function(e){$('c-out').innerHTML='<div class="err">'+esc(e.message)+'</div>'})};
function renderPlan(){var r=S.plan;if(!r)return;var order=['failed','missing','pending','planned','copied','reused','inplace','pack'];
 var sel=r.entries.filter(function(e){return e.sel&&e.state==='planned'});
 var bytes=sel.reduce(function(a,e){return a+(e.exists?0:(e.size||0))},0);
 var full=r.free!=null&&bytes>r.free;
 var h=r.error?'<div class="err">'+esc(r.error)+'</div>':'';
 if(full&&!r.error)h+='<div class="err">'+esc(t('noSpace',fmt0(bytes),fmt0(r.free)))+'</div>';
 h+='<div class="tiles" id="c-tiles"></div><div class="toolbar"><span class="expl">'+
  esc(t('cSummary','\u0001',sel.length,fmt0(bytes))).replace('\u0001','<code>'+esc(r.dest||'-')+'</code>')+
  (r.free!=null?' &middot; '+esc(t('free',fmt0(r.free))):'')+'</span><div class="sp"></div>'+
  '<button class="btn pri" id="c-go"'+(sel.length&&!r.error&&!full?'':' disabled')+'>'+t('consolidateSel')+'</button></div>';
 h+='<div id="c-prog"></div>';
 var groups={},rest=[];r.entries.forEach(function(e,i){e._i=i;if(S.cFilter!=='*'&&e.state!==S.cFilter)return;if(e.group)(groups[e.group]=groups[e.group]||[]).push(e);else rest.push(e)});
 Object.keys(groups).sort().forEach(function(g){h+='<div class="grp">'+esc(g)+'</div><div class="list">'+groups[g].map(planItem).join('')+'</div>'});
 if(rest.length)h+='<div class="grp">'+t('notConcerned')+'</div><div class="list">'+rest.map(planItem).join('')+'</div>';
 $('c-out').innerHTML=h;tiles($('c-tiles'),r.entries,order,S.cFilter,function(f){S.cFilter=f;renderPlan()});
 $('c-out').querySelectorAll('[data-csel]').forEach(function(c){c.onchange=function(){r.entries[+c.dataset.csel].sel=c.checked;renderPlan()}});
 var go=$('c-go');if(go)go.onclick=startJob;if(S.job&&S.job.running)renderJob()}
function planItem(e){return '<div class="it" style="--c:'+col(e.state)+'"><div class="hd">'+(e.state==='planned'?'<input type="checkbox" data-csel="'+e._i+'"'+(e.sel?' checked':'')+'>':'')+
 '<span class="badge">'+LAB(e.state)+'</span><span class="type">'+e.type+'</span><span class="name">'+esc(base(e.old))+'</span><span class="expl">'+
 (e.state==='planned'&&e.exists?t('identical'):EXPL(e.state))+(e.err?' : '+esc(t(e.err)):'')+'</span><span class="size">'+fmt(e.size)+'</span></div>'+
 '<div class="p old"><span class="k">'+t('kBefore')+'</span><code>'+esc(e.old)+'</code>'+tools(e.src)+'</div>'+
 (e.new?'<div class="p new"><span class="k">'+t('kAfter')+'</span><code>'+esc(e.new)+'</code>'+((e.state==='copied'||e.state==='reused'||e.state==='pending')?tools(e.target):'')+'</div>':'')+
 (e.state==='missing'?'<div class="hint">'+t('missingHint')+'</div>':'')+uses(e.users)+'</div>'}
function startJob(){var r=S.plan;var sel=r.entries.filter(function(e){return e.sel&&e.state==='planned'}).map(function(e){return e.old});
 api('/api/consolidate/start',{dest:r.dest,selected:sel}).then(function(){S.job={running:true};renderPlan();pollJob()}).catch(function(e){toast(e.message,1)})}
function renderJob(){var j=S.job,el=$('c-prog');if(!el||!j)return;var pc=j.total_bytes?Math.round(100*j.done_bytes/j.total_bytes):(j.total?Math.round(100*(j.index||0)/j.total):0);
 el.innerHTML='<div class="box"><div class="row"><b>'+(j.running?t('copying'):t('done'))+'</b><span class="expl">'+(j.index||0)+' / '+(j.total||0)+' &middot; '+
  fmt0(j.done_bytes)+' / '+fmt0(j.total_bytes)+'</span><span class="mono expl">'+esc(j.current||'')+'</span><div class="sp"></div>'+
  (j.running?'<button class="btn sm" id="c-cancel">'+t('cancel')+'</button>':'')+'</div><div class="prog" style="margin-top:10px"><i style="width:'+pc+'%"></i></div>'+
  (j.error?'<div class="err" style="margin:10px 0 0">'+esc(j.error)+'</div>':'')+'</div>';
 var c=$('c-cancel');if(c)c.onclick=function(){api('/api/consolidate/cancel')}}
function pollJob(){fetch('/api/job',{method:'POST'}).then(function(r){return r.json()}).then(function(j){S.job=j;
 var byOld={};(j.results||[]).forEach(function(x){byOld[x.old]=x});
 if(S.plan)S.plan.entries.forEach(function(e){var x=byOld[e.old];if(x){e.state=x.state;e.err=x.error;e.sel=false}});
 if(j.running){renderJob();var el=$('c-prog');if(!el)renderPlan();setTimeout(pollJob,500)}
 else{renderPlan();renderJob();scan();var pend=(j.results||[]).filter(function(x){return x.state==='pending'}).map(function(x){return x.new});
  toast(j.error?t('jobErr',j.error):t('jobDone'),!!j.error);
  if(pend.length)watchPending(pend,'plan')}},
 function(){toast(t('retry'),1);setTimeout(pollJob,2000)})}

/* ---------------- check of the waiting files ---------------- */
/* re-checks every 2 s (40 s max); a single project rescan at the end (a scan freezes Smode for a few
   seconds on a large project); after that, files never recognised become Failed with an explanation */
function watchPending(paths,where,n){n=n||0;var list=where==='reloc'?(S.reloc&&S.reloc.entries):(S.plan&&S.plan.entries);
 function redraw(){where==='reloc'?renderReloc():renderPlan()}
 if(!paths.length){scan();return}
 if(n>=20){(list||[]).forEach(function(e){if(e.state==='pending'&&paths.indexOf(e.new)>=0){e.state='failed';e.err='neverIndexed'}});
  redraw();scan();return}
 setTimeout(function(){api('/api/check',{paths:paths}).then(function(res){
  var left=paths.filter(function(p){return res[p]!=='ok'});
  (list||[]).forEach(function(e){if(e.state==='pending'&&res[e.new]==='ok')e.state=where==='reloc'?(e.isAbs?'applied_abs':'applied'):'copied'});
  if(left.length<paths.length)redraw();
  watchPending(left,where,n+1)},function(){watchPending(paths,where,n+1)})},2000)}

/* ---------------- MEDIA DIRECTORIES ---------------- */
/* the Script restarted in Smode (project reopened...): start again from scratch on the current project */
function checkSession(s){if(s==null)return;if(S.session==null){S.session=s;return}if(s===S.session)return;S.session=s;
 S.reloc=null;S.plan=null;S.job=null;$('r-out').innerHTML='';$('c-out').innerHTML='';
 toast(t('reloaded'));scan();loadInfo()}
function renderDirs(){$('d-list').innerHTML='<table><tr><th>'+t('thName')+'</th><th>'+t('thDir')+'</th><th></th></tr>'+S.dirs.map(function(d){return '<tr><td><b>'+esc(d.name)+'</b>'+
  (d.readOnly?' <span class="type">'+t('readOnly')+'</span>':'')+'</td><td class="mono">'+esc(d.dir)+'</td><td>'+tools(d.dir)+'</td></tr>'}).join('')+'</table>'}
function loadInfo(){return api('/api/info').then(function(r){S.dirs=r.mediaDirs;setDot(!!r.alive);checkSession(r.session);renderDirs();
 $('c-md').innerHTML='<option value=""></option>'+r.mediaDirs.filter(function(d){return !d.readOnly}).map(function(d){
  return '<option value="'+esc(d.dir)+'">'+esc(d.name)+'</option>'}).join('');syncMd()})}
$('d-refresh').onclick=loadInfo;
/* ---------------- custom drop-down lists (the highlight of a native <select> is forced by Windows) ---------------- */
function ddRefresh(sel){var w=sel._dd;if(!w)return;var o=sel.options[sel.selectedIndex];w.lab.textContent=o?o.textContent:'';
 w.btn.classList.toggle('warn',sel.dataset.warn==='1');w.btn.title=sel.title||''}
function makeDD(sel){var w=document.createElement('div');w.className='dd';sel.parentNode.insertBefore(w,sel);w.appendChild(sel);sel.style.display='none';
 var btn=document.createElement('button');btn.type='button';btn.className='dd-btn';btn.title=sel.title||'';
 btn.innerHTML='<span class="dd-lab"></span><svg width="10" height="6" viewBox="0 0 10 6" aria-hidden="true"><path d="M1 1l4 4 4-4" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>';
 var list=document.createElement('div');list.className='dd-list';w.appendChild(btn);w.appendChild(list);
 list.onmousedown=function(e){e.preventDefault()};   /* keeps the focus: the scrollbar no longer closes the list */
 sel._dd={btn:btn,lab:btn.firstChild};var act=-1,opts=[];
 function close(){w.classList.remove('open')}
 function mark(){opts.forEach(function(o,i){o.el.classList.toggle('act',i===act)});if(opts[act])opts[act].el.scrollIntoView({block:'nearest'})}
 function pick(i){var o=opts[i];if(!o)return;sel.value=o.v;close();ddRefresh(sel);sel.dispatchEvent(new Event('change'));btn.focus()}
 function open(){opts=[];list.innerHTML='';Array.prototype.forEach.call(sel.options,function(op){if(op.value===''||op.value==='__sub')return;
   var el=document.createElement('div');el.className='dd-opt'+(op.value===sel.value?' sel':'');el.textContent=op.textContent;var i=opts.length;
   el.onmousedown=function(e){e.preventDefault();pick(i)};el.onmouseenter=function(){act=i;mark()};list.appendChild(el);opts.push({v:op.value,el:el})});
  if(!opts.length)list.innerHTML='<div class="dd-empty">'+t('ddEmpty')+'</div>';
  act=Math.max(0,opts.map(function(o){return o.v}).indexOf(sel.value));w.classList.add('open');mark()}
 btn.onclick=function(){w.classList.contains('open')?close():open()};
 btn.onblur=function(){setTimeout(close,120)};
 btn.onkeydown=function(e){var isOpen=w.classList.contains('open');
  if(e.key==='ArrowDown'||e.key==='ArrowUp'){e.preventDefault();if(!isOpen){open();return}
   act=Math.min(opts.length-1,Math.max(0,act+(e.key==='ArrowDown'?1:-1)));mark()}
  else if(e.key==='Enter'||e.key===' '){e.preventDefault();if(isOpen)pick(act);else open()}
  else if(e.key==='Escape'&&isOpen){e.preventDefault();close()}};
 ddRefresh(sel)}
applyStatic();
makeDD($('m-scope'));makeDD($('c-md'));
renderFolders();loadInfo();scan();
setInterval(function(){fetch('/api/info',{method:'POST'}).then(function(r){return r.json()}).then(function(j){setDot(!!j.alive);checkSession(j.session)},
 function(){setDot(null)})},5000);
</script></body></html>"""


# ===================================== LOOP (every frame) =====================================
_fmg_port = int(script.port.get())
_fmg_now = time.time()
for _t in ("SERVEUR", "ETAT"):
    if str(getattr(script, _t)) != "-" * 40:
        setattr(script, _t, "-" * 40)
# The Script (re)starts: first run of the Smode session, or it had not run for a few seconds (project closed
# and reopened, Script added to the project, Script set back to At Every Update). The server and _FMG survive
# closing the project, so the server start alone cannot be relied on.
_fmg_resumed = _FMG["version"] is None or _fmg_now - _FMG["tick"] > 3
if _fmg_resumed:
    _FMG["session"] += 1
    _FMG["refs"] = {}                      # Oil references of the old project: never use them again
    if _FMG["job"] and _FMG["job"].get("running"):
        _FMG["job"]["cancel"] = True
# (Re)start the server only on the first run, when the version or the port changes, or on Restart Server.
# A failure (port already taken) is NOT retried on every frame: change the port or tick Restart Server.
_fmg_restart = bool(script.restartServer.get())
if _FMG["version"] != FMG_VERSION or _FMG["port"] != _fmg_port or _fmg_restart:
    if _fmg_restart:
        script.restartServer.set(False)
    script.status = fmg_start_server(_fmg_port)
_fmg_url = "http://127.0.0.1:%d" % _fmg_port
if script.openInterface.get():
    script.openInterface.set(False)
    if _FMG["servers"]:
        fmg_open_window(_fmg_url)
elif _fmg_resumed and script.autoOpen.get() and _FMG["servers"]:
    # An open window polls the server every 5 s (at least once a minute when minimised): in that case no
    # 2nd window, the open one reloads the project by itself (session).
    if _fmg_now - _FMG["last_poll"] > 70:
        fmg_open_window(_fmg_url)
_FMG["tick"] = time.time()
fmg_process_queue()
