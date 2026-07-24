# fx_health.py -- headless bridge: scan the project's FX assets for problems.
# Runs INSIDE Unreal. Run via fx_runner (command "health").

import os
import sys
import hashlib
sys.path.insert(0, os.path.dirname(__file__))

import unreal
import fx_common


def _file_md5(path):
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def run_health(params):
    """params: {} -> data: {"issues": [...], "assets": N}"""
    fx_common.try_scan()
    ar = fx_common.get_asset_registry()
    issues = []

    assets = fx_common.get_all_fx_asset_data()
    seen_hash = {}

    for ad in assets:
        obj_path = fx_common.asset_data_object_path(ad)
        name = str(ad.asset_name)
        pkg = str(ad.package_path)

        # 1) Missing / unbundled dependencies (asset references a missing file).
        for dep in fx_common.get_dependencies(obj_path):
            if fx_common.is_engine_or_plugin_asset(dep):
                continue
            dep_ad = ar.get_asset_by_object_path(dep)
            if dep_ad is None:
                issues.append({
                    "severity": "error",
                    "asset": name,
                    "kind": "missing_dependency",
                    "detail": "depends on %s which is not found in this project" % dep,
                })

        # 2) Duplicate detection by file hash.
        src = fx_common.package_to_content_file(pkg, name)
        if os.path.exists(src):
            digest = _file_md5(src)
            if digest in seen_hash:
                issues.append({
                    "severity": "warning",
                    "asset": name,
                    "kind": "duplicate",
                    "detail": "identical file (md5) to %s" % seen_hash[digest],
                })
            else:
                seen_hash[digest] = name

    return {"issues": issues, "assets": len(assets)}
