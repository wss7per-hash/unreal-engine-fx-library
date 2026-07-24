# fx_common.py -- shared helpers for the UE headless bridge.
# Runs INSIDE Unreal (imports `unreal`). No UI / selection dependency.

import os
import unreal
import fx_config


def get_asset_registry():
    # unreal.AssetRegistry is abstract; the concrete instance is obtained via the helpers class.
    return unreal.AssetRegistryHelpers.get_asset_registry()


def ensure_dir(path):
    """Create a directory (and parents) if it does not exist."""
    os.makedirs(str(path), exist_ok=True)


def _assets_by_class(ar, class_name):
    """Get assets of a class. Tries TopLevelAssetPath first, falls back to the
    plain class-name string (API shape differs across UE 5.x)."""
    package, asset = fx_config.CLASS_PATHS[class_name]
    try:
        tl = unreal.TopLevelAssetPath(package, asset)
        return ar.get_assets_by_class(tl)
    except Exception:
        try:
            return ar.get_assets_by_class(class_name)
        except Exception as e:
            unreal.log_warning("[FXLibrary] get_assets_by_class failed for %s: %s" % (class_name, e))
            return []


def asset_data_class_name(ad):
    if ad is None:
        return None
    if hasattr(ad, "asset_class_path") and ad.asset_class_path is not None:
        return str(ad.asset_class_path.asset_name)
    return str(ad.asset_class)


def asset_data_object_path(ad):
    """Full canonical object path: /Game/Folder/AssetName.AssetName

    In some UE 5.x versions `str(ad.object_path)` returns an ambiguous dotted
    format (e.g. /Game.AssetName) that `EditorAssetLibrary.load_asset` rejects
    for assets nested in sub-folders. We always build the package_path + asset_name
    form ourselves, which the editor recognises reliably."""
    if ad is None:
        return None
    pkg = str(ad.package_path)
    aname = str(ad.asset_name)
    return pkg + "." + aname


def is_fx_asset_data(ad):
    cls = asset_data_class_name(ad)
    return cls in (fx_config.NIAGARA_CLASS, fx_config.CASCADE_CLASS)


def get_all_fx_asset_data():
    ar = get_asset_registry()
    out = []
    for cls in (fx_config.NIAGARA_CLASS, fx_config.CASCADE_CLASS):
        for a in _assets_by_class(ar, cls):
            out.append(a)
    return out


def get_dependencies(object_path):
    """Return a list of object-path dependencies for an asset.
    Handles both the (bool, list) and list return shapes of get_dependencies
    across UE 5.x, and falls back to the options-overload if needed."""
    ar = get_asset_registry()
    try:
        res = ar.get_dependencies(object_path)
    except TypeError:
        opts = unreal.AssetRegistryDependencyOptions()
        opts.include_hard_package_references = True
        opts.include_soft_package_references = True
        opts.include_searchable_name_references = False
        opts.include_soft_management_references = False
        opts.include_none = False
        res = ar.get_dependencies(object_path, opts)

    if isinstance(res, tuple):
        return list(res[1]) if len(res) > 1 else []
    return list(res) if res else []


def is_engine_or_plugin_asset(object_path):
    """Skip engine-builtin and /Script assets; we only bundle project content."""
    p = str(object_path)
    return p.startswith("/Engine/") or p.startswith("/Script/") or p.startswith("/Plugin/")


def package_to_content_file(package_path, asset_name):
    """Map a /Game/... package path to its .uasset file on disk.
    NOTE: only /Game assets are supported in this scaffold (project Content dir)."""
    content_dir = unreal.Paths.project_content_dir()
    rel = str(package_path).replace("/Game/", "", 1).lstrip("/")
    return str(unreal.Paths.combine(content_dir, rel, asset_name + ".uasset"))


def try_scan():
    """Force a synchronous asset scan so the registry is up to date (important headless)."""
    try:
        ar = get_asset_registry()
        if hasattr(ar, "scan_paths_synchronous"):
            ar.scan_paths_synchronous([unreal.Paths.project_content_dir()])
        if hasattr(ar, "wait_for_data"):
            ar.wait_for_data()
    except Exception as e:
        unreal.log_warning("[FXLibrary] try_scan warning: %s" % e)
