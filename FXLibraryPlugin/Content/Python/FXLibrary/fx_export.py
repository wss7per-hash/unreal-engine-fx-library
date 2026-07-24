import sys
import os
import time
import json
import shutil
import zipfile
sys.path.insert(0, os.path.dirname(__file__))

import unreal
import fx_config
import fx_common


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


def main():
    selected = unreal.EditorUtilityLibrary.get_selected_assets()
    roots = [a for a in selected if fx_common.is_fx_object(a)]
    if not roots:
        unreal.EditorDialog.show_message(
            "FX Library",
            "Select a Niagara/Cascade asset in the Content Browser to export.",
            unreal.AppMsgType.OK)
        return
    root = roots[0]

    ar = fx_common.get_asset_registry()
    root_path = fx_common.asset_object_path(root)
    deps = collect_dependencies(root_path)
    all_paths = [root_path] + sorted(deps)

    # Prepare a temp working directory.
    stamp = str(int(time.time()))
    work = os.path.join(fx_config.EXPORT_ROOT, "tmp", stamp)
    assets_dir = os.path.join(work, "assets")
    preview_dir = os.path.join(work, "preview")
    fx_common.ensure_dir(assets_dir)
    fx_common.ensure_dir(preview_dir)

    class_name = root.get_class().get_name()
    fx_type = "Niagara" if "Niagara" in class_name else "Cascade"

    manifest = {
        "name": root.get_name(),
        "type": fx_type,
        "engineVersion": fx_config.ENGINE_VERSION,
        "rootObjectPath": root_path,
        "dependencies": [],
        "assets": [],
    }
    deps_graph = {"root": root_path, "edges": []}

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
        if obj_path != root_path:
            manifest["dependencies"].append(obj_path)
            deps_graph["edges"].append({"from": root_path, "to": obj_path})

    # Thumbnail (Tier 1: engine-builtin, exported via C++ helper).
    thumb_out = os.path.join(preview_dir, "thumb.png")
    ok = unreal.FXLibraryBPLibrary.export_asset_thumbnail(root, thumb_out)
    if not ok:
        unreal.log_warning("[FXLibrary] thumbnail export failed (open asset once to generate it).")

    with open(os.path.join(work, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
    with open(os.path.join(work, "deps_graph.json"), "w", encoding="utf-8") as f:
        json.dump(deps_graph, f, indent=2, ensure_ascii=False)

    fx_common.ensure_dir(fx_config.EXPORT_ROOT)
    fxpack = os.path.join(fx_config.EXPORT_ROOT, manifest["name"] + ".fxpack")
    if os.path.exists(fxpack):
        os.remove(fxpack)
    with zipfile.ZipFile(fxpack, "w", zipfile.ZIP_DEFLATED) as z:
        for root_dir, _, files in os.walk(work):
            for fn in files:
                full = os.path.join(root_dir, fn)
                z.write(full, os.path.relpath(full, work))

    msg = "Exported %d asset(s) (1 root + %d deps) ->\n%s" % (
        len(manifest["assets"]), len(manifest["dependencies"]), fxpack)
    unreal.log("[FXLibrary] " + msg)
    unreal.EditorDialog.show_message("FX Library", msg, unreal.AppMsgType.OK)


if __name__ == "__main__":
    main()
