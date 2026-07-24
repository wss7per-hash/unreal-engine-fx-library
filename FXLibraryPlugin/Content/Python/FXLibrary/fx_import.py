import sys
import os
import json
import zipfile
import shutil
sys.path.insert(0, os.path.dirname(__file__))

import unreal
import fx_config
import fx_common


def _find_fxpack():
    """Resolve the .fxpack to import.

    Priority:
      1. An explicit path passed on the command line:  py fx_import.py "C:/path/to/x.fxpack"
      2. The most recently modified .fxpack found in the export root (where exports land).
    UE 5.x Python has no file-open dialog binding, so we use the export folder as the
    default drop location for round-trip testing.
    """
    if len(sys.argv) > 1:
        p = sys.argv[1]
        if os.path.isfile(p):
            return p
        unreal.log_warning("[FXLibrary] given path is not a file: %s" % p)

    root = fx_config.EXPORT_ROOT
    if not os.path.isdir(root):
        return None
    candidates = []
    for fn in os.listdir(root):
        if fn.lower().endswith(".fxpack"):
            candidates.append(os.path.join(root, fn))
    if not candidates:
        return None
    # Newest first.
    candidates.sort(key=lambda f: os.path.getmtime(f), reverse=True)
    return candidates[0]


def main():
    fxpack = _find_fxpack()
    if not fxpack:
        msg = ("No .fxpack found.\n\n"
               "To import:\n"
               "  1) Export a FX asset first (it lands in Saved/FXLibrary/), or\n"
               "  2) Run from the Python console:  py \".../fx_import.py\" \"C:/path/to/file.fxpack\"")
        unreal.EditorDialog.show_message("FX Library", msg, unreal.AppMsgType.OK)
        return

    tmp = os.path.join(fx_config.EXPORT_ROOT, "import_tmp")
    fx_common.ensure_dir(tmp)
    # Clean previous extraction to avoid stale files.
    if os.path.isdir(tmp):
        shutil.rmtree(tmp)
    fx_common.ensure_dir(tmp)

    with zipfile.ZipFile(fxpack, "r") as z:
        z.extractall(tmp)

    manifest_path = os.path.join(tmp, "manifest.json")
    if not os.path.exists(manifest_path):
        unreal.EditorDialog.show_message("FX Library", "Invalid .fxpack (no manifest.json).", unreal.AppMsgType.OK)
        return

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
            skipped.append(dst)
            continue
        shutil.copy2(src, dst)
        imported.append(pkg + "." + aname)

    # Re-scan so the Asset Registry picks up the new files.
    ar = fx_common.get_asset_registry()
    ar.scan_paths_synchronous([content_dir])

    msg = "Imported %d asset(s) into:\n%s" % (len(imported), content_dir)
    if skipped:
        msg += "\n\nSkipped %d existing asset(s) (already present)." % len(skipped)
    unreal.log("[FXLibrary] " + msg)
    unreal.EditorDialog.show_message("FX Library", msg, unreal.AppMsgType.OK)


if __name__ == "__main__":
    main()
