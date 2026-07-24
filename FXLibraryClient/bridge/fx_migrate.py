# fx_migrate.py -- headless bridge: import a raw Content folder (UE migrate-style).
# Runs INSIDE Unreal. Run via fx_runner (command "import_content_folder").
#
# Behaviour (matches the user's request = "UE migrate into the connected project"):
#   1. Recursively copy every asset file from srcFolder into the current project's
#      Content dir, preserving relative paths (so internal cross-references stay valid).
#   2. Re-scan the asset registry so the new files are registered.
#   3. Enumerate Niagara / Cascade FX assets (auto-recognition).
#   4. In the SAME UE session, render a static thumbnail for each recognised FX asset.
# The whole pipeline is one headless UE launch -> the client gets a single result.

import os
import sys
import shutil
sys.path.insert(0, os.path.dirname(__file__))

import unreal
import fx_common
import fx_config


# Directories we never copy (engine / OS cruft that may live under a project root).
_SKIP_DIRS = {
    "Intermediate", "Saved", "Binaries", "DerivedDataCache",
    ".git", ".svn", ".vs", "__pycache__", "Config", "Source", "Plugins",
}
# File extensions we treat as importable assets (mirrors what UE migrate carries).
_ASSET_EXTS = (".uasset", ".umap", ".uexp", ".ubulk")


def _is_asset_file(name):
    return name.lower().endswith(_ASSET_EXTS)


def run_import_content_folder(params):
    """params: {
        "srcFolder": str,
        "destPackage": str (optional, default "/Game"),
        "generateThumbs": bool (optional, default True),
        "thumbSize": int (optional, default 256),
        "thumbOutDir": str (optional),
    }
    -> data: {
        "copied": [rel paths], "copiedCount": int, "skippedCount": int,
        "assets": [{objectPath,name,packagePath,className,type}],
        "niagara": int, "cascade": int,
        "thumbnails": [{objectPath,available,path}], "thumbAvailable": int,
    }
    """
    src = params.get("srcFolder")
    if not src or not os.path.isdir(src):
        raise RuntimeError("import_content_folder requires a valid 'srcFolder'")

    dest_package = params.get("destPackage") or "/Game"
    if not dest_package.startswith("/Game"):
        dest_package = "/Game/" + dest_package.lstrip("/")

    generate_thumbs = bool(params.get("generateThumbs", True))
    thumb_size = int(params.get("thumbSize", 256))
    thumb_out = params.get("thumbOutDir") or (fx_config.default_export_root() + "thumbs")

    content_dir = unreal.Paths.project_content_dir()
    # Map the destination package to a disk directory under Content.
    rel = dest_package.replace("/Game/", "", 1).lstrip("/")
    dest_root = str(unreal.Paths.combine(content_dir, rel)) if rel else str(content_dir)
    fx_common.ensure_dir(dest_root)

    copied = []
    skipped = []
    for root, dirs, files in os.walk(src):
        # Prune junk dirs in place so os.walk never descends into them.
        dirs[:] = [d for d in dirs if d not in _SKIP_DIRS]
        for fn in files:
            if not _is_asset_file(fn):
                continue
            full = os.path.join(root, fn)
            rel_path = os.path.relpath(full, src)
            dst = os.path.join(dest_root, rel_path)
            fx_common.ensure_dir(os.path.dirname(dst))
            if os.path.exists(dst):
                skipped.append(rel_path)
                continue
            shutil.copy2(full, dst)
            copied.append(rel_path)

    unreal.log("[FXLibrary] migrate: copied %d, skipped %d existing" %
               (len(copied), len(skipped)))

    # Re-scan so the Asset Registry picks up the new files.
    ar = fx_common.get_asset_registry()
    try:
        ar.scan_paths_synchronous([dest_root])
    except Exception as e:
        unreal.log_warning("[FXLibrary] re-scan warning: %s" % e)

    # Enumerate Niagara / Cascade FX assets (auto-recognition).
    fx_assets = []
    niagara = 0
    cascade = 0
    for ad in fx_common.get_all_fx_asset_data():
        cls = fx_common.asset_data_class_name(ad)
        if cls == fx_config.NIAGARA_CLASS:
            fx_type = "Niagara"; niagara += 1
        elif cls == fx_config.CASCADE_CLASS:
            fx_type = "Cascade"; cascade += 1
        else:
            continue
        fx_assets.append({
            "objectPath": fx_common.asset_data_object_path(ad),
            "name": str(ad.asset_name),
            "packagePath": str(ad.package_path),
            "className": cls,
            "type": fx_type,
        })

    # Render thumbnails for every recognised FX asset, in this same session.
    thumbnails = []
    if generate_thumbs and fx_assets:
        import fx_thumbnail
        fx_common.ensure_dir(thumb_out)
        for a in fx_assets:
            op = a["objectPath"]
            asset = unreal.EditorAssetLibrary.load_asset(op)
            if asset is None:
                unreal.log_warning("[FXLibrary] migrate thumbnail: cannot load %s" % op)
                thumbnails.append({"objectPath": op, "available": False, "path": None})
                continue
            out_path = os.path.join(thumb_out, a["name"] + ".png")
            ok = fx_thumbnail.try_render(asset, out_path, thumb_size)
            thumbnails.append({"objectPath": op, "available": ok, "path": out_path if ok else None})

    return {
        "copied": copied,
        "copiedCount": len(copied),
        "skippedCount": len(skipped),
        "assets": fx_assets,
        "niagara": niagara,
        "cascade": cascade,
        "thumbnails": thumbnails,
        "thumbAvailable": sum(1 for t in thumbnails if t.get("available")),
    }
