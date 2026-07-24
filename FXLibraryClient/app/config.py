# app/config.py -- client-side configuration persistence.
# Stores settings in %USERPROFILE%/.fxlibrary/config.json

import os
import json

CONFIG_DIR = os.path.join(os.path.expanduser("~"), ".fxlibrary")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")

# The standalone FX library lives here by default (DB + thumbs + optional copies).
DEFAULT_LIBRARY_DIR = os.path.join(CONFIG_DIR, "library")

DEFAULTS = {
    "ue_editor_path": "",   # absolute path to UnrealEditor.exe (optional, for thumbnail rendering)
    "library_dir": DEFAULT_LIBRARY_DIR,  # the standalone FX library root
    "last_project": "",     # optional .uproject used only to render real thumbnails
    "scan_roots": [],       # directories the "auto-scan" feature searches
    "import_mode": "reference",  # "reference" (keep original) | "copy" (into library)
    "import_fx_only": True,  # skip non-FX (.uasset that is neither Niagara nor Cascade)
    "ue_bridge_dir": "",    # optional override of the bundled bridge/ folder
    "language": "auto",     # "auto" | "zh" | "en"
    "theme": "auto",        # "auto" | "light" | "dark"
}


def load():
    if not os.path.exists(CONFIG_FILE):
        return dict(DEFAULTS)
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        merged = dict(DEFAULTS)
        merged.update(data)
        return merged
    except Exception:
        return dict(DEFAULTS)


def save(cfg):
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)
