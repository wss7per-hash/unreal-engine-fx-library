# app/models.py -- plain data containers used across the client.
#
# The FX library is a STANDALONE asset manager (Eagle-style): it catalogs
# local .uasset files on disk, generates thumbnails, and manages them. The
# primary identity of an asset is its on-disk file path (source_path), not a
# UE object path. `object_path` is kept as a read-only alias so the card grid
# layer (which keys selection/thumbnails by object_path) keeps working.

from dataclasses import dataclass, field
from typing import List, Optional

TYPE_NIAGARA = "Niagara"
TYPE_CASCADE = "Cascade"
TYPE_UNKNOWN = "Unknown"


@dataclass
class FXAsset:
    source_path: str                 # original .uasset absolute path (PRIMARY KEY)
    name: str
    type: str = TYPE_UNKNOWN         # "Niagara" | "Cascade" | "Unknown"
    class_name: str = ""             # e.g. "NiagaraSystem"
    stored_path: Optional[str] = None   # library copy path (set when import_mode=copy)
    thumb_path: Optional[str] = None
    tags: str = ""
    favorite: bool = False
    rating: int = 0                  # 0..5
    note: str = ""
    size: int = 0                    # bytes
    imported_at: str = ""            # ISO timestamp
    source: str = "scan"             # "scan" | "fxpack"
    project_path: str = ""           # UE project used to render the thumbnail (optional)
    engine_version: str = ""         # detected UE engine label, e.g. "UE 5.4" ("" = not in a UE project)
    health: str = "ok"               # "ok" | "warn" | "bad"
    tier: int = 1                    # 1=engine 2=peak 3=manual
    deps: List[str] = field(default_factory=list)
    blueprint: bool = False          # True = this FX is wrapped inside a Blueprint
                                     # (Blueprint that *contains* a Niagara/Cascade system)
    deleted: bool = False            # True = soft-deleted (moved to trash)
    has_thumb: bool = False         # True = a REAL embedded thumbnail was extracted
                                     # (False = only a generated placeholder is shown)

    @property
    def object_path(self):
        # Backward-compatible alias for the card grid (selection / thumbnails).
        return self.source_path


@dataclass
class FxPackEntry:
    name: str
    fxpack_path: str
    source_project: str = ""
    engine_version: str = ""
    manifest: str = ""  # JSON string
    added_at: str = ""
