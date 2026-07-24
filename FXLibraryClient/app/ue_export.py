# app/ue_export.py -- Export .uasset FX to another UE project's Content folder.
#
# Reads .uasset files to find asset references (/Game/... paths), then copies
# the main file plus discovered dependencies (recursively) to a target UE
# Content directory, preserving the original relative folder structure.
#
# Dependency resolution strategy:
#   1. Byte-scan the raw file for /Game/... patterns (catches FTopLevelAssetPath,
#      FSoftObjectPath, and other full-path serializations).
#   2. Try binary import-table parsing and resolve the outer-index chain to
#      reconstruct full /Game/ paths.
#   3. Recursively scan each discovered dependency to catch nested references
#      (material → material function, Niagara system → emitter → module, etc.).

import os
import shutil
import re
import struct
import json
import zipfile
import datetime
import logging
from typing import List, Set, Tuple, Dict, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

UE_MAGIC = 0x9E2A83C1
MAX_SCAN_BYTES = 256 * 1024 * 1024  # read up to 256 MB for byte scanning
MAX_DEPTH = 8  # maximum recursion depth for dependency resolution

# ---------------------------------------------------------------------------
# Byte-scanning for /Game/ references
# ---------------------------------------------------------------------------

# Pattern: /Game/ followed by valid UE package-path characters.
# UE package paths may contain: A-Z a-z 0-9 _ - / . and (rarely) +
_RE_REF = re.compile(rb'/Game/[A-Za-z0-9_/.\-+]+')


def _extract_game_refs(data: bytes) -> Set[str]:
    """Extract all /Game/ package-path references from raw bytes.

    Returns a set of canonical package paths like ``/Game/Folder/Asset``
    (without the ``.Asset`` suffix when it duplicates the leaf name).
    """
    refs = set()
    for m in _RE_REF.finditer(data):
        raw = m.group().decode("ascii", errors="replace")
        raw = raw.rstrip(".")  # trailing dot
        # Normalise ``/Game/Folder/Asset.Asset`` → ``/Game/Folder/Asset``
        if "." in raw:
            parts = raw.rsplit(".", 1)
            parent, leaf = parts
            if leaf and parent.endswith("/" + leaf):
                raw = parent
            elif leaf and parent == leaf:
                raw = parent
        # Discard obviously non-FX engine paths and short garbage
        if (len(raw) > 6
                and not raw.startswith("/Game/Engine")
                and not raw.startswith("/Game/Media/")):
            refs.add(raw)
    return refs


# ---------------------------------------------------------------------------
# Binary import-table parser (version-aware)
# ---------------------------------------------------------------------------

# FPackageFileSummary: we try several offset tables and keep the one that
# produces sensible results.
_OFFSET_CANDIDATES = [
    # (name_count_off, name_off, import_count_off, import_off)
    ("UE4.25-27",  (40, 44, 104, 108)),
    ("UE4.25-adj", (40, 44, 140, 144)),
    ("UE5-early",  (44, 48, 168, 172)),
    ("UE5-mid",    (44, 48, 176, 180)),
    ("UE5-late",   (44, 48, 184, 188)),
    ("UE5-wide",   (48, 52, 196, 200)),
    ("UE5-x",      (48, 52, 208, 212)),
]


def _try_read_summary(data: bytes, nc_off: int, no_off: int,
                     ic_off: int, io_off: int):
    """Try to read the four key fields at given offsets.

    Returns (name_count, name_offset, import_count, import_offset)
    or None if any field looks invalid.
    """
    try:
        nc = struct.unpack_from("<I", data, nc_off)[0]
        no = struct.unpack_from("<I", data, no_off)[0]
        ic = struct.unpack_from("<I", data, ic_off)[0]
        io = struct.unpack_from("<I", data, io_off)[0]
    except struct.error:
        return None
    # Sanity checks
    if nc <= 0 or nc > 500000:
        return None
    if no <= 0 or no > len(data):
        return None
    if ic < 0 or ic > 500000:
        return None
    if io < 0 or io > len(data):
        return None
    if ic == 0:  # no imports at all — valid but useless
        return (nc, no, ic, io)
    if io + ic * 24 > len(data) + 1000000:
        return None  # import table would be past EOF
    return (nc, no, ic, io)


def _read_package_header(path: str):
    """Read the FPackageFileSummary and return key fields.

    Returns dict with keys: magic, legacy_version, name_count, name_offset,
    import_count, import_offset.
    Returns None if the file is not a valid .uasset.
    """
    try:
        with open(path, "rb") as fh:
            head = fh.read(4096)
    except Exception:
        return None

    if len(head) < 12:
        return None
    magic = struct.unpack_from("<I", head, 0)[0]
    if magic != UE_MAGIC:
        return None
    legacy_ver = struct.unpack_from("<I", head, 4)[0]

    # Try each offset candidate
    best = None
    for label, (nc_off, no_off, ic_off, io_off) in _OFFSET_CANDIDATES:
        result = _try_read_summary(head, nc_off, no_off, ic_off, io_off)
        if result:
            best = result
            break

    if best is None:
        return None

    nc, no, ic, io = best
    return {
        "magic": magic,
        "legacy_version": legacy_ver,
        "name_count": nc,
        "name_offset": no,
        "import_count": ic,
        "import_offset": io,
    }


def _read_names(path: str, header: dict) -> List[str]:
    """Read the name table from a .uasset file.

    Handles both UE4 (ANSI) and UE5 (potentially wide) FNameEntry formats.
    """
    n_count = header.get("name_count", 0)
    n_off = header.get("name_offset", 0)
    if n_count <= 0 or n_off <= 0:
        return []

    try:
        with open(path, "rb") as fh:
            fh.seek(0)
            data = fh.read(min(os.path.getsize(path), MAX_SCAN_BYTES))
    except Exception:
        return []

    names = []
    pos = n_off
    for _ in range(n_count):
        if pos + 8 > len(data):
            break
        # FNameEntry header: uint32 Flags, uint32 LenField
        flags = struct.unpack_from("<I", data, pos)[0]
        length_field = struct.unpack_from("<I", data, pos + 4)[0]
        length = length_field & 0x3FFFFFFF  # lower 30 bits = actual length
        wide = bool(flags & 0x1)
        if length == 0:
            names.append("")
            pos += 12  # header + 4-byte null
            continue
        if wide:
            start = pos + 8
            raw = data[start:start + length * 2]
            name = raw.decode("utf-16-le", errors="replace").rstrip("\0")
            pos = start + length * 2 + 2  # null wchar
        else:
            start = pos + 8
            raw = data[start:start + length]
            name = raw.decode("ascii", errors="replace").rstrip("\0")
            pos = start + length + 1  # null byte
        names.append(name)
    return names


def _resolve_import_refs(path: str) -> Set[str]:
    """Parse the import table and reconstruct /Game/ package paths.

    Follows the OuterIndex chain to build the full path for each import
    that originates from /Game/ (rather than /Engine/).
    """
    header = _read_package_header(path)
    if header is None or header["import_count"] <= 0:
        return set()

    names = _read_names(path, header)
    if not names:
        return set()

    ic = header["import_count"]
    io = header["import_offset"]

    try:
        with open(path, "rb") as fh:
            fh.seek(0)
            data = fh.read(min(os.path.getsize(path), MAX_SCAN_BYTES))
    except Exception:
        return set()

    # Read all import entries
    # Each FObjectImport varies in size by UE version (20–24 bytes typically).
    # We use a fixed stride of 24 bytes (generous for both UE4/5) and detect
    # the actual stride by looking for valid outer-index patterns.
    entries = []
    # Try shorter strides first
    for stride in (20, 24, 28):
        pos = io
        ok = True
        entries.clear()
        for _ in range(ic):
            if pos + stride > len(data):
                ok = False
                break
            try:
                raw = data[pos:pos + stride]
                class_pkg = struct.unpack_from("<i", raw, 0)[0]
                class_name = struct.unpack_from("<i", raw, 4)[0]
                outer_idx = struct.unpack_from("<i", raw, 8)[0]
                obj_name_idx = struct.unpack_from("<I", raw, 12)[0]
                obj_name_num = struct.unpack_from("<I", raw, 16)[0]
            except struct.error:
                ok = False
                break
            # Basic validity: import indices must be negative (<0 means import)
            # and obj_name_idx must be in range
            if obj_name_idx >= len(names):
                ok = False
                break
            entries.append({
                "outer": outer_idx,
                "name_idx": obj_name_idx,
                "name": names[obj_name_idx] if 0 <= obj_name_idx < len(names) else "",
            })
        if ok and len(entries) == ic:
            break

    if not entries:
        return set()

    # Build full import paths by following the OuterIndex chain.
    # In the import table, outer_idx is negative: -1 means the package root,
    # -2 means entry #0 in the import table, -3 means entry #1, etc.
    # (outer_idx = -(index + 2))
    def _full_path(entry_idx):
        parts = []
        cur = entry_idx
        visited = set()
        while cur >= 0 and cur < len(entries):
            if cur in visited:
                break
            visited.add(cur)
            e = entries[cur]
            name = e["name"]
            if not name:
                break
            parts.append(name)
            o = e["outer"]
            if o >= -1:  # -1 = top-level (package root), stop
                break
            cur = -(o + 2)  # convert negative index to list index
        parts.reverse()
        return "/" + "/".join(parts) if parts else ""

    refs = set()
    for i, e in enumerate(entries):
        path_str = _full_path(i)
        if path_str.startswith("/Game/") and len(path_str) > 6:
            refs.add(path_str)

    return refs


# ---------------------------------------------------------------------------
# Public API: dependency collection (recursive)
# ---------------------------------------------------------------------------


def find_asset_refs(path: str) -> Set[str]:
    """Find all /Game/ asset references in a .uasset file.

    Combines:
      1. Byte-scanning for contiguous ``/Game/...`` byte patterns.
      2. Binary import-table parsing with outer-index chain resolution.

    Returns a deduplicated set of canonical package paths
    (e.g. ``/Game/FX/NS_Fire``).
    """
    refs: Set[str] = set()

    # 1) Byte scan (catches FTopLevelAssetPath, FSoftObjectPath, metadata, etc.)
    try:
        with open(path, "rb") as fh:
            size = os.path.getsize(path)
            data = fh.read(min(size, MAX_SCAN_BYTES))
    except Exception:
        data = b""

    if data:
        refs.update(_extract_game_refs(data))

    # 2) Binary import-table parsing (catches references stored as index chains)
    bin_refs = _resolve_import_refs(path)
    refs.update(bin_refs)

    # 3) Deduplicate: if /Game/A/B exists in both, keep one
    return refs


def find_content_dir(file_path: str) -> Tuple[str, str]:
    """Walk up from *file_path* looking for a 'Content' parent directory.

    Returns (content_dir, relative_path) if found, or (None, basename)
    if no 'Content' ancestor is found.
    """
    cur = os.path.dirname(os.path.abspath(file_path))
    for _ in range(20):
        parent = os.path.dirname(cur)
        if os.path.basename(cur).lower() == "content":
            rel = os.path.relpath(file_path, cur)
            return cur, rel
        if parent == cur:
            break
        cur = parent
    return None, os.path.basename(file_path)


def _related_files(uasset_path: str) -> List[str]:
    """Return the .uasset plus its sibling chunk files."""
    base = os.path.splitext(uasset_path)[0]
    out = [uasset_path]
    for ext in (".uexp", ".ubulk", ".upayload", ".ufont"):
        sib = base + ext
        if os.path.isfile(sib):
            out.append(sib)
    return out


def collect_deps_recursive(main_path: str,
                           content_dirs: List[str],
                           visited: Set[str] = None,
                           depth: int = 0) -> Set[str]:
    """Recursively collect all dependency .uasset files.

    Scans *main_path* for references, resolves each to a .uasset on disk,
    then recurses into newly-found dependencies up to *MAX_DEPTH* levels.

    Returns a set of absolute paths to dependency .uasset files (the main
    file itself is **excluded**).
    """
    if visited is None:
        visited = set()
    if depth > MAX_DEPTH or main_path in visited:
        return set()

    visited.add(main_path)
    direct_deps: Set[str] = set()

    refs = find_asset_refs(main_path)
    for ref in refs:
        if not ref.startswith("/Game/"):
            continue
        rel = ref[6:] + ".uasset"
        for cd in content_dirs:
            candidate = os.path.normpath(os.path.join(cd, rel))
            if os.path.isfile(candidate) and candidate not in visited:
                direct_deps.add(candidate)
                break

    # Recurse into each newly found dependency
    deeper: Set[str] = set()
    for dep in direct_deps:
        sub = collect_deps_recursive(dep, content_dirs, visited, depth + 1)
        deeper.update(sub)

    return direct_deps | deeper


def export_to_ue_project(assets: List,
                          source_roots: List[str],
                          target_content_dir: str,
                          progress_callback=None,
                          log_callback=None) -> int:
    """Export a list of assets (FXAsset objects) to a UE project's Content folder.

    For each asset:
      1. Recursively resolves ALL /Game/ dependencies up to 8 levels deep.
      2. Copies the main .uasset + sibling chunks + all dependencies to
         *target_content_dir*, preserving the relative directory structure
         under the nearest 'Content' parent.
      3. Logs all skipped dependencies for debugging.

    Returns the number of files successfully copied.
    """
    # Build the set of source Content directories for dependency search.
    content_dirs: Set[str] = set()
    for a in assets:
        cd, _ = find_content_dir(a.source_path)
        if cd:
            content_dirs.add(cd)
    for r in source_roots:
        abspath = os.path.abspath(r)
        if os.path.isdir(abspath):
            content_dirs.add(abspath)
    content_dirs_list = list(content_dirs)

    if log_callback:
        log_callback(f"源 Content 目录: {content_dirs_list}")

    total = 0

    for idx, asset in enumerate(assets):
        src = asset.source_path
        if not os.path.isfile(src):
            msg = f"源文件缺失: {asset.name}"
            if log_callback:
                log_callback(msg)
            continue

        # Log the references found in this asset
        refs = find_asset_refs(src)
        if log_callback:
            log_callback(f"{asset.name}: 发现 {len(refs)} 个引用")
            for r in sorted(refs):
                log_callback(f"  引用: {r}")

        # 1) Determine target directory for the main asset
        cd, rel = find_content_dir(src)
        if cd:
            target_dir = os.path.normpath(os.path.join(
                target_content_dir, os.path.dirname(rel)))
        else:
            target_dir = target_content_dir

        # 2) Collect ALL dependencies (recursive)
        all_deps = collect_deps_recursive(src, content_dirs_list)
        if log_callback:
            log_callback(f"{asset.name}: 共扫描到 {len(all_deps)} 个依赖文件")

        # 3) Collect all files to copy: main + siblings + deps + deps' siblings
        all_src_files: Set[str] = set(_related_files(src))

        for dep in all_deps:
            for f in _related_files(dep):
                if os.path.isfile(f):
                    all_src_files.add(f)

        # 4) Copy every file to the right target location
        os.makedirs(target_dir, exist_ok=True)
        for f in sorted(all_src_files):
            try:
                f_cd, f_rel = find_content_dir(f)
                if f_cd and f_rel:
                    target_path = os.path.normpath(
                        os.path.join(target_content_dir, f_rel))
                else:
                    target_path = os.path.normpath(
                        os.path.join(target_dir, os.path.basename(f)))
                os.makedirs(os.path.dirname(target_path), exist_ok=True)
                shutil.copy2(f, target_path)
                total += 1
            except Exception as e:
                msg = f"复制失败: {os.path.basename(f)} — {e}"
                if log_callback:
                    log_callback(msg)

        msg = f"已导出 {asset.name} ({len(all_deps)} 个依赖, 共 {len(all_src_files)} 个文件)"
        if log_callback:
            log_callback(msg)
        if progress_callback:
            progress_callback(idx + 1, len(assets), asset.name)

    return total


def export_to_fxpack(assets: List, out_path: str,
                      library_dir: Optional[str] = None,
                      progress_callback=None, log_callback=None) -> int:
    """Package one or more FXAsset objects into a self-contained .fxpack.

    The archive contains ``manifest.json`` plus ``assets/`` (the main
    .uasset, its sibling chunk files, and ALL recursively-resolved
    dependencies) and ``thumbs/`` (each asset's embedded thumbnail when
    present). File names are flattened (de-duplicated by basename) so the
    matching ``_import_from_fxpack`` can restore them into the library
    directory unchanged.

    Returns the number of top-level assets packaged.
    """
    # Content directories used to resolve /Game/ dependencies.
    content_dirs: Set[str] = set()
    for a in assets:
        cd, _ = find_content_dir(a.source_path)
        if cd:
            content_dirs.add(cd)
    content_dirs_list = list(content_dirs)

    asset_files: Dict[str, str] = {}   # stored_name -> src_path
    thumb_files: Dict[str, str] = {}    # stored_name -> src_path
    used: Dict[str, int] = {}

    def _add_file(src: str, target: Dict[str, str]) -> str:
        bn = os.path.basename(src)
        if bn in target and target[bn] == src:
            return bn
        if bn in target and target[bn] != src:
            n = 2
            root, ext = os.path.splitext(bn)
            while True:
                cand = "%s_%d%s" % (root, n, ext)
                if cand not in target or target[cand] == src:
                    target[cand] = src
                    return cand
                n += 1
        target[bn] = src
        return bn

    manifest_assets = []
    packaged = 0
    for idx, asset in enumerate(assets):
        src = asset.source_path
        if not os.path.isfile(src):
            if log_callback:
                log_callback("跳过（源文件缺失）：%s" % asset.name)
            continue

        # main file + siblings
        files = list(_related_files(src))
        # recursively resolved dependencies
        deps = collect_deps_recursive(src, content_dirs_list)
        for d in sorted(deps):
            for f in _related_files(d):
                if os.path.isfile(f):
                    files.append(f)

        main_sn = _add_file(src, asset_files)
        dep_names = []
        for f in files:
            if f == src:
                continue
            sn = _add_file(f, asset_files)
            if sn not in dep_names:
                dep_names.append(sn)

        # thumbnail
        thumb_sn = ""
        tp = getattr(asset, "thumb_path", None)
        if tp and os.path.isfile(tp):
            thumb_sn = _add_file(tp, thumb_files)

        entry = {
            "name": asset.name,
            "type": asset.type,
            "class_name": getattr(asset, "class_name", ""),
            "file": main_sn,
            "thumb": thumb_sn,
            "tags": getattr(asset, "tags", ""),
            "rating": getattr(asset, "rating", 0),
            "note": getattr(asset, "note", ""),
            "size": getattr(asset, "size", 0),
            "imported_at": getattr(asset, "imported_at", ""),
            "source": "fxpack",
            "deps": dep_names,
        }
        manifest_assets.append(entry)
        packaged += 1
        if log_callback:
            log_callback("%s: 打包 %d 个文件，%d 个依赖"
                        % (asset.name, len(files), len(dep_names)))
        if progress_callback:
            progress_callback(idx + 1, len(assets), asset.name)

    manifest = {
        "version": 1,
        "created_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "assets": manifest_assets,
    }

    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("manifest.json",
                     json.dumps(manifest, ensure_ascii=False, indent=2))
        for sn, sp in asset_files.items():
            if sp:
                z.write(sp, "assets/" + sn)
        for sn, sp in thumb_files.items():
            if sp:
                z.write(sp, "thumbs/" + sn)
    return packaged


def export_to_fxpack(assets: List, out_path: str,
                      library_dir: Optional[str] = None,
                      progress_callback=None, log_callback=None) -> int:
    """Package one or more FXAsset objects into a self-contained .fxpack.

    The archive contains ``manifest.json`` plus ``assets/`` (the main
    .uasset, its sibling chunk files, and ALL recursively-resolved
    dependencies) and ``thumbs/`` (each asset's embedded thumbnail when
    present). File names are flattened (de-duplicated by basename) so the
    matching ``_import_from_fxpack`` can restore them into the library
    directory unchanged.

    Returns the number of top-level assets packaged.
    """
    # Content directories used to resolve /Game/ dependencies.
    content_dirs: Set[str] = set()
    for a in assets:
        cd, _ = find_content_dir(a.source_path)
        if cd:
            content_dirs.add(cd)
    content_dirs_list = list(content_dirs)

    asset_files: Dict[str, str] = {}   # stored_name -> src_path
    thumb_files: Dict[str, str] = {}    # stored_name -> src_path
    used: Dict[str, int] = {}

    def _add_file(src: str, target: Dict[str, str]) -> str:
        bn = os.path.basename(src)
        if bn in target and target[bn] == src:
            return bn
        if bn in target and target[bn] != src:
            n = 2
            root, ext = os.path.splitext(bn)
            while True:
                cand = "%s_%d%s" % (root, n, ext)
                if cand not in target or target[cand] == src:
                    target[cand] = src
                    return cand
                n += 1
        target[bn] = src
        return bn

    manifest_assets = []
    packaged = 0
    for idx, asset in enumerate(assets):
        src = asset.source_path
        if not os.path.isfile(src):
            if log_callback:
                log_callback("跳过（源文件缺失）：%s" % asset.name)
            continue

        # main file + siblings
        files = list(_related_files(src))
        # recursively resolved dependencies
        deps = collect_deps_recursive(src, content_dirs_list)
        for d in sorted(deps):
            for f in _related_files(d):
                if os.path.isfile(f):
                    files.append(f)

        main_sn = _add_file(src, asset_files)
        dep_names = []
        for f in files:
            if f == src:
                continue
            sn = _add_file(f, asset_files)
            if sn not in dep_names:
                dep_names.append(sn)

        # thumbnail
        thumb_sn = ""
        tp = getattr(asset, "thumb_path", None)
        if tp and os.path.isfile(tp):
            thumb_sn = _add_file(tp, thumb_files)

        entry = {
            "name": asset.name,
            "type": asset.type,
            "class_name": getattr(asset, "class_name", ""),
            "file": main_sn,
            "thumb": thumb_sn,
            "tags": getattr(asset, "tags", ""),
            "rating": getattr(asset, "rating", 0),
            "note": getattr(asset, "note", ""),
            "size": getattr(asset, "size", 0),
            "imported_at": getattr(asset, "imported_at", ""),
            "source": "fxpack",
            "deps": dep_names,
        }
        manifest_assets.append(entry)
        packaged += 1
        if log_callback:
            log_callback("%s: 打包 %d 个文件，%d 个依赖"
                        % (asset.name, len(files), len(dep_names)))
        if progress_callback:
            progress_callback(idx + 1, len(assets), asset.name)

    manifest = {
        "version": 1,
        "created_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "assets": manifest_assets,
    }

    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("manifest.json",
                     json.dumps(manifest, ensure_ascii=False, indent=2))
        for sn, sp in asset_files.items():
            if sp:
                z.write(sp, "assets/" + sn)
        for sn, sp in thumb_files.items():
            if sp:
                z.write(sp, "thumbs/" + sn)
    return packaged
