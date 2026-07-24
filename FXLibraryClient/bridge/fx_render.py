# fx_render.py -- headless bridge: render thumbnails for arbitrary local
# .uasset files (hybrid mode). Each file is copied into a temp mount under the
# current project's Content, scanned, rendered, and the temp copy is removed.
#
# Two entry points:
#   * run_render_files()    -> static editor thumbnails (try_render)
#   * run_render_playing()  -> real playing-frame capture (try_render_playing)
#
# params: {"files": [abs .uasset paths], "outDir": str, "size": int}
# -> data: {"thumbnails": [{"source","available","path"}], "count": N}

import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(__file__))

import unreal
import fx_common
import fx_thumbnail


def _related_paths(uasset_path):
    base = os.path.splitext(uasset_path)[0]
    out = [uasset_path]
    for ext in (".uexp", ".ubulk"):
        sib = base + ext
        if os.path.isfile(sib):
            out.append(sib)
    return out


def _render_one(asset, out_path, size, playing):
    if playing:
        return fx_thumbnail.try_render_playing(asset, out_path, size)
    return fx_thumbnail.try_render(asset, out_path, size)


def _run(params, playing):
    files = params.get("files") or []
    out_dir = params.get("outDir")
    if not out_dir:
        raise RuntimeError("render requires 'outDir'")
    fx_common.ensure_dir(out_dir)
    size = int(params.get("size", 256))

    content_dir = unreal.Paths.project_content_dir()
    mount = "_FXLibRender"
    dest_dir = os.path.join(content_dir, mount)
    fx_common.ensure_dir(dest_dir)

    results = []
    try:
        for src in files:
            if not src or not os.path.isfile(src):
                results.append({"source": src, "available": False, "path": None})
                continue
            base = os.path.splitext(os.path.basename(src))[0]
            # copy asset + siblings into the temp mount
            for zn in _related_paths(src):
                shutil.copy2(zn, os.path.join(dest_dir, os.path.basename(zn)))

            object_path = "/Game/%s/%s" % (mount, base)
            # Try loading directly first; scan only if needed to save time.
            asset = unreal.EditorAssetLibrary.load_asset(object_path)
            if asset is None:
                try:
                    unreal.AssetRegistryHelpers.get_asset_registry().scan_paths_synchronous(
                        [os.path.join(content_dir, mount)])
                except Exception as e:
                    unreal.log_warning("[FXLibrary] scan failed for %s: %s" % (src, e))
                asset = unreal.EditorAssetLibrary.load_asset(object_path)
            out_path = os.path.join(out_dir, base + ".png")
            ok = False
            if asset is not None:
                ok = _render_one(asset, out_path, size, playing)
            results.append({"source": src, "available": ok,
                            "path": out_path if ok else None})
            # clean up temp copy
            for zn in _related_paths(src):
                tmp = os.path.join(dest_dir, os.path.basename(zn))
                try:
                    os.remove(tmp)
                except Exception:
                    pass
    finally:
        # remove the temp mount directory if empty
        try:
            if os.path.isdir(dest_dir) and not os.listdir(dest_dir):
                os.rmdir(dest_dir)
        except Exception:
            pass

    return {"thumbnails": results, "count": len(results)}


def run_render_files(params):
    """Static editor thumbnails for local .uasset files."""
    return _run(params, playing=False)


def run_render_playing(params):
    """Real playing-frame thumbnails for local .uasset files."""
    return _run(params, playing=True)
