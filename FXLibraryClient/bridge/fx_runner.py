# fx_runner.py -- headless bridge ENTRY POINT.
# Launched by the client via:
#   UnrealEditor.exe <Project>.uproject
#     -ExecutePythonScript=<this file>
#     -unattended -NoSplash -RenderOffScreen -ABSLOG=<log>
# Request/result are passed via env vars FXLIB_REQUEST_PATH / FXLIB_RESULT_PATH.
# Reads the request JSON, dispatches to a module, writes the result JSON, then
# asks the (headless) editor to exit.

import os
import sys
import json
import traceback
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import unreal
import fx_common
import fx_list
import fx_thumbnail
import fx_export
import fx_import
import fx_health
import fx_render


DISPATCH = {
    "list": fx_list.run_list,
    "thumbnail_batch": fx_thumbnail.run_thumbnail_batch,
    "export": fx_export.run_export,
    "import": fx_import.run_import,
    "render_files": fx_render.run_render_files,
    "render_playing": fx_render.run_render_playing,
    "health": fx_health.run_health,
}


def main():
    req_path = os.environ.get("FXLIB_REQUEST_PATH")
    res_path = os.environ.get("FXLIB_RESULT_PATH")
    log_lines = []

    def cap(msg):
        log_lines.append(str(msg))
        unreal.log("[FXLibrary] " + str(msg))

    result = {"ok": False, "command": None, "data": None, "error": None,
              "traceback": None, "logs": []}
    try:
        if not req_path or not os.path.exists(req_path):
            raise RuntimeError("FXLIB_REQUEST_PATH not set or file missing: %s" % req_path)
        with open(req_path, "r", encoding="utf-8") as f:
            req = json.load(f)
        cmd = req.get("command")
        params = req.get("params", {}) or {}
        result["command"] = cmd
        cap("request command=%s" % cmd)

        # Make sure the asset registry is ready before doing engine work.
        fx_common.try_scan()

        fn = DISPATCH.get(cmd)
        if fn is None:
            raise RuntimeError("Unknown command: %s" % cmd)
        data = fn(params)
        result["ok"] = True
        result["data"] = data
        cap("done: %s" % cmd)
    except Exception as e:
        result["ok"] = False
        result["error"] = str(e)
        result["traceback"] = traceback.format_exc()
        cap("ERROR: %s" % e)
        cap(traceback.format_exc())
    finally:
        result["logs"] = log_lines
        if res_path:
            try:
                with open(res_path, "w", encoding="utf-8") as f:
                    json.dump(result, f, indent=2, ensure_ascii=False)
            except Exception as we:
                unreal.log_warning("[FXLibrary] failed to write result file: %s" % we)
        # Headless: ask the editor to exit now that the result is written.
        try:
            unreal.SystemLibrary.request_exit(False)
        except Exception:
            pass


if __name__ == "__main__":
    main()
