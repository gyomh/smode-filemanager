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
# |    SMODE FILEMANAGER                  | | RELOCATE : retrouve les fichiers        |
# |       V0.6                            | | manquants meme deplaces et repartis     |
# |    Relocate + Consolidate             | | autrement (recherche par nom).          |
# |_______________________________________| |_________________________________________|
# |    Instructions :                     | | CONSOLIDATE : copie les medias dans     |
# | 1- Mode : Relocate ou Consolidate     | | Destination / Scene / Type (VIDEO,      |
# | 2- Relocate : Search Folders (;)      | | IMAGE, AUDIO, 3D), partages dans        |
# |    Consolidate : Consolidate Folder   | | _COMMUN, puis repointe le projet.       |
# |    (dans un Media Directory)          | | - Rapport HTML (navigateur)             |
# | 3- Execute = rapport ; Apply Changes  | | - Rien n'est modifie sans Apply Changes |
# |    + Execute = applique               | |                                         |
# |_______________________________________| |_________________________________________|
#
# HISTORIQUE
# V0.1 - 08/10/2026 - Version initiale : scan des FileReference, index disque par nom,
#                      score par dossiers communs, rapport texte, application optionnelle.
# V0.2 - 08/10/2026 - Fichier retrouve hors de tout Media Directory : repointe en chemin
#                      absolu (accepte par Smode, verifie) si Allow Absolute Paths est coche.
# V0.3 - 08/10/2026 - Fix compile dans un Script Smode : declarations de parametres placees
#                      avant les imports (ScriptStatementOrderException).
# V0.4 - 08/10/2026 - Rapport HTML ouvert dans le navigateur : tuiles de compteurs cliquables
#                      (filtre), une couleur par cas, boutons copier chemin/dossier par fichier,
#                      utilisations depliables, clair/sombre. Option Open Report.
#                      Conseil "Search Folders" affiche sur les fichiers introuvables.
# V0.5 - 08/10/2026 - Mode Consolidate : copie vers Consolidate Folder / Scene / Type,
#                      fichiers partages entre Scenes dans _COMMUN, collisions de noms suffixees,
#                      copie identique reutilisee, packs Smode ignores, repointage verifie.
#                      Liste deroulante Mode (Relocate / Consolidate). Panneau de parametres
#                      organise en sections (GENERAL / RELOCATE / CONSOLIDATE / RAPPORT).
#                      Liste Mode remplie des la compilation (expression lambda dans la declaration).
#                      Rapport : chemin "avant" en gris au lieu de barre. Guillemets retires
#                      autour des chemins saisis (Search Folders / Consolidate Folder).
#                      Fichier copie pas encore indexe par Smode : reload + etat "En attente Smode"
#                      (au lieu de "Echec"), aussi detecte au passage suivant.
# V0.6 - 08/10/2026 - Relecture du code, corrections : dossiers de recherche imbriques (un meme fichier
#                      n'est plus compte deux fois -> faux "ambigu") ; Media Directory a la racine d'un
#                      lecteur reconnu ; copie via .fmgpart supprime en cas d'erreur + controle de l'espace
#                      libre ; controle "destination en lecture seule" exact (plus de faux positif par prefixe) ;
#                      Scene nommee CON, NUL, AUX, COM1... : dossier prefixe par _ (nom reserve Windows).
#

# =============== OPTIONS (visibles/modifiables dans le panneau du Script) ===============
# (Smode exige les declarations de parametres avant toute autre instruction, imports compris)
# Les titres en MAJUSCULES sont de faux parametres qui servent de separateurs dans le panneau
# (le libelle affiche = nom de la variable, les majuscules sont conservees ; valeur ignoree).
GENERAL: Oil.String("----------------------------------------")
# Mode : liste Relocate / Consolidate remplie DES LA COMPILATION (une seule expression : les declarations
# doivent preceder toute instruction, donc pas de fonction ; sinon la liste reste vide jusqu'au 1er Execute)
mode: (lambda e: ([e.enumerators.append((lambda n: (setattr(n, "label", lab), setattr(n, "value", i), n)[2])(Oil.createObject("CustomEnumerator"))) for i, lab in enumerate(("Relocate", "Consolidate"))], e.set("Relocate"), e)[2])(Oil.createObject("CustomEnumeration"))
applyChanges: Oil.Boolean(False)   # decoche = rapport seul ; coche = applique (repointe / copie)
RELOCATE: Oil.String("----------------------------------------")
searchFolders: Oil.String("")      # dossiers ou chercher, separes par ";" (vide = tous les Media Directories modifiables)
allowAbsolutePaths: Oil.Boolean(True)   # fichier hors Media Directory : chemin disque absolu (non portable)
CONSOLIDATE: Oil.String("----------------------------------------")
consolidateFolder: Oil.String("")  # dossier de destination (doit etre dans un Media Directory)
RAPPORT: Oil.String("----------------------------------------")
openReport: Oil.Boolean(True)      # ouvre le rapport HTML dans le navigateur a la fin
status: Oil.String("")             # resume du dernier passage

import os
import re
import glob
import datetime

SKIP_CLASSES = ('String', 'SrgbColor', 'Boolean', 'PositiveReal', 'Real', 'Percentage',
                'UnboundedPercentage', 'Integer', 'Matrix4d')
REPORT_DIR = os.path.join(os.path.expanduser("~"), "Documents", "Smode Filemanager")


# ----------------------------- Media Directories -----------------------------
def read_media_directories():
    """[(nom, dossier absolu, lecture seule)] depuis la configuration Data_<version>.configuration de Smode."""
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


def _clean_path(p):
    """Chemin saisi dans le panneau -> sans espaces ni guillemets autour ("Copier en tant que chemin d'acces")."""
    return str(p).strip().strip('"\'').strip()


def from_smode_path(path, media_dirs):
    """'NomMediaDirectory/sous/dossier/fichier' (ou chemin absolu) -> chemin disque, None si inconnu."""
    path = str(path).replace("\\", "/")
    if re.match(r"^[A-Za-z]:/", path):
        return os.path.abspath(path)
    for name, d, _ in sorted(media_dirs, key=lambda m: -len(m[0])):   # nom le plus long d'abord
        if path.startswith(name + "/"):
            return os.path.join(d, *path[len(name) + 1:].split("/"))
    return None


def _root(d):
    """Dossier normalise pour comparer des chemins, sans separateur final (gere la racine d'un lecteur, ex. G:\\)."""
    return os.path.normcase(os.path.abspath(d)).rstrip(os.sep)


def to_smode_path(abs_path, media_dirs):
    """Chemin disque -> 'NomMediaDirectory/sous/dossier/fichier' (le Media Directory le plus profond gagne)."""
    p = os.path.normcase(os.path.abspath(abs_path))
    best = None
    for name, d, _ in media_dirs:
        root = _root(d)
        if p.startswith(root + os.sep) and (best is None or len(root) > len(best[1])):
            best = (name, root)
    if best is None:
        return None
    rel = os.path.abspath(abs_path)[len(best[1]) + 1:]
    return best[0] + "/" + rel.replace(os.sep, "/")


# ----------------------------- Scan du projet -----------------------------
def scan_file_references(project):
    """Toutes les FileReference du projet : [(chemin d'elements lisible, nom de la Scene, FileReference)]."""
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
        if cn in SKIP_CLASSES:
            return
        try:
            uid = o.getUniqueIdentifier()
        except Exception:
            uid = None
        if uid:                       # uid nul pour certains objets : ne pas dedupliquer dessus
            if uid in seen:
                return
            seen.add(uid)
        try:
            lab = o.label.get()
            if lab:
                labels = labels + [str(lab)]
                if cn == "Scene" and scene is None:   # 1re Scene sous la masterScene (sans label)
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


def is_missing(ref):
    fo = ref.file.get()
    return fo is None or fo.getOilClassName() == "MissingFile"


# ----------------------------- Recherche disque -----------------------------
def build_index(folders):
    """nom de fichier (minuscule) -> [chemins absolus]. Ignore les .meta de Smode. Un dossier contenu dans un autre
    de la liste n'est parcouru qu'une fois, et un meme fichier n'est jamais compte deux fois (sinon faux "ambigu")."""
    roots = []                                    # (cle normalisee, dossier tel que saisi : on garde sa casse)
    for f in sorted(folders, key=lambda x: len(_root(x))):
        k = _root(f)
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


def score(old_path, candidate):
    """Nombre de dossiers communs (en partant du fichier) entre l'ancien chemin Smode et le candidat."""
    old_dirs = [s.lower() for s in old_path.split("/")[:-1]]
    new_dirs = [s.lower() for s in os.path.dirname(candidate).split(os.sep)]
    n = 0
    for a, b in zip(reversed(old_dirs), reversed(new_dirs)):
        if a != b:
            break
        n += 1
    common = len(set(old_dirs) & set(new_dirs))   # departage secondaire : dossiers communs n'importe ou
    return (n, common)


def resolve(old_path, index):
    """-> ('found', candidat) | ('ambiguous', [candidats]) | ('notfound', None)"""
    cands = index.get(old_path.split("/")[-1].lower(), [])
    if not cands:
        return "notfound", None
    if len(cands) == 1:
        return "found", cands[0]
    ranked = sorted(cands, key=lambda c: score(old_path, c), reverse=True)
    if score(old_path, ranked[0]) > score(old_path, ranked[1]):
        return "found", ranked[0]
    return "ambiguous", ranked


# ----------------------------- Rapport HTML -----------------------------
# etats : cle -> (libelle, couleur, explication)
RELOCATE_STATES = {
    "applied":     ("Applique",                 "#1a9e55", "Fichier repointe et verifie"),
    "applied_abs": ("Applique (chemin absolu)", "#c98a00", "Repointe hors Media Directory : chemin non portable"),
    "found":       ("Retrouve",                 "#2f6fde", "Pret a appliquer (cocher Apply Changes)"),
    "found_abs":   ("Retrouve (chemin absolu)", "#c98a00", "Hors Media Directory : sera repointe en chemin absolu"),
    "outside":     ("Hors Media Directory",     "#d9622b", "Trouve mais Allow Absolute Paths est decoche"),
    "ambiguous":   ("Ambigu",                   "#8e44ad", "Plusieurs candidats a egalite : choix manuel"),
    "notfound":    ("Introuvable",              "#d33a3a", "Aucun fichier de ce nom dans les dossiers fouilles"),
    "failed":      ("Echec",                    "#a11d1d", "Repointe mais toujours manquant pour Smode"),
}
RELOCATE_ORDER = ["failed", "notfound", "ambiguous", "outside", "found_abs", "found", "applied_abs", "applied"]

CONSOLIDATE_STATES = {
    "copied":    ("Copie",               "#1a9e55", "Fichier copie puis repointe et verifie"),
    "reused":    ("Deja copie",          "#13877f", "Copie identique deja presente : repointe sans recopier"),
    "planned":   ("A copier",            "#2f6fde", "Sera copie (cocher Apply Changes)"),
    "pending":   ("En attente Smode",    "#2a9fc9", "Fichier sur le disque, pas encore indexe par Smode : rechargement "
                                                    "lance, relancer Execute pour verifier"),
    "inplace":   ("Deja consolide",      "#6b7385", "Deja dans le dossier de destination : rien a faire"),
    "pack":      ("Pack Smode ignore",   "#8a8f99", "Media d'un Media Directory en lecture seule (Standard Pack...)"),
    "missing":   ("Manquant",            "#d33a3a", "Fichier introuvable : lancer d'abord un Relocate"),
    "failed":    ("Echec",               "#a11d1d", "Copie ou repointage en erreur"),
}
CONSOLIDATE_ORDER = ["failed", "missing", "pending", "planned", "copied", "reused", "inplace", "pack"]

HTML_CSS = """
:root{--bg:#f6f7f9;--card:#fff;--fg:#1d2330;--mut:#6b7385;--line:#e3e6ec;--code:#f0f2f5;--link:#2f6fde}
@media (prefers-color-scheme:dark){:root{--bg:#14161b;--card:#1d2027;--fg:#e6e8ee;--mut:#9aa1b2;--line:#2c3039;--code:#262a33;--link:#7ea6ff}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:14px/1.45 "Segoe UI",system-ui,sans-serif}
main{max-width:1100px;margin:0 auto;padding:28px 16px 60px}
h1{margin:0;font-size:22px;letter-spacing:.02em}h1 small{color:var(--mut);font-weight:400;font-size:14px;margin-left:8px}
.meta{color:var(--mut);margin:6px 0 18px}.meta code{background:var(--code);padding:1px 6px;border-radius:4px}
.err{background:#d33a3a;color:#fff;border-radius:8px;padding:10px 14px;margin:0 0 18px}
.tiles{display:flex;flex-wrap:wrap;gap:10px;margin:0 0 18px}
.tile{all:unset;cursor:pointer;background:var(--card);border:1px solid var(--line);border-left:5px solid var(--c);
 border-radius:8px;padding:10px 14px;min-width:120px;display:flex;flex-direction:column}
.tile b{font-size:22px;color:var(--c)}.tile span{color:var(--mut);font-size:12px}
.tile.off{opacity:.35}.all{--c:var(--fg)}
.row{background:var(--card);border:1px solid var(--line);border-left:5px solid var(--c);border-radius:8px;
 padding:10px 14px;margin:0 0 8px}
.row header{display:flex;flex-wrap:wrap;align-items:center;gap:10px;margin-bottom:6px}
.badge{background:var(--c);color:#fff;font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:.04em;
 padding:2px 8px;border-radius:999px}
.name{font-weight:600}.expl{color:var(--mut);font-size:12px}
.p{display:flex;gap:8px;align-items:baseline;margin:2px 0;min-width:0;flex-wrap:wrap}
.k{color:var(--mut);font-size:11px;width:38px;flex:none;text-align:right}
code{font:12px Consolas,monospace;background:var(--code);padding:2px 6px;border-radius:4px;overflow-wrap:anywhere}
.strike code{color:var(--mut)}.new code{border-left:3px solid var(--c)}
.cp{font:11px "Segoe UI",system-ui,sans-serif;color:var(--link);background:none;border:1px solid var(--line);
 border-radius:4px;padding:1px 7px;cursor:pointer;white-space:nowrap}.cp:hover{border-color:var(--link)}
.cp.ok{color:#1a9e55;border-color:#1a9e55}
details{margin-top:6px;color:var(--mut);font-size:12px}summary{cursor:pointer}ul{margin:4px 0 0;padding-left:20px}
.folders{margin:0 0 18px;padding-left:18px;color:var(--mut);font:12px Consolas,monospace}
.empty{padding:30px;text-align:center;color:var(--mut)}
.hint{margin:8px 0 2px 46px;padding:6px 10px;border-radius:6px;font-size:12px;
 background:color-mix(in srgb,var(--c) 10%,transparent);border:1px dashed var(--c)}
"""

HTML_JS = """
document.querySelectorAll('.tile').forEach(function(t){t.onclick=function(){var f=t.dataset.f;
document.querySelectorAll('.tile').forEach(function(x){x.classList.toggle('off',f!=='*'&&x!==t)});
document.querySelectorAll('.row').forEach(function(r){r.style.display=(f==='*'||r.dataset.s===f)?'':'none'})}});
function copyText(t){
  if(navigator.clipboard&&window.isSecureContext){return navigator.clipboard.writeText(t)}
  var a=document.createElement('textarea');a.value=t;a.style.position='fixed';a.style.opacity='0';
  document.body.appendChild(a);a.select();document.execCommand('copy');a.remove();return Promise.resolve()}
document.querySelectorAll('.cp').forEach(function(b){var lab=b.textContent;b.onclick=function(){
  copyText(b.dataset.p).then(function(){b.textContent='copie !';b.classList.add('ok');
  setTimeout(function(){b.textContent=lab;b.classList.remove('ok')},1200)})}});
"""

NOTFOUND_HINT = ('<div class="hint">Conseil : indiquer dans <b>Search Folders</b> le dossier ou se trouve '
                 'probablement ce fichier (ou un dossier parent, ex. le dossier du projet), plusieurs dossiers '
                 'separes par <code>;</code>. Par defaut seuls les Media Directories sont fouilles.</div>')


def _esc(t):
    return str(t).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def _copy_btn(text, label):
    """Bouton qui copie un chemin dans le presse-papier (les liens file:/// sont bloques par les navigateurs)."""
    return ' <button class="cp" data-p="%s" title="%s">%s</button>' % (_esc(text), _esc(text), label)


def _links(abs_path):
    if not abs_path:
        return ""
    abs_path = os.path.abspath(abs_path)
    return _copy_btn(abs_path, "copier le chemin") + _copy_btn(os.path.dirname(abs_path), "copier le dossier")


def write_html_report(path, kind, project_name, folders_title, folders, entries, n_refs, apply,
                      states, order, error=""):
    """entries : dicts {state, old, old_abs?, new?, abs?, cands?, users, hint?}."""
    counts = {k: sum(1 for e in entries if e["state"] == k) for k in order}
    tiles = "".join(
        '<button class="tile" data-f="%s" style="--c:%s"><b>%d</b><span>%s</span></button>'
        % (k, states[k][1], counts[k], states[k][0]) for k in order if counts[k])
    rows = []
    for e in sorted(entries, key=lambda e: (order.index(e["state"]), e["old"].lower())):
        lab, col, expl = states[e["state"]]
        strike = " strike" if e.get("new") and e["state"] not in ("inplace", "pack") else ""
        body = ('<div class="p old%s"><span class="k">avant</span><code>%s</code>%s</div>'
                % (strike, _esc(e["old"]), _links(e.get("old_abs"))))
        if e.get("new"):
            body += ('<div class="p new"><span class="k">apres</span><code>%s</code>%s</div>'
                     % (_esc(e["new"]), _links(e.get("abs"))))
        for c in e.get("cands") or []:
            body += '<div class="p cand"><span class="k">?</span><code>%s</code>%s</div>' % (_esc(c), _links(c))
        body += e.get("hint", "")
        users = e["users"]
        uses = ('<details><summary>%d utilisation%s &middot; %s</summary><ul>%s</ul></details>'
                % (len(users), "s" if len(users) > 1 else "", _esc(users[0] or "(racine)"),
                   "".join("<li>%s</li>" % _esc(u or "(racine)") for u in users)))
        rows.append('<article class="row" data-s="%s" style="--c:%s"><header><span class="badge">%s</span>'
                    '<span class="name">%s</span><span class="expl">%s</span></header>%s%s</article>'
                    % (e["state"], col, lab, _esc(e["old"].split("/")[-1]), expl, body, uses))
    mode = "application" if apply else "rapport seul (rien n'a ete modifie)"
    html = ('<!doctype html><html lang="fr"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            '<title>Smode Filemanager - ' + kind + '</title><style>' + HTML_CSS + '</style></head><body><main>'
            '<h1>Smode Filemanager<small>' + kind + ' &middot; ' + mode + '</small></h1>'
            '<div class="meta">Projet <code>%s</code> &middot; %s &middot; %d fichiers, %d references</div>'
            % (_esc(project_name), datetime.datetime.now().strftime("%d/%m/%Y %H:%M"), len(entries), n_refs)
            + ('<div class="err">%s</div>' % _esc(error) if error else "")
            + '<div class="tiles"><button class="tile all" data-f="*"><b>%d</b><span>Tout afficher</span></button>%s</div>'
            % (len(entries), tiles)
            + '<details><summary>%s (%d)</summary><ul class="folders">%s</ul></details>'
            % (folders_title, len(folders), "".join("<li>%s%s</li>" % (_esc(f), _copy_btn(os.path.abspath(f), "copier"))
                                                    for f in folders))
            + '<section id="list">' + ("".join(rows) or '<div class="empty">Rien a signaler.</div>')
            + '</section></main><script>' + HTML_JS + '</script></body></html>')
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(html)


def _finish_report(kind, project, folders_title, folders, entries, n_refs, apply, states, order, open_report,
                   error=""):
    os.makedirs(REPORT_DIR, exist_ok=True)
    report = os.path.join(REPORT_DIR, "%s_%s.html" % (kind.lower(), datetime.datetime.now().strftime("%Y%m%d_%H%M%S")))
    write_html_report(report, kind, project.getFriendlyName(), folders_title, folders, entries, n_refs, apply,
                      states, order, error)
    if open_report:
        try:
            os.startfile(report)
        except Exception as ex:
            print("Ouverture du rapport impossible : %s" % ex)
    return report


# ----------------------------- Relocate -----------------------------
def run(project, search_folders="", apply=False, allow_absolute=True, open_report=False):
    media_dirs = read_media_directories()
    folders = [_clean_path(f) for f in search_folders.split(";") if _clean_path(f)]
    if not folders:
        folders = [d for _, d, ro in media_dirs if not ro]
    folders = [f for f in folders if os.path.isdir(f)]

    missing = {}                                   # ancien chemin -> [(labels, ref)]
    for labels, _, ref in scan_file_references(project):
        path = str(ref.path.get())
        if path and is_missing(ref):
            missing.setdefault(path, []).append((labels, ref))

    index = build_index(folders) if missing else {}
    entries = []
    for old in sorted(missing):
        users = missing[old]
        e = {"old": old, "users": [u for u, _ in users]}
        kind, cand = resolve(old, index)
        if kind == "found":
            new = to_smode_path(cand, media_dirs)
            absolute = new is None
            e["abs"] = cand
            if absolute and not allow_absolute:
                e.update(state="outside", new=cand)
            else:
                if absolute:
                    new = cand
                e.update(state="found_abs" if absolute else "found", new=new)
                if apply:
                    for _, ref in users:
                        ref.path.set(new)
                    ok = not any(is_missing(r) for _, r in users)
                    e["state"] = ("applied_abs" if absolute else "applied") if ok else "failed"
        elif kind == "ambiguous":
            e.update(state="ambiguous", cands=cand)
        else:
            e.update(state="notfound", hint=NOTFOUND_HINT)
        entries.append(e)

    c = lambda *ks: sum(1 for e in entries if e["state"] in ks)
    n_refs = sum(len(u) for u in missing.values())
    summary = ("%d fichiers manquants (%d references) | retrouves %d | ambigus %d | introuvables %d | hors Media Dir %d"
               % (len(missing), n_refs, c("found", "applied", "failed"), c("ambiguous"), c("notfound"),
                  c("outside", "found_abs", "applied_abs")))
    if apply:
        summary += " | appliques %d | echecs %d" % (c("applied", "applied_abs"), c("failed"))
    report = _finish_report("Relocate", project, "Dossiers fouilles", folders, entries, n_refs, apply,
                            RELOCATE_STATES, RELOCATE_ORDER, open_report)
    lines = ["%s | %s -> %s" % (RELOCATE_STATES[e["state"]][0].upper(), e["old"], e.get("new") or "") for e in entries]
    return summary, report, lines


# ----------------------------- Consolidate -----------------------------
TYPE_FOLDERS = {"VideoFileContent": "VIDEO", "Color2dMipmaps": "IMAGE", "AudioFileContent": "AUDIO",
                "Group3dLayer": "3D"}
EXT_FOLDERS = {"VIDEO": (".mov", ".mp4", ".avi", ".mxf", ".mkv", ".webm", ".hap"),
               "IMAGE": (".png", ".jpg", ".jpeg", ".tif", ".tiff", ".exr", ".bmp", ".tga", ".dds", ".hdr", ".psd"),
               "AUDIO": (".wav", ".mp3", ".aif", ".aiff", ".flac", ".ogg"),
               "3D": (".fbx", ".obj", ".gltf", ".glb", ".abc", ".usd", ".usdz", ".3ds", ".dae")}
SHARED_FOLDER = "_COMMUN"
NO_SCENE_FOLDER = "_PROJET"


def media_type_folder(ref_class, path):
    inner = ref_class[len("FileReference("):-1] if ref_class.startswith("FileReference(") else ""
    if inner in TYPE_FOLDERS:
        return TYPE_FOLDERS[inner]
    ext = os.path.splitext(path)[1].lower()
    for folder, exts in EXT_FOLDERS.items():
        if ext in exts:
            return folder
    return "AUTRES"


def _safe_name(name):
    """Nom de Scene -> nom de dossier Windows valide."""
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip().rstrip(".")
    if re.match(r"^(con|prn|aux|nul|com\d|lpt\d)(\..*)?$", name, re.I):   # noms reserves par Windows
        name = "_" + name
    return name or "_SANS_NOM"


def _same_file(a, b):
    try:
        return os.path.getsize(a) == os.path.getsize(b) and int(os.path.getmtime(a)) == int(os.path.getmtime(b))
    except OSError:
        return False


def _copy_file(src, dst):
    """Copie via un fichier .fmgpart renomme a la fin : en cas d'erreur (disque plein...) le fichier partiel est
    supprime au lieu de rester sur le disque. Verifie d'abord l'espace libre."""
    import shutil
    free = shutil.disk_usage(os.path.dirname(dst)).free
    size = os.path.getsize(src)
    if size > free:
        raise RuntimeError("espace insuffisant sur le disque de destination (%d Mo a copier, %d Mo libres)"
                           % (size // 1048576, free // 1048576))
    tmp = dst + ".fmgpart"
    try:
        shutil.copy2(src, tmp)
        os.replace(tmp, dst)
    except BaseException:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def consolidate(project, dest_folder, apply=False, open_report=False):
    import shutil
    media_dirs = read_media_directories()
    dest = os.path.abspath(_clean_path(dest_folder)) if _clean_path(dest_folder) else ""
    error = ""
    if not dest:
        error = "Consolidate Folder est vide : indiquer le dossier de destination."
    elif to_smode_path(os.path.join(dest, "x"), media_dirs) is None:
        error = ("Le dossier de destination n'est dans aucun Media Directory : l'ajouter comme Media Directory "
                 "dans Smode (ou choisir un dossier qui en fait partie), puis relancer. Si tu viens de l'ajouter : "
                 "Smode enregistre la liste avec quelques secondes de retard, attendre un peu et relancer.")
    elif any(ro and (_root(dest) + os.sep).startswith(_root(d) + os.sep) for _, d, ro in media_dirs):
        error = "Le dossier de destination est dans un Media Directory en lecture seule."

    # source absolue -> {refs, users, scenes, ref_class, smode_path}
    files = {}
    missing, missing_refs = {}, {}
    for labels, scene, ref in scan_file_references(project):
        path = str(ref.path.get())
        if not path:
            continue
        src = None
        if not is_missing(ref):
            try:
                src = os.path.abspath(str(ref.file.get().nativeFile.get()))
            except Exception:
                pass
        if src is None:
            missing.setdefault(path, []).append(labels)
            missing_refs.setdefault(path, []).append(ref)
            continue
        f = files.setdefault(src, {"refs": [], "users": [], "scenes": set(), "cls": ref.getOilClassName(),
                                   "smode": path})
        f["refs"].append(ref)
        f["users"].append(labels)
        f["scenes"].add(scene or NO_SCENE_FOLDER)

    entries = []
    for p, u in sorted(missing.items()):
        on_disk = from_smode_path(p, media_dirs)
        if on_disk and os.path.isfile(on_disk):
            # present sur le disque mais pas encore indexe par Smode (copie recente) : rechargement
            for r in missing_refs[p]:
                r.reload.trig()
            entries.append({"state": "pending", "old": p, "old_abs": on_disk, "users": u})
        else:
            entries.append({"state": "missing", "old": p, "users": u})
    used_targets = {}                             # cible (normcase) -> source, pour eviter les collisions de noms
    for src in sorted(files, key=lambda s: s.lower()):
        f = files[src]
        e = {"old": f["smode"], "old_abs": src, "users": f["users"]}
        entries.append(e)
        ro = [d for _, d, r in media_dirs if r and os.path.normcase(src).startswith(_root(d) + os.sep)]
        if ro:
            e["state"] = "pack"
            continue
        if dest and os.path.normcase(src).startswith(_root(dest) + os.sep):
            e["state"] = "inplace"
            continue
        scene_dir = SHARED_FOLDER if len(f["scenes"]) > 1 else _safe_name(next(iter(f["scenes"])))
        folder = os.path.join(dest or "<destination>", scene_dir, media_type_folder(f["cls"], src))
        base, ext = os.path.splitext(os.path.basename(src))
        target, n = os.path.join(folder, base + ext), 2
        while os.path.normcase(target) in used_targets and used_targets[os.path.normcase(target)] != src \
                or (os.path.exists(target) and not _same_file(src, target)):
            target, n = os.path.join(folder, "%s (%d)%s" % (base, n, ext)), n + 1
        used_targets[os.path.normcase(target)] = src
        new = to_smode_path(target, media_dirs) if dest else None
        e.update(new=new or target, abs=target, state="planned")
        if not apply or error:
            continue
        try:
            reused = os.path.exists(target)
            if not reused:
                os.makedirs(folder, exist_ok=True)
                _copy_file(src, target)
            for ref in f["refs"]:
                ref.path.set(new)
            still = [r for r in f["refs"] if is_missing(r)]
            if not still:
                e["state"] = "reused" if reused else "copied"
            elif os.path.exists(target):
                # Smode indexe les fichiers fraichement copies en differe : forcer le rechargement
                for r in still:
                    r.reload.trig()
                e["state"] = "pending"
            else:
                e["state"] = "failed"
        except Exception as ex:
            e["state"] = "failed"
            e["hint"] = '<div class="hint">%s</div>' % _esc(ex)

    c = lambda *ks: sum(1 for e in entries if e["state"] in ks)
    n_refs = sum(len(f["refs"]) for f in files.values()) + sum(len(u) for u in missing.values())
    summary = ("%d fichiers | a copier %d | deja consolides %d | pack Smode %d | manquants %d"
               % (len(entries), c("planned", "copied", "reused", "failed") + (c("pending") if apply else 0),
                  c("inplace"), c("pack"), c("missing")))
    if apply and not error:
        summary += " | copies %d | deja copies %d | echecs %d" % (c("copied"), c("reused"), c("failed"))
    if c("pending"):
        summary += " | en attente Smode %d (relancer Execute)" % c("pending")
    if error:
        summary = "ERREUR : " + error
    report = _finish_report("Consolidate", project, "Dossier de destination", [dest] if dest else [], entries,
                            n_refs, apply and not error, CONSOLIDATE_STATES, CONSOLIDATE_ORDER, open_report, error)
    lines = ["%s | %s -> %s" % (CONSOLIDATE_STATES[e["state"]][0].upper(), e["old"], e.get("new") or "")
             for e in entries]
    return summary, report, lines


# ----------------------------- Lancement -----------------------------
def _ensure_mode_enum():
    """Peuple la liste deroulante Mode (CustomEnumeration vide a la declaration, cf. smode-oil-reference)."""
    if len(script.mode.enumerators) == 0:
        for i, lab in enumerate(("Relocate", "Consolidate")):
            en = Oil.createObject("CustomEnumerator")
            en.label = lab
            en.value = i
            script.mode.enumerators.append(en)
        script.mode.set("Relocate")


if "FM_NO_RUN" not in globals():
    _ensure_mode_enum()
    for _title in ("GENERAL", "RELOCATE", "CONSOLIDATE", "RAPPORT"):   # separateurs remis en place s'ils ont ete edites
        setattr(script, _title, "-" * 40)
    if str(script.mode.get()) == "Consolidate":
        _summary, _report, _ = consolidate(script.project, str(script.consolidateFolder), bool(script.applyChanges),
                                           bool(script.openReport))
    else:
        _summary, _report, _ = run(script.project, str(script.searchFolders), bool(script.applyChanges),
                                   bool(script.allowAbsolutePaths), bool(script.openReport))
    script.status = _summary
    print(_summary)
    print("Rapport : " + _report)
