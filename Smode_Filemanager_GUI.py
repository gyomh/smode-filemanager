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
# |    SMODE FILEMANAGER GUI              | | Interface graphique du Filemanager,     |
# |       V0.9                            | | servie par Smode (serveur HTTP local)   |
# |                                       | | dans une fenetre d'application.         |
# |_______________________________________| |_________________________________________|
# |    Instructions :                     | | - Medias : liste, etats, filtres        |
# | 1- Glisser le script dans le projet   | | - Relocate : recherche, choix des       |
# | 2- Launch Mode = At Every Update      | |   ambigus, application selective        |
# | 3- La fenetre s'ouvre toute seule     | | - Consolidate : Scene / Type, copie     |
# |    (ou cocher Open Interface)         | |   en arriere-plan avec progression      |
# | 4- Tout se fait dans la fenetre       | | - Ecoute 127.0.0.1 uniquement           |
# |_______________________________________| |_________________________________________|
#
# HISTORIQUE
# V0.1 - 08/10/2026 - Premiere version : serveur HTTP 127.0.0.1 integre (queue + thread principal
#                      pour Oil, travail disque en arriere-plan), interface Edge --app, onglets
#                      Medias / Relocate / Consolidate / Media Directories.
# V0.2 - 08/10/2026 - Consolidate : bouton de mise a jour des Media Directories + relecture auto
#                      toutes les 3 s tant que la destination n'est dans aucun Media Directory
#                      (analyse relancee des qu'un nouveau dossier apparait).
# V0.3 - 08/10/2026 - Consolidate : la liste affiche le Media Directory qui contient la destination
#                      ("Nom > sous-dossier" si sous-dossier, "Hors Media Directory" en orange sinon).
# V0.4 - 08/10/2026 - Medias : recherche avec portee (Nom + Scene par defaut, Nom, Scene, Chemins,
#                      Partout), compteur de resultats, tuiles recalculees sur la recherche, surlignage.
# V0.5 - 08/10/2026 - Medias : bouton croix a gauche du champ pour effacer la recherche (ou Echap).
# V0.6 - 08/10/2026 - Bouton d'effacement : croix dessinee en SVG centree, survol bleu comme les autres boutons.
# V0.7 - 08/10/2026 - Listes deroulantes : contour bleu au survol / focus ; cases et boutons radio bleus.
# V0.8 - 08/10/2026 - Listes deroulantes dessinees par l'interface (surbrillance bleue de l'app au lieu de
#                      celle de Windows), clavier fleches / Entree / Echap, "Hors Media Directory" en orange.
# V0.9 - 08/10/2026 - Relecture du code, corrections :
#                      - dossiers de recherche imbriques : un meme fichier n'est plus compte deux fois
#                        (faux "Ambigu" avec deux chemins identiques) ;
#                      - Media Directory a la racine d'un lecteur (ex. G:\) reconnu ;
#                      - port deja pris : plus de tentative de demarrage a chaque frame ;
#                      - copie annulee / en erreur : le fichier partiel .fmgpart est supprime ; espace disque
#                        verifie avant la copie (et affiche dans le plan) ;
#                      - API en POST uniquement (une page web ne peut plus declencher Explorateur / dialogue /
#                        scan par un simple lien), 404 pour les chemins inconnus ;
#                      - voyant orange quand le Script ne tourne plus, erreur immediate au lieu d'attendre 2 min ;
#                      - Relocate : dossiers introuvables signales ; candidats en chemin absolu ecartes si les
#                        chemins absolus sont desactives ;
#                      - fichiers "En attente Smode" jamais reconnus : passes en Echec apres 40 s ; un seul
#                        rescan du projet a la fin au lieu d'un par fichier ;
#                      - erreurs reseau gerees (suivi de copie, Parcourir) ; rappel d'enregistrer le projet ;
#                      - survol bleu partout (croix des dossiers, Annuler, tuiles, onglets) ;
#                      - Scene nommee CON, NUL, AUX, COM1... : dossier prefixe par _ (nom reserve Windows).
#

# =============== OPTIONS (visibles/modifiables dans le panneau du Script) ===============
SERVEUR: Oil.String("----------------------------------------")
port: Oil.PositiveInteger(8893)          # port local de l'interface (127.0.0.1 uniquement)
openInterface: Oil.Boolean(False)        # cocher = ouvre la fenetre (se decoche tout seul)
autoOpen: Oil.Boolean(True)              # ouvre la fenetre au demarrage du serveur
restartServer: Oil.Boolean(False)        # cocher = redemarre le serveur (se decoche tout seul)
ETAT: Oil.String("----------------------------------------")
status: Oil.String("")                   # adresse de l'interface / erreurs

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

FMG_VERSION = "0.9"
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

# Etat persistant entre les frames (le Script tourne a chaque update ; les globals sont partages entre
# Scripts, d'ou le prefixe _FMG / fmg_ partout).
if "_FMG" not in globals():
    _FMG = {"queue": queue.Queue(), "servers": [], "version": None, "port": None,
            "refs": {}, "job": None, "lock": threading.Lock()}
_FMG.setdefault("tick", time.time())     # cles ajoutees en V0.9 (un _FMG d'une version precedente peut etre en memoire)
_FMG.setdefault("busy", False)


# ===================================== CHEMINS / DISQUE (sans Oil) =====================================
def fmg_clean_path(p):
    return str(p).strip().strip('"\'').strip()


def fmg_media_dirs():
    """[(nom, dossier, lecture seule)] depuis %APPDATA%\\Smode Compose\\configurations\\Data_*.configuration."""
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
    """Dossier normalise pour comparer des chemins, sans separateur final (gere la racine d'un lecteur, ex. G:\\)."""
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
    """nom de fichier (minuscule) -> [chemins]. Un dossier contenu dans un autre de la liste n'est parcouru qu'une
    fois, et un meme fichier n'est jamais compte deux fois (sinon faux cas "ambigu" avec deux chemins identiques)."""
    roots = []                                    # (cle normalisee, dossier tel que saisi : on garde sa casse)
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
    if re.match(r"^(con|prn|aux|nul|com\d|lpt\d)(\..*)?$", name, re.I):   # noms reserves par Windows
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
    for unit in ("o", "Ko", "Mo", "Go"):
        if n < 1024:
            return "%.0f %s" % (n, unit) if unit == "o" else "%.1f %s" % (n, unit)
        n /= 1024.0
    return "%.1f To" % n


def fmg_free_space(path):
    """Espace libre sur le disque de path (le dossier peut ne pas encore exister : on remonte au parent existant)."""
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


# ===================================== TACHES OIL (thread principal) =====================================
def fmg_is_missing(ref):
    fo = ref.file.get()
    return fo is None or fo.getOilClassName() == "MissingFile"


def fmg_walk_refs(project):
    """[(labels, scene, ref)] pour toutes les FileReference du projet."""
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
    """Toutes les references, regroupees par chemin Smode. Garde les refs Oil pour les ecritures."""
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
    """changes = [(ancien chemin Smode, nouveau)] -> {ancien: 'ok' | 'pending' | 'failed'}."""
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
    """Etat actuel de chemins Smode ; recharge ceux encore manquants."""
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
    """Vrai si le Script tourne encore (frame recente, ou tache Oil en cours sur le thread principal)."""
    return _FMG["busy"] or time.time() - _FMG["tick"] < 5


def fmg_main(task, arg=None, timeout=120):
    """Execute une tache Oil sur le thread principal (Script en At Every Update) et attend le resultat."""
    if not fmg_alive():
        raise RuntimeError("Smode ne traite plus les demandes : le Script Smode Filemanager GUI est-il toujours dans "
                           "le projet ouvert, actif, en Launch Mode 'At Every Update' ?")
    box = {"task": task, "arg": arg, "result": None, "error": None, "done": threading.Event()}
    _FMG["queue"].put(box)
    if not box["done"].wait(timeout):
        raise RuntimeError("Smode ne repond pas (Script bien en Launch Mode 'At Every Update' ?)")
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


# ===================================== LOGIQUE (thread HTTP, sans Oil) =====================================
def fmg_items_view(scan, media_dirs):
    """Liste des medias pour l'onglet Medias."""
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
    bad = [f for f in folders if not os.path.isdir(f)]            # saisis par l'utilisateur mais introuvables
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
            # chemins absolus desactives : on ecarte les candidats hors Media Directory
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
        error = "Indiquer le dossier de destination."
    elif fmg_to_smode(os.path.join(dest, "x"), media_dirs) is None:
        error = ("Ce dossier n'est dans aucun Media Directory. L'ajouter dans Smode (panneau Media Directories), "
                 "attendre quelques secondes (Smode enregistre la liste en differe) puis relancer l'analyse.")
    elif fmg_in_readonly(os.path.join(dest, "x"), media_dirs):
        error = "Ce dossier est dans un Media Directory en lecture seule."
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
    """Copie par blocs dans un .fmgpart renomme a la fin ; le fichier partiel est supprime en cas d'erreur ou
    d'annulation (sinon des Go de fichier tronque resteraient sur le disque)."""
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    tmp = dst + ".fmgpart"
    done0 = job["done_bytes"]
    try:
        with open(src, "rb") as fi, open(tmp, "wb") as fo:
            while True:
                if job.get("cancel"):
                    raise RuntimeError("annule")
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


def fmg_consolidate_job(dest, selected):
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
            raise RuntimeError("Espace insuffisant sur le disque de destination : %s a copier, %s libres."
                               % (fmg_fmt_size(job["total_bytes"]), fmg_fmt_size(free)))
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


# ===================================== OUTILS SYSTEME =====================================
def fmg_browse_folder(initial=""):
    """Boite de dialogue Windows de choix de dossier (PowerShell, hors du process Smode)."""
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
        raise RuntimeError("introuvable : " + path)


def fmg_open_window(url):
    for edge in (r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
                 r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"):
        if os.path.isfile(edge):
            subprocess.Popen([edge, "--app=" + url, "--window-size=1400,900"])
            return
    os.startfile(url)


# ===================================== SERVEUR HTTP =====================================
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
        # L'API n'accepte que POST : une page web etrangere peut declencher un GET (<img src=...>) sans en-tete
        # Origin, mais un POST de sa part porte toujours son Origin (refuse ci-dessus).
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
        return {"version": FMG_VERSION, "alive": fmg_alive(),
                "mediaDirs": [{"name": n, "dir": d, "readOnly": ro} for n, d, ro in fmg_media_dirs()]}
    if path == "/api/scan":
        scan = fmg_main("scan")
        return {"project": scan["project"], "items": fmg_items_view(scan, fmg_media_dirs())}
    if path == "/api/relocate/analyze":
        return fmg_relocate_analyze(data.get("folders") or [], bool(data.get("allowAbsolute", True)))
    if path == "/api/relocate/apply":
        changes = [(c["old"], c["new"]) for c in data.get("changes", [])]
        fmg_main("scan")                       # references fraiches
        return {"results": fmg_main("set_paths", changes)}
    if path == "/api/consolidate/plan":
        return fmg_consolidate_plan(data.get("dest", ""))
    if path == "/api/consolidate/start":
        with _FMG["lock"]:
            if _FMG["job"] and _FMG["job"]["running"]:
                raise RuntimeError("un consolidate est deja en cours")
            _FMG["job"] = {"running": True, "total": 0, "index": 0, "total_bytes": 0, "done_bytes": 0,
                           "current": "", "results": [], "error": "", "cancel": False}
        sel = data.get("selected")
        threading.Thread(target=fmg_consolidate_job, args=(data.get("dest", ""), set(sel) if sel is not None else None),
                         daemon=True).start()
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
    raise RuntimeError("endpoint inconnu : " + path)


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
</style></head><body>
<header>
  <div class="logo">SMODE FILEMANAGER<small>v__VERSION__</small></div>
  <div class="proj"><span class="dot" id="dot"></span>Projet <b id="proj">...</b></div>
  <div class="sp"></div>
  <button class="btn" id="rescan">Rescanner le projet</button>
</header>
<nav>
  <button data-t="medias" class="on">Medias</button>
  <button data-t="relocate">Relocate</button>
  <button data-t="consolidate">Consolidate</button>
  <button data-t="dirs">Media Directories</button>
</nav>
<main>
<section class="tab on" id="t-medias">
  <div class="tiles" id="m-tiles"></div>
  <div class="toolbar"><button class="btn clr" id="m-clear" title="Effacer la recherche (Echap)"><svg width="12" height="12" viewBox="0 0 12 12" aria-hidden="true"><path d="M2 2L10 10M10 2L2 10" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg></button><input type="text" id="m-q" placeholder="Rechercher...">
    <select id="m-scope" title="Ou chercher">
      <option value="ns">Nom du fichier + Scene</option><option value="name">Nom du fichier</option>
      <option value="scene">Scene</option><option value="path">Chemins (Smode + disque)</option>
      <option value="all">Partout (y compris Compos / calques)</option></select>
    <span class="expl" id="m-count"></span></div>
  <div class="list" id="m-list"><div class="empty"><span class="spin"></span> Scan du projet...</div></div>
</section>

<section class="tab" id="t-relocate">
  <div class="box">
    <h2>Dossiers ou chercher</h2>
    <p class="help">Les fichiers manquants sont cherches par leur nom dans ces dossiers (sous-dossiers compris).
      Sans dossier : tous les Media Directories modifiables. Un dossier parent large (ex. le dossier du projet) trouve plus.</p>
    <div class="chips" id="r-folders" style="margin-bottom:10px"></div>
    <div class="row"><input type="text" id="r-add" placeholder="Coller un chemin (les guillemets sont acceptes)">
      <button class="btn" id="r-addbtn">Ajouter</button><button class="btn" id="r-browse">Parcourir...</button></div>
    <div class="row" style="margin-top:12px">
      <label class="chk"><input type="checkbox" id="r-abs" checked> Autoriser les chemins absolus (fichier hors Media Directory, non portable)</label>
      <div class="sp"></div><button class="btn pri" id="r-run">Analyser</button></div>
  </div>
  <div id="r-out"></div>
</section>

<section class="tab" id="t-consolidate">
  <div class="box">
    <h2>Destination</h2>
    <p class="help">Les medias sont copies dans Destination / Scene / Type (VIDEO, IMAGE, AUDIO, 3D). Un fichier
      utilise dans plusieurs Scenes va dans _COMMUN. Les originaux restent en place. La destination doit etre dans un Media Directory.</p>
    <div class="row"><input type="text" id="c-dest" placeholder="Dossier de destination">
      <select id="c-md"><option value="">Media Directories...</option></select>
      <button class="btn" id="c-mdref" title="Relire la liste des Media Directories (apres en avoir ajoute un dans Smode)">&#8635; Media Directories</button>
      <button class="btn" id="c-browse">Parcourir...</button><button class="btn pri" id="c-run">Analyser</button></div>
  </div>
  <div id="c-out"></div>
</section>

<section class="tab" id="t-dirs">
  <div class="box"><h2>Media Directories</h2>
    <p class="help">Lus dans la configuration de Smode. Pour en ajouter : panneau Media Directories de Smode, puis Rafraichir
      (Smode enregistre la liste quelques secondes apres l'ajout).</p>
    <div id="d-list"></div><div style="margin-top:10px"><button class="btn" id="d-refresh">Rafraichir</button></div></div>
</section>
</main>
<div id="toast"></div>
<script>
var S={items:[],mfilter:'*',rFolders:[],reloc:null,rFilter:'*',plan:null,cFilter:'*',dirs:[],job:null};
var COL={ok:'--ok',missing:'--red',absolute:'--amber',pack:'--grey',found:'--blue',found_abs:'--amber',outside:'--orange',
 ambiguous:'--violet',notfound:'--red',pending:'--cyan',applied:'--ok',applied_abs:'--amber',failed:'--dred',
 planned:'--blue',copied:'--ok',reused:'--teal',inplace:'--grey'};
var LAB={ok:'OK',missing:'Manquant',absolute:'Chemin absolu',pack:'Pack Smode',found:'Retrouve',found_abs:'Retrouve (absolu)',
 outside:'Hors Media Directory',ambiguous:'Ambigu',notfound:'Introuvable',pending:'En attente Smode',applied:'Applique',
 applied_abs:'Applique (absolu)',failed:'Echec',planned:'A copier',copied:'Copie',reused:'Deja copie',inplace:'Deja consolide'};
var EXPL={ok:'Fichier trouve dans un Media Directory',missing:'Introuvable pour Smode : utiliser Relocate',
 absolute:'Trouve hors de tout Media Directory (non portable)',pack:'Media d\'un pack Smode en lecture seule',
 found:'Pret a appliquer',found_abs:'Hors Media Directory : sera rebranche en chemin absolu',
 outside:'Trouve mais les chemins absolus sont desactives',ambiguous:'Plusieurs candidats a egalite : choisir le bon',
 notfound:'Aucun fichier de ce nom : ajouter un dossier ou chercher (un dossier parent large marche bien)',
 pending:'Fichier present sur le disque, Smode ne l\'a pas encore indexe : verification automatique',
 applied:'Rebranche et verifie',applied_abs:'Rebranche en chemin absolu',failed:'Erreur',planned:'Sera copie puis rebranche',
 copied:'Copie, rebranche et verifie',reused:'Copie identique deja presente : rebranche sans recopier',
 inplace:'Deja dans la destination'};
function $(id){return document.getElementById(id)}
function esc(t){return String(t==null?'':t).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;')}
function col(s){return 'var('+(COL[s]||'--grey')+')'}
function base(p){p=String(p||'').replace(/\\/g,'/');return p.split('/').pop()}
function fmt(n){if(!n)return '';var u=['o','Ko','Mo','Go','To'],i=0;while(n>=1024&&i<4){n/=1024;i++}return n.toFixed(i?1:0)+' '+u[i]}
function toast(m,bad){var t=$('toast');t.textContent=m;t.className='on'+(bad?' bad':'');clearTimeout(t._h);t._h=setTimeout(function(){t.className=''},3500)}
function api(path,data){return fetch(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data||{})})
 .then(function(r){return r.json().then(function(j){if(!r.ok)throw new Error(j.error||r.status);return j})},
 function(e){setDot(null);throw new Error('Smode ne repond pas (serveur arrete ?)')})}
/* voyant : vert = Smode traite les demandes, orange = serveur joignable mais Script inactif, rouge = serveur injoignable */
function setDot(alive){var d=$('dot');d.className='dot '+(alive===null?'off':alive?'on':'warn');
 d.title=alive===null?'Serveur injoignable':alive?'Connecte a Smode':'Le Script ne tourne plus dans Smode (projet ferme, Script supprime ou inactif ?)'}
function copy(t){if(navigator.clipboard)navigator.clipboard.writeText(t);toast('Copie : '+t)}
function tools(abs){if(!abs)return '';var a=esc(abs);return ' <button class="btn sm" data-reveal="'+a+'">Explorateur</button>'+
 ' <button class="btn sm" data-copy="'+a+'">Copier</button>'}
function uses(u){if(!u||!u.length)return '';return '<details><summary>'+u.length+' utilisation'+(u.length>1?'s':'')+' &middot; '+esc(u[0]||'(racine)')+
 '</summary><ul>'+u.map(function(x){return '<li>'+esc(x||'(racine)')+'</li>'}).join('')+'</ul></details>'}
function tiles(el,list,order,cur,cb){var c={};list.forEach(function(e){c[e.state]=(c[e.state]||0)+1});
 var h='<button class="tile'+(cur==='*'?'':' off')+'" data-f="*" style="--c:var(--fg)"><b>'+list.length+'</b><span>Tout</span></button>';
 order.forEach(function(k){if(c[k])h+='<button class="tile'+(cur==='*'||cur===k?'':' off')+'" data-f="'+k+'" style="--c:'+col(k)+'"><b>'+c[k]+'</b><span>'+LAB[k]+'</span></button>'});
 el.innerHTML=h;el.querySelectorAll('.tile').forEach(function(b){b.onclick=function(){cb(b.dataset.f)}})}
document.addEventListener('click',function(ev){var b=ev.target.closest('[data-reveal],[data-copy]');if(!b)return;
 if(b.dataset.copy!=null)copy(b.dataset.copy);else api('/api/reveal',{path:b.dataset.reveal}).catch(function(e){toast(e.message,1)})});
document.querySelectorAll('nav button').forEach(function(b){b.onclick=function(){
 document.querySelectorAll('nav button').forEach(function(x){x.classList.toggle('on',x===b)});
 document.querySelectorAll('.tab').forEach(function(t){t.classList.toggle('on',t.id==='t-'+b.dataset.t)})}});

/* ---------------- MEDIAS ---------------- */
function scan(){$('m-list').innerHTML='<div class="empty"><span class="spin"></span> Scan du projet...</div>';
 return api('/api/scan').then(function(r){S.items=r.items;$('proj').textContent=r.project;renderMedias()})
 .catch(function(e){$('m-list').innerHTML='<div class="err">'+esc(e.message)+'</div>'})}
/* surligne q dans t (texte brut -> HTML echappe) */
function hl(t,q){t=String(t==null?'':t);if(!q)return esc(t);var lo=t.toLowerCase(),out='',i=0,j;
 while((j=lo.indexOf(q,i))>=0){out+=esc(t.slice(i,j))+'<mark>'+esc(t.slice(j,j+q.length))+'</mark>';i=j+q.length}return out+esc(t.slice(i))}
/* champs fouilles selon la portee choisie */
function mFields(e,sc){var name=base(e.path),scenes=e.scenes.join(' ');
 if(sc==='name')return name;if(sc==='scene')return scenes;if(sc==='path')return e.path+' '+(e.abs||'');
 if(sc==='all')return name+' '+scenes+' '+e.path+' '+(e.abs||'')+' '+e.users.join(' ');return name+' '+scenes}
function renderMedias(){var q=$('m-q').value.trim().toLowerCase(),sc=$('m-scope').value;
 var hit=S.items.filter(function(e){return !q||mFields(e,sc).toLowerCase().indexOf(q)>=0});
 tiles($('m-tiles'),hit,['missing','absolute','ok','pack'],S.mfilter,function(f){S.mfilter=f;renderMedias()});
 var l=hit.filter(function(e){return S.mfilter==='*'||e.state===S.mfilter});
 $('m-count').textContent=q?(hit.length+' / '+S.items.length+' media(s)'):'';
 var qn=(sc==='ns'||sc==='name'||sc==='all')?q:'',qs=(sc==='ns'||sc==='scene'||sc==='all')?q:'',qp=(sc==='path'||sc==='all')?q:'';
 $('m-list').innerHTML=l.length?l.map(function(e){return '<div class="it" style="--c:'+col(e.state)+'"><div class="hd"><span class="badge">'+LAB[e.state]+
  '</span><span class="type">'+e.type+'</span><span class="name">'+hl(base(e.path),qn)+'</span><span class="expl">'+hl(e.scenes.join(', '),qs)+
  '</span><span class="size">'+fmt(e.size)+'</span></div><div class="p"><span class="k">Smode</span><code>'+hl(e.path,qp)+'</code></div>'+
  (e.abs?'<div class="p"><span class="k">disque</span><code>'+hl(e.abs,qp)+'</code>'+tools(e.abs)+'</div>':'')+uses(e.users)+'</div>'}).join('')
  :'<div class="empty">'+(q?'Aucun media ne correspond a &laquo; '+esc(q)+' &raquo;.':'Aucun media.')+'</div>'}
$('m-q').oninput=renderMedias;$('m-scope').onchange=renderMedias;
$('m-clear').onclick=function(){$('m-q').value='';renderMedias();$('m-q').focus()};
$('m-q').onkeydown=function(e){if(e.key==='Escape')$('m-clear').onclick()};$('rescan').onclick=function(){scan();loadInfo()};

/* ---------------- RELOCATE ---------------- */
function renderFolders(){$('r-folders').innerHTML=S.rFolders.length?S.rFolders.map(function(f,i){return '<span class="chip">'+esc(f)+
 '<button data-i="'+i+'" title="Retirer">&times;</button></span>'}).join(''):'<span class="expl">Aucun dossier : tous les Media Directories modifiables seront fouilles.</span>';
 $('r-folders').querySelectorAll('button').forEach(function(b){b.onclick=function(){S.rFolders.splice(+b.dataset.i,1);renderFolders()}})}
function addFolder(p){p=String(p||'').trim().replace(/^["']|["']$/g,'');if(p&&S.rFolders.indexOf(p)<0)S.rFolders.push(p);renderFolders()}
$('r-addbtn').onclick=function(){addFolder($('r-add').value);$('r-add').value=''};
$('r-add').onkeydown=function(e){if(e.key==='Enter')$('r-addbtn').onclick()};
$('r-browse').onclick=function(){api('/api/browse',{initial:S.rFolders[0]||''}).then(function(r){if(r.path)addFolder(r.path)})
 .catch(function(e){toast(e.message,1)})};
$('r-run').onclick=function(){$('r-out').innerHTML='<div class="empty"><span class="spin"></span> Recherche des fichiers manquants...</div>';
 api('/api/relocate/analyze',{folders:S.rFolders,allowAbsolute:$('r-abs').checked}).then(function(r){
  r.entries.forEach(function(e){e.sel=(e.state==='found'||e.state==='found_abs');e.pick=-1});S.reloc=r;S.rFilter='*';renderReloc();
  var pend=r.entries.filter(function(e){return e.state==='pending'}).map(function(e){return e.old});if(pend.length)watchPending(pend,'reloc')})
 .catch(function(e){$('r-out').innerHTML='<div class="err">'+esc(e.message)+'</div>'})};
function renderReloc(){var r=S.reloc;if(!r)return;var order=['failed','notfound','ambiguous','outside','found_abs','found','pending','applied_abs','applied'];
 var n=r.entries.filter(function(e){return e.sel&&(e.new||e.pick>=0)}).length;
 var h='<div class="tiles" id="r-tiles"></div><div class="toolbar"><span class="expl">'+r.entries.length+' fichier(s) manquant(s) &middot; dossiers fouilles : '+
  r.folders.map(esc).join(' ; ')+'</span><div class="sp"></div><button class="btn pri" id="r-apply"'+(n?'':' disabled')+'>Appliquer la selection ('+n+')</button></div>';
 if(r.badFolders&&r.badFolders.length)h='<div class="err">Dossier(s) introuvable(s), ignore(s) : '+r.badFolders.map(esc).join(' ; ')+
  '. Verifier le chemin (faute de frappe, disque deconnecte ?).</div>'+h;
 if(!r.entries.length)h+='<div class="empty">Aucun fichier manquant dans le projet.</div>';
 h+='<div class="list">';
 r.entries.forEach(function(e,i){if(S.rFilter!=='*'&&e.state!==S.rFilter)return;
  var canSel=(e.state==='found'||e.state==='found_abs'||(e.state==='ambiguous'&&e.pick>=0));
  h+='<div class="it" style="--c:'+col(e.state)+'"><div class="hd">'+
   ((e.state==='found'||e.state==='found_abs'||e.state==='ambiguous')?'<input type="checkbox" data-sel="'+i+'"'+(e.sel&&canSel?' checked':'')+(canSel?'':' disabled')+'>':'')+
   '<span class="badge">'+LAB[e.state]+'</span><span class="type">'+e.type+'</span><span class="name">'+esc(base(e.old))+'</span><span class="expl">'+EXPL[e.state]+'</span></div>'+
   '<div class="p old"><span class="k">avant</span><code>'+esc(e.old)+'</code></div>'+
   (e.new&&e.state!=='pending'?'<div class="p new"><span class="k">apres</span><code>'+esc(e.new)+'</code>'+tools(e.abs)+'</div>':'')+
   (e.state==='pending'?'<div class="p"><span class="k">disque</span><code>'+esc(e.abs)+'</code>'+tools(e.abs)+'</div>':'');
  if(e.cands)e.cands.forEach(function(c,j){h+='<label class="cand"><input type="radio" name="pk'+i+'" data-pick="'+i+'" value="'+j+'"'+(e.pick===j?' checked':'')+
   '><code>'+esc(c.abs)+'</code>'+(c.absolute?'<span class="type">absolu</span>':'')+tools(c.abs)+'</label>'});
  if(e.state==='notfound')h+='<div class="hint">Ajouter en haut le dossier ou ce fichier se trouve probablement (ou un dossier parent), puis Analyser.</div>';
  if(e.err)h+='<div class="hint">'+esc(e.err)+'</div>';
  h+=uses(e.users)+'</div>'});
 $('r-out').innerHTML=h+'</div>';
 tiles($('r-tiles'),r.entries,order,S.rFilter,function(f){S.rFilter=f;renderReloc()});
 $('r-out').querySelectorAll('[data-sel]').forEach(function(c){c.onchange=function(){r.entries[+c.dataset.sel].sel=c.checked;renderReloc()}});
 $('r-out').querySelectorAll('[data-pick]').forEach(function(c){c.onchange=function(){var e=r.entries[+c.dataset.pick];e.pick=+c.value;e.sel=true;renderReloc()}});
 var ab=$('r-apply');if(ab)ab.onclick=applyReloc}
function applyReloc(){var r=S.reloc,ch=[],map={};
 r.entries.forEach(function(e){if(!e.sel)return;var nw=e.state==='ambiguous'?(e.pick>=0?e.cands[e.pick].new:null):e.new;
  if(nw&&(e.state==='found'||e.state==='found_abs'||e.state==='ambiguous')){ch.push({old:e.old,new:nw});map[e.old]=e}});
 if(!ch.length)return;$('r-apply').disabled=true;$('r-apply').innerHTML='<span class="spin"></span> Application...';
 api('/api/relocate/apply',{changes:ch}).then(function(res){var pend=[];
  Object.keys(res.results).forEach(function(old){var e=map[old],s=res.results[old];var abs=e.state==='found_abs'||(e.state==='ambiguous'&&e.cands[e.pick].absolute);
   if(e.state==='ambiguous'){e.abs=e.cands[e.pick].abs;e.new=e.cands[e.pick].new;e.cands=null}
   e.isAbs=abs;e.sel=false;e.state=s==='ok'?(abs?'applied_abs':'applied'):s==='pending'?'pending':'failed';
   if(s==='failed')e.err='Reference introuvable dans le projet (deja modifiee ?) : relancer Analyser.';if(s==='pending')pend.push(e.new)});
  renderReloc();toast(ch.length+' fichier(s) rebranche(s) - penser a enregistrer le projet Smode (Ctrl+S)');scan();
  if(pend.length)watchPending(pend,'reloc')})
 .catch(function(e){toast(e.message,1);renderReloc()})}

/* ---------------- CONSOLIDATE ---------------- */
function normP(p){return String(p||'').trim().replace(/^["']|["']$/g,'').replace(/\//g,'\\').replace(/\\+$/,'').toLowerCase()}
/* la liste affiche le Media Directory qui contient la destination (ou "hors Media Directory") */
function syncMd(){syncMd0();ddRefresh($('c-md'))}
function syncMd0(){var d=normP($('c-dest').value),sel=$('c-md'),best=null;
 S.dirs.forEach(function(m){if(m.readOnly)return;var r=normP(m.dir);if((d===r||d.indexOf(r+'\\')===0)&&(!best||r.length>normP(best.dir).length))best=m});
 var x=sel.querySelector('option[data-sub]');if(x)x.remove();
 sel.options[0].textContent='Media Directories...';sel.dataset.warn='';
 if(!d){sel.value='';return}
 if(best&&normP(best.dir)===d){sel.value=best.dir}
 else if(best){var o=document.createElement('option');o.dataset.sub='1';o.value='__sub';
  o.textContent=best.name+' › '+$('c-dest').value.trim().replace(/^["']|["']$/g,'').slice(best.dir.length).replace(/^[\\\/]+/,'');
  sel.appendChild(o);sel.value='__sub'}
 else{sel.value='';sel.options[0].textContent='Hors Media Directory';sel.dataset.warn='1'}}
$('c-md').onchange=function(){if(this.value&&this.value!=='__sub')$('c-dest').value=this.value;syncMd()};
$('c-dest').oninput=syncMd;
function mdRefresh(silent){var before=S.dirs.length;return loadInfo().then(function(){
 if(!silent)toast(S.dirs.length+' Media Directories'+(S.dirs.length>before?' ('+(S.dirs.length-before)+' nouveau'+(S.dirs.length-before>1?'x':'')+')':''));
 if(S.plan&&S.plan.error&&$('c-dest').value)$('c-run').onclick()})}
$('c-mdref').onclick=function(){mdRefresh(false)};
/* destination hors Media Directory : on relit la liste toutes les 3 s (Smode l'enregistre en differe) */
setInterval(function(){if(S.plan&&S.plan.error&&$('c-dest').value&&!(S.job&&S.job.running)){var n=S.dirs.length;
 loadInfo().then(function(){if(S.dirs.length!==n){toast('Nouveau Media Directory detecte');$('c-run').onclick()}})}},3000);
$('c-browse').onclick=function(){api('/api/browse',{initial:$('c-dest').value}).then(function(r){if(r.path){$('c-dest').value=r.path;syncMd()}})
 .catch(function(e){toast(e.message,1)})};
$('c-run').onclick=function(){$('c-out').innerHTML='<div class="empty"><span class="spin"></span> Analyse...</div>';
 api('/api/consolidate/plan',{dest:$('c-dest').value}).then(function(r){r.entries.forEach(function(e){e.sel=e.state==='planned'});S.plan=r;S.cFilter='*';renderPlan()})
 .catch(function(e){$('c-out').innerHTML='<div class="err">'+esc(e.message)+'</div>'})};
function renderPlan(){var r=S.plan;if(!r)return;var order=['failed','missing','pending','planned','copied','reused','inplace','pack'];
 var sel=r.entries.filter(function(e){return e.sel&&e.state==='planned'});
 var bytes=sel.reduce(function(a,e){return a+(e.exists?0:(e.size||0))},0);
 var full=r.free!=null&&bytes>r.free;
 var h=r.error?'<div class="err">'+esc(r.error)+'</div>':'';
 if(full&&!r.error)h+='<div class="err">Espace insuffisant sur le disque de destination : '+fmt(bytes)+' a copier, '+(fmt(r.free)||'0 o')+' libres.</div>';
 h+='<div class="tiles" id="c-tiles"></div><div class="toolbar"><span class="expl">Destination <code>'+esc(r.dest||'-')+'</code> &middot; '+sel.length+
  ' fichier(s), '+(fmt(bytes)||'0 o')+' a copier'+(r.free!=null?' &middot; '+(fmt(r.free)||'0 o')+' libres':'')+'</span><div class="sp"></div>'+
  '<button class="btn pri" id="c-go"'+(sel.length&&!r.error&&!full?'':' disabled')+'>Consolider la selection</button></div>';
 h+='<div id="c-prog"></div>';
 var groups={},rest=[];r.entries.forEach(function(e,i){e._i=i;if(S.cFilter!=='*'&&e.state!==S.cFilter)return;if(e.group)(groups[e.group]=groups[e.group]||[]).push(e);else rest.push(e)});
 Object.keys(groups).sort().forEach(function(g){h+='<div class="grp">'+esc(g)+'</div><div class="list">'+groups[g].map(planItem).join('')+'</div>'});
 if(rest.length)h+='<div class="grp">Non concernes</div><div class="list">'+rest.map(planItem).join('')+'</div>';
 $('c-out').innerHTML=h;tiles($('c-tiles'),r.entries,order,S.cFilter,function(f){S.cFilter=f;renderPlan()});
 $('c-out').querySelectorAll('[data-csel]').forEach(function(c){c.onchange=function(){r.entries[+c.dataset.csel].sel=c.checked;renderPlan()}});
 var go=$('c-go');if(go)go.onclick=startJob;if(S.job&&S.job.running)renderJob()}
function planItem(e){return '<div class="it" style="--c:'+col(e.state)+'"><div class="hd">'+(e.state==='planned'?'<input type="checkbox" data-csel="'+e._i+'"'+(e.sel?' checked':'')+'>':'')+
 '<span class="badge">'+LAB[e.state]+'</span><span class="type">'+e.type+'</span><span class="name">'+esc(base(e.old))+'</span><span class="expl">'+
 (e.state==='planned'&&e.exists?'Copie identique deja presente':EXPL[e.state])+(e.err?' : '+esc(e.err):'')+'</span><span class="size">'+fmt(e.size)+'</span></div>'+
 '<div class="p old"><span class="k">avant</span><code>'+esc(e.old)+'</code>'+tools(e.src)+'</div>'+
 (e.new?'<div class="p new"><span class="k">apres</span><code>'+esc(e.new)+'</code>'+((e.state==='copied'||e.state==='reused'||e.state==='pending')?tools(e.target):'')+'</div>':'')+
 (e.state==='missing'?'<div class="hint">Lancer d\'abord un Relocate pour retrouver ce fichier.</div>':'')+uses(e.users)+'</div>'}
function startJob(){var r=S.plan;var sel=r.entries.filter(function(e){return e.sel&&e.state==='planned'}).map(function(e){return e.old});
 api('/api/consolidate/start',{dest:r.dest,selected:sel}).then(function(){S.job={running:true};renderPlan();pollJob()}).catch(function(e){toast(e.message,1)})}
function renderJob(){var j=S.job,el=$('c-prog');if(!el||!j)return;var pc=j.total_bytes?Math.round(100*j.done_bytes/j.total_bytes):(j.total?Math.round(100*(j.index||0)/j.total):0);
 el.innerHTML='<div class="box"><div class="row"><b>'+(j.running?'Copie en cours':'Termine')+'</b><span class="expl">'+(j.index||0)+' / '+(j.total||0)+' &middot; '+
  fmt(j.done_bytes)+' / '+fmt(j.total_bytes)+'</span><span class="mono expl">'+esc(j.current||'')+'</span><div class="sp"></div>'+
  (j.running?'<button class="btn sm" id="c-cancel">Annuler</button>':'')+'</div><div class="prog" style="margin-top:10px"><i style="width:'+pc+'%"></i></div>'+
  (j.error?'<div class="err" style="margin:10px 0 0">'+esc(j.error)+'</div>':'')+'</div>';
 var c=$('c-cancel');if(c)c.onclick=function(){api('/api/consolidate/cancel')}}
function pollJob(){fetch('/api/job',{method:'POST'}).then(function(r){return r.json()}).then(function(j){S.job=j;
 var byOld={};(j.results||[]).forEach(function(x){byOld[x.old]=x});
 S.plan.entries.forEach(function(e){var x=byOld[e.old];if(x){e.state=x.state;e.err=x.error;e.sel=false}});
 if(j.running){renderJob();var el=$('c-prog');if(!el)renderPlan();setTimeout(pollJob,500)}
 else{renderPlan();renderJob();scan();var pend=(j.results||[]).filter(function(x){return x.state==='pending'}).map(function(x){return x.new});
  toast(j.error?'Consolidate interrompu : '+j.error:'Consolidate termine - penser a enregistrer le projet Smode (Ctrl+S)',!!j.error);
  if(pend.length)watchPending(pend,'plan')}},
 function(){toast('Smode ne repond pas, nouvel essai...',1);setTimeout(pollJob,2000)})}

/* ---------------- verification des fichiers en attente ---------------- */
/* revérifie toutes les 2 s (40 s max) ; un seul rescan du projet a la fin (un scan gele Smode quelques
   secondes sur un gros projet) ; au-dela, les fichiers jamais reconnus passent en Echec avec une explication */
function watchPending(paths,where,n){n=n||0;var list=where==='reloc'?(S.reloc&&S.reloc.entries):(S.plan&&S.plan.entries);
 function redraw(){where==='reloc'?renderReloc():renderPlan()}
 if(!paths.length){scan();return}
 if(n>=20){(list||[]).forEach(function(e){if(e.state==='pending'&&paths.indexOf(e.new)>=0){e.state='failed';
   e.err='Smode ne reconnait toujours pas ce fichier : verifier qu\'il est lisible (format, droits), puis relancer Analyser.'}});
  redraw();scan();return}
 setTimeout(function(){api('/api/check',{paths:paths}).then(function(res){
  var left=paths.filter(function(p){return res[p]!=='ok'});
  (list||[]).forEach(function(e){if(e.state==='pending'&&res[e.new]==='ok')e.state=where==='reloc'?(e.isAbs?'applied_abs':'applied'):'copied'});
  if(left.length<paths.length)redraw();
  watchPending(left,where,n+1)},function(){watchPending(paths,where,n+1)})},2000)}

/* ---------------- MEDIA DIRECTORIES ---------------- */
function loadInfo(){return api('/api/info').then(function(r){S.dirs=r.mediaDirs;setDot(!!r.alive);
 $('d-list').innerHTML='<table><tr><th>Nom</th><th>Dossier</th><th></th></tr>'+r.mediaDirs.map(function(d){return '<tr><td><b>'+esc(d.name)+'</b>'+
  (d.readOnly?' <span class="type">lecture seule</span>':'')+'</td><td class="mono">'+esc(d.dir)+'</td><td>'+tools(d.dir)+'</td></tr>'}).join('')+'</table>';
 $('c-md').innerHTML='<option value="">Media Directories...</option>'+r.mediaDirs.filter(function(d){return !d.readOnly}).map(function(d){
  return '<option value="'+esc(d.dir)+'">'+esc(d.name)+'</option>'}).join('');syncMd()})}
$('d-refresh').onclick=loadInfo;
/* ---------------- listes deroulantes maison (la surbrillance d'un <select> natif est imposee par Windows) ---------------- */
function ddRefresh(sel){var w=sel._dd;if(!w)return;var o=sel.options[sel.selectedIndex];w.lab.textContent=o?o.textContent:'';
 w.btn.classList.toggle('warn',sel.dataset.warn==='1')}
function makeDD(sel){var w=document.createElement('div');w.className='dd';sel.parentNode.insertBefore(w,sel);w.appendChild(sel);sel.style.display='none';
 var btn=document.createElement('button');btn.type='button';btn.className='dd-btn';btn.title=sel.title||'';
 btn.innerHTML='<span class="dd-lab"></span><svg width="10" height="6" viewBox="0 0 10 6" aria-hidden="true"><path d="M1 1l4 4 4-4" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>';
 var list=document.createElement('div');list.className='dd-list';w.appendChild(btn);w.appendChild(list);
 list.onmousedown=function(e){e.preventDefault()};   /* garde le focus : la barre de defilement ne ferme plus la liste */
 sel._dd={btn:btn,lab:btn.firstChild};var act=-1,opts=[];
 function close(){w.classList.remove('open')}
 function mark(){opts.forEach(function(o,i){o.el.classList.toggle('act',i===act)});if(opts[act])opts[act].el.scrollIntoView({block:'nearest'})}
 function pick(i){var o=opts[i];if(!o)return;sel.value=o.v;close();ddRefresh(sel);sel.dispatchEvent(new Event('change'));btn.focus()}
 function open(){opts=[];list.innerHTML='';Array.prototype.forEach.call(sel.options,function(op){if(op.value===''||op.value==='__sub')return;
   var el=document.createElement('div');el.className='dd-opt'+(op.value===sel.value?' sel':'');el.textContent=op.textContent;var i=opts.length;
   el.onmousedown=function(e){e.preventDefault();pick(i)};el.onmouseenter=function(){act=i;mark()};list.appendChild(el);opts.push({v:op.value,el:el})});
  if(!opts.length)list.innerHTML='<div class="dd-empty">Aucun element</div>';
  act=Math.max(0,opts.map(function(o){return o.v}).indexOf(sel.value));w.classList.add('open');mark()}
 btn.onclick=function(){w.classList.contains('open')?close():open()};
 btn.onblur=function(){setTimeout(close,120)};
 btn.onkeydown=function(e){var isOpen=w.classList.contains('open');
  if(e.key==='ArrowDown'||e.key==='ArrowUp'){e.preventDefault();if(!isOpen){open();return}
   act=Math.min(opts.length-1,Math.max(0,act+(e.key==='ArrowDown'?1:-1)));mark()}
  else if(e.key==='Enter'||e.key===' '){e.preventDefault();if(isOpen)pick(act);else open()}
  else if(e.key==='Escape'&&isOpen){e.preventDefault();close()}};
 ddRefresh(sel)}
makeDD($('m-scope'));makeDD($('c-md'));
renderFolders();loadInfo();scan();
setInterval(function(){fetch('/api/info',{method:'POST'}).then(function(r){return r.json()}).then(function(j){setDot(!!j.alive)},
 function(){setDot(null)})},5000);
</script></body></html>"""


# ===================================== BOUCLE (chaque frame) =====================================
_fmg_port = int(script.port.get())
for _t in ("SERVEUR", "ETAT"):
    if str(getattr(script, _t)) != "-" * 40:
        setattr(script, _t, "-" * 40)
# (Re)demarrage seulement au premier passage, si la version ou le port change, ou sur Restart Server.
# Un echec (port deja pris) n'est PAS retente a chaque frame : changer le port ou cocher Restart Server.
_fmg_restart = bool(script.restartServer.get())
if _FMG["version"] != FMG_VERSION or _FMG["port"] != _fmg_port or _fmg_restart:
    if _fmg_restart:
        script.restartServer.set(False)
    _first = _FMG["version"] is None
    _url = fmg_start_server(_fmg_port)
    script.status = _url
    if _url.startswith("http") and (script.openInterface.get() or (_first and script.autoOpen.get())):
        fmg_open_window(_url)
        script.openInterface.set(False)
if script.openInterface.get():
    script.openInterface.set(False)
    if _FMG["servers"]:
        fmg_open_window("http://127.0.0.1:%d" % _fmg_port)
_FMG["tick"] = time.time()
fmg_process_queue()
