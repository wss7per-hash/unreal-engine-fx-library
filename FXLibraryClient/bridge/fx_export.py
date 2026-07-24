# fx_export.py -- headless bridge: pack an FX asset + its dependencies into a .fxpack.
# Runs INSIDE Unreal. Run via fx_runner (command "export").

import os
import sys
import time
import json
import shutil
import zipfile
sys.path.insert(0, os.path.dirname(__file__))

import unreal
import fx_config
import fx_common
import fx_thumbnail


def collect_dependencies(root_object_path):
    """BFS over recursive dependencies, skipping engine/plugin assets and cycles."""
    visited = set()
    queue = [root_object_path]
    while queue:
        cur = queue.pop()
        if cur in visited:
            continue
        visited.add(cur)
        for dep in fx_common.get_dependencies(cur):
            if fx_common.is_engine_or_plugin_asset(dep):
                continue
            if dep not in visited:
                queue.append(dep)
    visited.discard(root_object_path)
    return visited


def run_export(params):
    """params: {"objectPath": str, "outDir": str (optional)}
    -> data: {"fxpack": str, "assetCount": int, "manifest": {...}}"""
    object_path = params.get("objectPath")
    if not object_path:
        raise RuntimeError("export requires 'objectPath'")

    out_dir = params.get("outDir") or fx_config.default_export_root()
    fx_common.ensure_dir(out_dir)

    asset = unreal.EditorAssetLibrary.load_asset(object_path)
    if asset is None:
        raise RuntimeError("Cannot load asset: %s" % object_path)

    ar = fx_common.get_asset_registry()
    deps = collect_dependencies(object_path)
    all_paths = [object_path] + sorted(deps)

    stamp = str(int(time.time()))
    work = os.path.join(out_dir, "tmp", stamp)
    assets_dir = os.path.join(work, "assets")
    preview_dir = os.path.join(work, "preview")
    fx_common.ensure_dir(assets_dir)
    fx_common.ensure_dir(preview_dir)

    class_name = asset.get_class().get_name()
    fx_type = "Niagara" if "Niagara" in class_name else "Cascade"

    manifest = {
        "name": asset.get_name(),
        "type": fx_type,
        "engineVersion": fx_config.ENGINE_VERSION,
        "rootObjectPath": object_path,
        "dependencies": [],
        "assets": [],
    }
    deps_graph = {"root": object_path, "edges": []}

    for obj_path in all_paths:
        ad = ar.get_asset_by_object_path(obj_path)
        if ad is None:
            unreal.log_warning("[FXLibrary] asset data not found for %s" % obj_path)
            continue
        pkg = str(ad.package_path)
        aname = str(ad.asset_name)
        src = fx_common.package_to_content_file(pkg, aname)
        if not os.path.exists(src):
            unreal.log_warning("[FXLibrary] source file missing (only /Game assets supported): %s" % src)
            continue
        dst = os.path.join(assets_dir, aname + ".uasset")
        shutil.copy2(src, dst)
        manifest["assets"].append({"objectPath": obj_path, "package": pkg, "asset": aname})
        if obj_path != object_path:
            manifest["dependencies"].append(obj_path)
            deps_graph["edges"].append({"from": object_path, "to": obj_path})

    # Thumbnail (best-effort; unavailable -> client shows placeholder / manual).
    thumb_out = os.path.join(preview_dir, "thumb.png")
    thumb_ok = fx_thumbnail.try_render(asset, thumb_out)
    if not thumb_ok:
        unreal.log_warning("[FXLibrary] thumbnail unavailable (open asset once to cache, or set a manual one).")

    with open(os.path.join(work, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
    with open(os.path.join(work, "deps_graph.json"), "w", encoding="utf-8") as f:
        json.dump(deps_graph, f, indent=2, ensure_ascii=False)

    fx_common.ensure_dir(out_dir)
    fxpack = os.path.join(out_dir, manifest["name"] + ".fxpack")
    if os.path.exists(fxpack):
        os.remove(fxpack)
    with zipfile.ZipFile(fxpack, "w", zipfile.ZIP_DEFLATED) as z:
        for root_dir, _, files in os.walk(work):
            for fn in files:
                full = os.path.join(root_dir, fn)
                z.write(full, os.path.relpath(full, work))

    shutil.rmtree(work, ignore_errors=True)
    unreal.log("[FXLibrary] exported %d asset(s) -> %s" % (len(manifest["assets"]), fxpack))
    return {
        "fxpack": fxpack,
        "assetCount": len(manifest["assets"]),
        "dependencyCount": len(manifest["dependencies"]),
        "manifest": manifest,
        "thumbnail": thumb_ok,
    }
