# fx_import.py -- headless bridge: unpack a .fxpack into the current project.
# Runs INSIDE Unreal. Run via fx_runner (command "import").

import os
import sys
import json
import zipfile
import shutil
sys.path.insert(0, os.path.dirname(__file__))

import unreal
import fx_config
import fx_common


def run_import(params):
    """params: {"fxpack": str, "destPackage": str (optional, default /Game/ImportedFX)}
    -> data: {"imported": [...], "skipped": [...], "manifest": {...}}"""
    fxpack = params.get("fxpack")
    if not fxpack or not os.path.isfile(fxpack):
        raise RuntimeError("import requires a valid 'fxpack' path")

    dest_package = params.get("destPackage") or "/Game/ImportedFX"
    # Normalise: dest_package may be like "/Game/ImportedFX" or without leading slash.
    if not dest_package.startswith("/Game"):
        dest_package = "/Game/" + dest_package.lstrip("/")

    tmp = os.path.join(fx_config.default_export_root(), "import_tmp")
    if os.path.isdir(tmp):
        shutil.rmtree(tmp)
    fx_common.ensure_dir(tmp)

    with zipfile.ZipFile(fxpack, "r") as z:
        z.extractall(tmp)

    manifest_path = os.path.join(tmp, "manifest.json")
    if not os.path.exists(manifest_path):
        raise RuntimeError("Invalid .fxpack (no manifest.json)")
    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    assets_dir = os.path.join(tmp, "assets")
    content_dir = unreal.Paths.project_content_dir()

    imported = []
    skipped = []
    for entry in manifest.get("assets", []):
        pkg = entry["package"]
        aname = entry["asset"]
        src = os.path.join(assets_dir, aname + ".uasset")
        if not os.path.exists(src):
            continue
        # Preserve the original package path so internal cross-references stay valid.
        rel = pkg.replace("/Game/", "", 1).lstrip("/")
        dst = str(unreal.Paths.combine(content_dir, rel, aname + ".uasset"))
        dst_dir = os.path.dirname(dst)
        fx_common.ensure_dir(dst_dir)
        if os.path.exists(dst):
            skipped.append(pkg + "." + aname)
            continue
        shutil.copy2(src, dst)
        imported.append(pkg + "." + aname)

    # Re-scan so the Asset Registry picks up the new files.
    ar = fx_common.get_asset_registry()
    try:
        ar.scan_paths_synchronous([content_dir])
    except Exception as e:
        unreal.log_warning("[FXLibrary] re-scan warning: %s" % e)

    shutil.rmtree(tmp, ignore_errors=True)
    unreal.log("[FXLibrary] imported %d asset(s) into %s" % (len(imported), content_dir))
    return {"imported": imported, "skipped": skipped, "manifest": manifest}
