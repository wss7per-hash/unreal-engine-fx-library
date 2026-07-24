import unreal

# Target engine version. The plugin is written/tested against UE 5.4.
ENGINE_VERSION = "5.4"

# Root folder (under project Saved/) for exported .fxpack files, thumbnails and temp work.
EXPORT_ROOT = unreal.Paths.project_saved_dir() + "FXLibrary/"

# Class names we treat as FX assets.
NIAGARA_CLASS = "NiagaraSystem"
CASCADE_CLASS = "ParticleSystem"

# TopLevelAssetPath package/asset pairs (used for robust class lookup in UE 5.4).
CLASS_PATHS = {
    "NiagaraSystem": ("/Script/Niagara", "NiagaraSystem"),
    "ParticleSystem": ("/Script/Engine", "ParticleSystem"),
}


def ensure_dir(path):
    """Create a directory (including parents) if missing."""
    import os
    os.makedirs(path, exist_ok=True)
