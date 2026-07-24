# app/ue_bridge.py -- client-side orchestration of the UE headless bridge.
# Writes a request JSON, launches UnrealEditor headless to run fx_runner.py,
# tails the UE log, waits for the result JSON, then returns it.

import os
import sys
import json
import time
import tempfile
import subprocess
from typing import Callable, Optional

# Default bridge folder. In a frozen (PyInstaller) build, modules live inside
# the PYZ archive so `__file__` is a virtual path; use sys._MEIPASS (which
# points at the extracted bundle root, e.g. dist/FXLibraryClient/_internal)
# to locate the bundled bridge/ folder.
if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
    DEFAULT_BRIDGE_DIR = os.path.normpath(os.path.join(sys._MEIPASS, "bridge"))
else:
    DEFAULT_BRIDGE_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "bridge"))

# Candidate locations to auto-detect UnrealEditor.exe when not set in config.
_CANDIDATE_UE_PATHS = [
    r"C:\Program Files\Epic Games\UE_5.4\Engine\Binaries\Win64\UnrealEditor.exe",
    r"C:\Program Files\Epic Games\UE_5.3\Engine\Binaries\Win64\UnrealEditor.exe",
    r"C:\Program Files\Epic Games\UE_5.5\Engine\Binaries\Win64\UnrealEditor.exe",
    r"D:\Program Files\Epic Games\UE_5.4\Engine\Binaries\Win64\UnrealEditor.exe",
]


def find_ue_editor(configured: str = "") -> Optional[str]:
    """Return a usable UnrealEditor.exe path, or None if not found."""
    if configured and os.path.isfile(configured):
        return configured
    for p in _CANDIDATE_UE_PATHS:
        if os.path.isfile(p):
            return p
    # Last resort: scan the Epic Games folder.
    base = r"C:\Program Files\Epic Games"
    if os.path.isdir(base):
        for name in sorted(os.listdir(base)):
            cand = os.path.join(base, name, "Engine", "Binaries", "Win64", "UnrealEditor.exe")
            if os.path.isfile(cand):
                return cand
    return None


def _headless_ue_bin(ue_editor: str) -> str:
    """Prefer UnrealEditor-Cmd.exe (no GUI) when it lives next to the configured
    UnrealEditor.exe. Falls back to the configured exe if the Cmd variant is
    missing."""
    if not ue_editor or not os.path.isfile(ue_editor):
        return ue_editor
    # Only swap the Windows editor exe; on other platforms just use what's set.
    if not ue_editor.lower().endswith("unrealeditor.exe"):
        return ue_editor
    d = os.path.dirname(ue_editor)
    cmd = os.path.join(d, "UnrealEditor-Cmd.exe")
    if os.path.isfile(cmd):
        return cmd
    return ue_editor


def run_bridge(ue_editor: str, project: str, command: str, params: dict,
               bridge_dir: str = None, log_cb: Callable[[str], None] = None,
               timeout: float = 600.0) -> dict:
    """Launch UE headless, run `command` with `params`, return the result dict.

    log_cb (optional) is called with each new log line from the UE process.
    Raises RuntimeError on timeout / launch failure.
    """
    bridge_dir = bridge_dir or DEFAULT_BRIDGE_DIR
    runner = os.path.join(bridge_dir, "fx_runner.py")
    if not os.path.isfile(runner):
        raise RuntimeError("Bridge script not found: %s" % runner)

    work = tempfile.mkdtemp(prefix="fxlib_")
    req_path = os.path.join(work, "fx_request.json")
    res_path = os.path.join(work, "fx_result.json")
    log_path = os.path.join(work, "ue.log")

    with open(req_path, "w", encoding="utf-8") as f:
        json.dump({"command": command, "params": params}, f, indent=2)

    exe = _headless_ue_bin(ue_editor)
    cmd = [
        exe,
        project,
        "-ExecutePythonScript=" + runner,
        "-unattended",
        "-NoSplash",
        "-nohmd",
        "-nosound",
        "-ABSLOG=" + log_path,
        "-log",
    ]

    env = dict(os.environ)
    env["FXLIB_REQUEST_PATH"] = req_path
    env["FXLIB_RESULT_PATH"] = res_path

    if log_cb:
        log_cb("[client] launching: " + " ".join(cmd))

    # Windowed rendering: UE needs a real GPU surface, so do NOT hide the
    # process window and do NOT use -RenderOffScreen. The editor window will
    # be visible while rendering.
    popen_kwargs = {
        "env": env,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "stdin": subprocess.DEVNULL,
    }

    proc = subprocess.Popen(cmd, **popen_kwargs)

    # Tail the UE log while waiting for the result file.
    last_pos = 0
    deadline = time.time() + timeout
    result = None
    while time.time() < deadline:
        if os.path.exists(res_path):
            try:
                with open(res_path, "r", encoding="utf-8") as f:
                    result = json.load(f)
                break
            except Exception:
                pass
        # Read new log lines.
        if log_cb and os.path.exists(log_path):
            try:
                with open(log_path, "r", encoding="utf-8", errors="replace") as f:
                    f.seek(last_pos)
                    for line in f:
                        if line.strip():
                            log_cb(line.rstrip("\n"))
                    last_pos = f.tell()
            except Exception:
                pass
        # Process exited but no result file -> capture exit code and stop.
        rc = proc.poll()
        if rc is not None and not os.path.exists(res_path):
            break
        time.sleep(0.3)

    # Drain remaining log.
    if log_cb and os.path.exists(log_path):
        try:
            with open(log_path, "r", encoding="utf-8", errors="replace") as f:
                f.seek(last_pos)
                for line in f:
                    if line.strip():
                        log_cb(line.rstrip("\n"))
        except Exception:
            pass

    if result is None:
        rc = proc.poll()
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except Exception:
            proc.kill()
        tail = []
        if os.path.exists(log_path):
            try:
                with open(log_path, "r", encoding="utf-8", errors="replace") as f:
                    tail = [ln.rstrip("\n") for ln in f if ln.strip()][-20:]
            except Exception:
                pass
        msg = "UE bridge timed out or exited without a result (%.0fs, rc=%s)." % (timeout, rc)
        if tail:
            msg += "\nLast UE log lines:\n" + "\n".join(tail)
        raise RuntimeError(msg)

    return result
