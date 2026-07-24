# FX Library — UE5 Effects Manager (Standalone Client)

A desktop client (Python + PySide6) to **browse, preview and migrate** Niagara /
Cascade particle effects across UE5 projects — **without an in-editor plugin**.

The client does the GUI + library index (SQLite). When it needs engine work
(read assets, render thumbnails, import/export), it **launches Unreal Editor
headless** (`-ExecutePythonScript`) to run the bundled Python bridge scripts,
which do the engine-sensitive work and return JSON.

---

## Features (MVP)

- **Browse** all Niagara / Cascade assets in any UE5 project (grid view).
- **Static thumbnails** — best-effort engine render, with a placeholder fallback
  and a **manual (Tier 3)** image option (no video playback).
- **Export `.fxpack`** — a self-contained zip of an effect + its recursive
  dependencies (+ manifest + thumbnail), so it won't go pink when imported.
- **Import `.fxpack`** — unpacks into the current project (default `/Game/ImportedFX`),
  preserving original package paths so internal references stay valid.
- **Health check** — scans for missing dependencies and duplicate assets.
- **Local library** — SQLite index of discovered assets, thumbnails and `.fxpack`s.

> `.fxpack` is just `zip + manifest.json`; inside are 100% standard `.uasset`
> files. Engines see native `.uasset` after import — no new asset format.

---

## Requirements

- Windows + **Unreal Engine 5.3+** installed (the client drives it headless).
- Python 3.11+ (tested with the bundled managed Python).

## Run

**Quick start (this machine):** double-click `run.bat` in the project folder.
It uses the pre-configured managed Python that already has PySide6 installed.
GUI needs a real display; if it fails to launch, the error shows in the window.

**Portable (any machine with Python 3.11+):**
```bash
python -m venv venv
venv\Scripts\pip install -r requirements.txt
venv\Scripts\python main.py
```

**Build a standalone `.exe` (no Python required at runtime):** see "Packaging"
below — once built you can double-click `dist/FXLibraryClient.exe`.

First run: open **Settings** and point **UnrealEditor.exe** at your install
(e.g. `C:\Program Files\Epic Games\UE_5.4\Engine\Binaries\Win64\UnrealEditor.exe`),
and set a **Library folder** for exported `.fxpack`s and thumbnails.

Then: **Open Project** → pick a `.uproject` → **Refresh List**.

## How the headless bridge works

```
client writes fx_request.json
  -> launches: UnrealEditor.exe <project> -ExecutePythonScript=<bridge>/fx_runner.py
               -unattended -NoSplash -RenderOffScreen -ABSLOG=<log>
  -> bridge reads request, runs the command, writes fx_result.json
  -> client reads result + tails the UE log
  -> editor exits; client updates the UI
```

Bridge scripts live in `bridge/` (run **inside** UE): `fx_runner`,
`fx_config`, `fx_common`, `fx_list`, `fx_thumbnail`, `fx_export`,
`fx_import`, `fx_health`.

## Known limitations / next steps

- Thumbnail rendering depends on the UE Python `EditorThumbnailSubsystem`
  (version-sensitive). If a thumb is unavailable it shows a placeholder; use
  **Set Manual Thumbnail** or open the asset once in the editor to cache one.
- Oneshot mode relaunches UE per operation (cold start 10–30s). A **server /
  long-lived headless UE** mode is the planned enhancement to avoid this.
- Import reuses original package paths for reference integrity; wholesale
  path remapping (v2) is not yet implemented.

---

## Packaging a standalone `.exe`

A prebuilt `dist/FXLibraryClient/FXLibraryClient.exe` is produced by PyInstaller.
It bundles Python + Qt + the `bridge/` scripts, so the end user needs **no Python
install**. Run:

```bash
build_exe.bat      # or: pyinstaller --noconfirm --windowed --name FXLibraryClient
                   #      --add-data "bridge;bridge" --hidden-import PySide6.QtSvg
                   #      --hidden-import PySide6.QtXml main.py
```

The `bridge/` folder is embedded (read-only, unpacked to PyInstaller's temp dir at
runtime) and handed to UnrealEditor via `-ExecutePythonScript`. User data (config,
`fxlibrary.db`, thumbnails, exported `.fxpack`s) lives in `%USERPROFILE%/.fxlibrary`
and `%TEMP%` — never inside the bundled files.
