# fx_config.py -- shared constants for the UE headless bridge.
# This file runs INSIDE Unreal (it imports `unreal`).

import unreal  # noqa: F401  (bridge scripts run inside the UE python host)

# Target engine version the bridge was written/tested against.
ENGINE_VERSION = "5.4"

# Class names we treat as FX assets.
NIAGARA_CLASS = "NiagaraSystem"
CASCADE_CLASS = "ParticleSystem"

# TopLevelAssetPath package/asset pairs (robust class lookup in UE 5.x).
CLASS_PATHS = {
    "NiagaraSystem": ("/Script/Niagara", "NiagaraSystem"),
    "ParticleSystem": ("/Script/Engine", "ParticleSystem"),
}


def default_export_root():
    """Default scratch/output dir under the project's Saved folder."""
    return unreal.Paths.project_saved_dir() + "FXLibrary/"
