# app/scanner.py -- standalone library scanner (Eagle-style).
#
# Scans local directories for .uasset files, identifies Niagara / Cascade
# effects WITHOUT requiring UE (best-effort byte scan), generates a stylized
# placeholder thumbnail, optionally copies the file into the library, and
# records everything into the local SQLite library.
#
# UE is only an OPTIONAL enhancer: if a project is configured, the client can
# later re-render real thumbnails via the bridge (see render_files command).

import os
import time
import shutil
import hashlib
from typing import List

from PySide6.QtCore import QThread, Signal

from app.database import Database
from app.models import FXAsset, TYPE_NIAGARA, TYPE_CASCADE, TYPE_UNKNOWN
from app import uasset_thumb
from app.ue_project import detect_ue_project, project_folder_name

# Directories that never contain user FX assets worth cataloging.
SKIP_DIRS = {
    ".git", ".svn", ".vs", ".idea", "__pycache__", "node_modules",
    "Config", "Saved", "Intermediate", "Binaries", "DerivedDataCache",
    "ThirdParty", "Extras", "Source", "Build",
}

# Sentinel for "not yet cached" (distinct from a cached None / no-project).
_MISSING = object()


def find_uassets(root: str) -> List[str]:
    """Recursively collect .uasset file paths under `root`."""
    out = []
    root = os.path.abspath(root)
    for dirpath, dirnames, filenames in os.walk(root):
        # prune non-asset directories in place
        dirnames[:] = [
            d for d in dirnames
            if d not in SKIP_DIRS and not d.startswith(".")
        ]
        for fn in filenames:
            if fn.lower().endswith(".uasset"):
                out.append(os.path.join(dirpath, fn))
    return out


def detect_type_offline(path: str):
    """Best-effort type detection by scanning the package name table bytes.

    Returns (type, class_name, is_blueprint). Works for the vast majority of
    NiagaraSystem / ParticleSystem assets without launching UE.

    Particle-system references take PRIORITY over non-FX class markers: a
    Blueprint that *contains* a Niagara/Cascade system must still be recognized
    as an effect, otherwise real FX nested inside Blueprints would be dropped.

    `is_blueprint` distinguishes the two flavors of detected FX:
      - False -> a "pure" FX asset (the file itself is a Niagara/Cascade system)
      - True  -> an FX *wrapped inside a Blueprint* (the file is a Blueprint that
                 *contains* a Niagara/Cascade system)

    A plain Blueprint/Material/Mesh with no embedded FX falls through to
    TYPE_UNKNOWN and is skipped by the FX-only scanner.
    """
    try:
        with open(path, "rb") as fh:
            head = fh.read(8 * 1024 * 1024)  # name table usually near the front
    except Exception:
        return TYPE_UNKNOWN, "", False

    # 1) Particle-system references win first: an asset is treated as an effect
    #    whenever it actually carries a Niagara / Cascade system, even if it is
    #    wrapped inside a Blueprint.
    has_particle = (b"NiagaraSystem" in head or b"NiagaraEmitter" in head
                    or b"ParticleSystem" in head)
    if has_particle:
        # is this effect wrapped inside a Blueprint? (contains both a particle
        # marker and a Blueprint class marker)
        is_blueprint = (
            b"BlueprintGeneratedClass" in head
            or b"WidgetBlueprint" in head
            or b"AnimBlueprint" in head
        )
        if b"ParticleSystem" in head:
            return TYPE_CASCADE, "ParticleSystem", is_blueprint
        return TYPE_NIAGARA, "NiagaraSystem", is_blueprint

    # 2) Plain non-FX assets (Blueprint, Material, Mesh, Sound, ...) that carry
    #    no particle system are ignored in FX-only mode.
    NON_FX = (
        b"BlueprintGeneratedClass",
        b"WidgetBlueprint",
        b"AnimBlueprint",
        b"Material",
        b"MaterialInstance",
        b"MaterialFunction",
        b"Sound",
        b"Texture",
        b"StaticMesh",
        b"SkeletalMesh",
        b"Animation",
        b"ControlRig",
    )
    for marker in NON_FX:
        if marker in head:
            return TYPE_UNKNOWN, "", False
    return TYPE_UNKNOWN, "", False


# ---- placeholder thumbnail (Pillow, runs off the GUI thread) ----
_TYPE_COLORS = {
    TYPE_NIAGARA: ("#635bff", "#7c5cff"),
    TYPE_CASCADE: ("#8b5cf6", "#ec4899"),
    TYPE_UNKNOWN: ("#475569", "#94a3b8"),
}
_TYPE_GLYPH = {
    TYPE_NIAGARA: "N",
    TYPE_CASCADE: "C",
    TYPE_UNKNOWN: "?",
}


def _rgb(hexstr):
    h = hexstr.lstrip("#")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def make_placeholder_thumb(out_path: str, fx_type: str, name: str, size: int = 320):
    """Draw a stylized gradient thumbnail with a big type glyph + soft dots."""
    from PIL import Image, ImageDraw, ImageFont

    w = h = size
    a, b = _TYPE_COLORS.get(fx_type, _TYPE_COLORS[TYPE_UNKNOWN])
    ca, cb = _rgb(a), _rgb(b)

    img = Image.new("RGB", (w, h))
    px = img.load()
    # vertical gradient
    for y in range(h):
        t = y / max(1, h - 1)
        r = int(ca[0] + (cb[0] - ca[0]) * t)
        g = int(ca[1] + (cb[1] - ca[1]) * t)
        bl = int(ca[2] + (cb[2] - ca[2]) * t)
        for x in range(w):
            px[x, y] = (r, g, bl)

    d = ImageDraw.Draw(img, "RGBA")
    # soft glow circles
    d.ellipse([w - 90, -30, w + 50, 110], fill=(255, 255, 255, 40))
    d.ellipse([-40, h - 70, 110, h + 70], fill=(255, 255, 255, 30))
    # particle dots
    import random
    random.seed(abs(hash(name)) % (2 ** 31))
    for _ in range(14):
        x = random.randint(10, w - 10)
        y = random.randint(10, h - 10)
        r = random.randint(1, 3)
        d.ellipse([x - r, y - r, x + r, y + r], fill=(255, 255, 255, 90))

    # centered glyph
    glyph = _TYPE_GLYPH.get(fx_type, "?")
    try:
        font = ImageFont.truetype("arial.ttf", 150)
    except Exception:
        try:
            font = ImageFont.truetype(
                "C:/Windows/Fonts/arial.ttf", 150)
        except Exception:
            font = ImageFont.load_default()
    try:
        bb = d.textbbox((0, 0), glyph, font=font)
        tw, th = bb[2] - bb[0], bb[3] - bb[1]
        d.text(((w - tw) / 2 - bb[0], (h - th) / 2 - bb[1] - 18),
               glyph, fill=(255, 255, 255, 235), font=font)
    except Exception:
        d.text((w / 2 - 40, h / 2 - 60), glyph,
               fill=(255, 255, 255, 235), font=font)

    # asset name (truncated) near the bottom for distinguishability
    try:
        nfont = ImageFont.truetype("arial.ttf", 22)
    except Exception:
        try:
            nfont = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 22)
        except Exception:
            nfont = ImageFont.load_default()
    disp = name if len(name) <= 18 else name[:17] + "…"
    try:
        nb = d.textbbox((0, 0), disp, font=nfont)
        nw, nh = nb[2] - nb[0], nb[3] - nb[1]
        d.text(((w - nw) / 2 - nb[0], h - nh - 16),
               disp, fill=(255, 255, 255, 220), font=nfont)
    except Exception:
        pass

    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    img.save(out_path, "PNG")
    return out_path


class ScannerWorker(QThread):
    progress = Signal(int, int, str)     # done, total, current name
    finished = Signal(dict)
    failed = Signal(str)

    def __init__(self, db_path: str, roots: List[str], thumbs_dir: str,
                 copy: bool = False, files_dir: str = None, fx_only: bool = True,
                 read_thumbs: bool = True, auto_categorize_ue: bool = True):
        super().__init__()
        self.db_path = db_path
        self.roots = [os.path.abspath(r) for r in roots if os.path.isdir(r)]
        self.thumbs_dir = thumbs_dir
        self.copy = copy
        self.files_dir = files_dir
        self.fx_only = fx_only
        self.read_thumbs = read_thumbs
        self.auto_categorize_ue = auto_categorize_ue
        self._seen = set()
        # Per-scan caches so we don't re-walk the tree for every file in a
        # project (all files under one Content/ share the same .uproject).
        self._uproj_cache = {}     # dir -> UEProject | None
        self._folder_cache = {}    # folder name -> folder id
        self._ue_folders = set()   # folder names created/used this scan (UE + non-UE)
        self._ue_categorized = 0   # assets auto-assigned to a UE project folder
        self._auto_categorized = 0  # assets auto-assigned to ANY auto folder

    def _unique_copy_path(self, src):
        base = os.path.basename(src)
        dst = os.path.join(self.files_dir, base)
        if dst not in self._seen and not os.path.exists(dst):
            self._seen.add(dst)
            return dst
        stem, ext = os.path.splitext(base)
        i = 1
        while True:
            cand = os.path.join(self.files_dir, "%s_%d%s" % (stem, i, ext))
            if cand not in self._seen and not os.path.exists(cand):
                self._seen.add(cand)
                return cand
            i += 1

    def _root_for(self, f):
        """Return the scan root that contains *f* — i.e. the folder the user
        picked to import from. When several roots match, the most specific
        (longest path) wins. Falls back to the file's immediate parent dir.
        """
        af = os.path.abspath(f)
        best = None
        for r in self.roots:
            ar = os.path.abspath(r)
            if af == ar or af.startswith(ar + os.sep):
                if best is None or len(ar) > len(best):
                    best = ar
        if best:
            return best
        return os.path.dirname(af)

    def _maybe_categorize(self, db, f, a=None):
        """Auto-assign *f* to a category based on where it lives.

        - Inside a UE project: category = "<ProjectName> [UE x.y]"; the asset's
          ``engine_version`` is recorded (e.g. "UE 5.4") for the thumbnail badge.
        - Outside any UE project: category = the name of the selected scan
          folder that contains the file, so every imported file lands in a
          folder named after its source. ``engine_version`` is left empty.

        Folders are created idempotently (re-scanning the same source never
        duplicates a category).
        """
        if not self.auto_categorize_ue:
            return
        d = os.path.dirname(f)
        proj = self._uproj_cache.get(d, _MISSING)
        if proj is _MISSING:
            proj = detect_ue_project(f)
            self._uproj_cache[d] = proj
        if proj is not None:
            fname = project_folder_name(proj)
            path = proj.uproject_path
            engine = proj.engine_label
            self._ue_categorized += 1
        else:
            root = self._root_for(f)
            fname = os.path.basename(root) or os.path.basename(d)
            path = root
            engine = ""
        # Record the engine version on the asset (drives the thumbnail badge).
        if a is not None:
            a.engine_version = engine
            db.set_engine_version(f, engine)
        # Idempotent folder creation + link.
        fid = self._folder_cache.get(fname)
        if fid is None:
            fid = db.ensure_folder(fname, path=path, virtual=1)
            self._folder_cache[fname] = fid
            self._ue_folders.add(fname)
        db.add_asset_to_folder(f, fid)
        self._auto_categorized += 1

    def run(self):
        # SQLite connections cannot be shared across threads. Create a fresh
        # connection inside the worker thread. Skip the startup backup (the
        # main-thread Database already snapshotted the file before launch).
        db = Database(self.db_path, backup=False)
        files = []
        for r in self.roots:
            files.extend(find_uassets(r))
        total = len(files)
        if total == 0:
            self.finished.emit({"total": 0, "niagara": 0, "cascade": 0,
                                 "unknown": 0, "skipped": 0,
                                 "roots": len(self.roots), "sources": [],
                                 "ue_folders": [], "ue_categorized": 0})
            return

        niagara = cascade = unknown = skipped = 0
        scanned_sources = []
        errors = []
        imported_at = time.strftime("%Y-%m-%dT%H:%M:%S")
        os.makedirs(self.thumbs_dir, exist_ok=True)
        if self.copy and self.files_dir:
            os.makedirs(self.files_dir, exist_ok=True)

        for i, f in enumerate(files):
            try:
                t, cn, is_bp = detect_type_offline(f)
                # FX-only mode: skip anything that is neither Niagara nor Cascade.
                # IMPORTANT: never delete on a non-FX verdict. The heuristic
                # reads only the first 8MB and can mis-classify large/compressed
                # assets as Unknown, so a destructive delete here would silently
                # drop real assets. We just skip; any prior good record (or a
                # user-cataloged "uncategorized" entry) is preserved.
                if self.fx_only and t == TYPE_UNKNOWN:
                    skipped += 1
                    self.progress.emit(i + 1, total, os.path.basename(f))
                    continue

                name = os.path.splitext(os.path.basename(f))[0]
                try:
                    size = os.path.getsize(f)
                except OSError:
                    size = 0

                stored = None
                if self.copy and self.files_dir:
                    dst = self._unique_copy_path(f)
                    shutil.copy2(f, dst)
                    stored = dst

                thumb_name = hashlib.md5(f.encode("utf-8")).hexdigest() + ".png"
                thumb_path = os.path.join(self.thumbs_dir, thumb_name)
                # Extract the editor thumbnail embedded in the .uasset (pure
                # Python, no UE). Fall back to a generated placeholder only when
                # no usable embedded image exists.
                extracted = False
                if self.read_thumbs:
                    try:
                        extracted = uasset_thumb.extract_thumbnail(f, thumb_path)
                    except Exception:
                        extracted = False
                if not extracted and not os.path.exists(thumb_path):
                    make_placeholder_thumb(thumb_path, t, name)

                # Persist the real-thumbnail state RELIABLY as `tier`
                # (1 = engine thumbnail, 4 = no-thumbnail placeholder)
                # AND mirror it into `has_thumb`. A transient extract
                # failure (e.g. the source file is briefly offline)
                # must NOT nuke a previously-recorded real thumbnail.
                prev = db.get_asset(f) if not extracted else None
                if extracted:
                    has_thumb, tier = True, 1
                elif self.read_thumbs:
                    # We actively checked and found no embedded thumbnail
                    # this pass. Keep a prior real thumbnail if one was
                    # recorded and the source file is still reachable.
                    if prev is not None and getattr(prev, "has_thumb", False) \
                            and os.path.exists(f):
                        has_thumb = True
                        tier = getattr(prev, "tier", 1) or 1
                    else:
                        has_thumb, tier = False, 4
                else:
                    # Thumbnail reading disabled this pass: trust the prior
                    # flag so a previously-extracted real thumbnail isn't lost.
                    has_thumb = bool(getattr(prev, "has_thumb", False)) if prev else False
                    tier = getattr(prev, "tier", 1) or 1
                a = FXAsset(
                    source_path=f, name=name, type=t, class_name=cn,
                    stored_path=stored, thumb_path=thumb_path, size=size,
                    imported_at=imported_at, source="scan", blueprint=is_bp,
                    has_thumb=has_thumb, tier=tier)
                db.upsert_asset(a)
                scanned_sources.append(f)
                self._maybe_categorize(db, f, a)

                if t == TYPE_NIAGARA:
                    niagara += 1
                elif t == TYPE_CASCADE:
                    cascade += 1
                else:
                    unknown += 1
            except Exception as e:
                # Isolate per-file failures: a single bad file (locked,
                # odd encoding, decode surprise) must NOT abort the whole
                # scan. Collect and continue so the library is built fully.
                errors.append("%s: %s" % (f, e))
                self.failed.emit(errors[-1])
                self.progress.emit(i + 1, total, os.path.basename(f))
                continue
            self.progress.emit(i + 1, total, name)

        self.finished.emit({
            "total": total, "niagara": niagara, "cascade": cascade,
            "unknown": unknown, "skipped": skipped, "roots": len(self.roots),
            "sources": scanned_sources, "errors": errors,
            "ue_folders": sorted(self._ue_folders),
            "ue_categorized": self._ue_categorized,
            "auto_categorized": self._auto_categorized,
        })
