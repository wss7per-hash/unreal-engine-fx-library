# fx_list.py -- headless bridge: list Niagara/Cascade assets in a project.
# Run via fx_runner (command "list"). Reads nothing from selection; returns JSON.

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

import unreal
import fx_common


def run_list(params):
    """params: {} -> data: {"assets": [...], "count": N}"""
    fx_common.try_scan()
    assets = []
    for ad in fx_common.get_all_fx_asset_data():
        obj_path = fx_common.asset_data_object_path(ad)
        name = str(ad.asset_name)
        pkg = str(ad.package_path)
        cls = fx_common.asset_data_class_name(ad)
        fx_type = "Niagara" if cls == fx_common.fx_config.NIAGARA_CLASS else "Cascade"
        assets.append({
            "objectPath": obj_path,
            "name": name,
            "packagePath": pkg,
            "className": cls,
            "type": fx_type,
        })
        unreal.log("[FXLibrary] list: %s (%s) %s" % (name, fx_type, obj_path))
    return {"assets": assets, "count": len(assets)}
