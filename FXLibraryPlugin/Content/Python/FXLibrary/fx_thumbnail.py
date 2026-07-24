import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

import unreal
import fx_config
import fx_common


def main():
    selected = unreal.EditorUtilityLibrary.get_selected_assets()
    if not selected:
        unreal.EditorDialog.show_message(
            "FX Library",
            "No asset selected. Select a Niagara/Cascade asset in the Content Browser first.",
            unreal.AppMsgType.OK)
        return

    out_dir = fx_config.EXPORT_ROOT + "thumbs/"
    fx_common.ensure_dir(out_dir)

    for asset in selected:
        out_path = os.path.join(out_dir, asset.get_name() + ".png")
        ok = unreal.FXLibraryBPLibrary.export_asset_thumbnail(asset, out_path)
        if ok:
            unreal.log("[FXLibrary] thumbnail OK: %s -> %s" % (asset.get_name(), out_path))
        else:
            unreal.log_warning(
                "[FXLibrary] thumbnail FAILED for %s (open it once in the Content Browser to generate a thumbnail, then retry)."
                % asset.get_name())


if __name__ == "__main__":
    main()
