# -*- coding: utf-8 -*-
"""Detect Unreal Engine projects from arbitrary file paths.

A UE project is identified by a ``*.uproject`` file somewhere up the directory
tree from an asset. The ``.uproject`` is JSON and carries an ``EngineAssociation``
field that tells us which engine built it:

  * ``"5.4"`` / ``"4.27"`` / ...   -> a launcher-installed engine (clean version)
  * a GUID like ``"9a6d3a8e..."``  -> a custom / source build registered in the
                                     Windows registry under
                                     ``HKCU\\Software\\Epic Games\\Unreal Engine\\Builds``

This module is pure standard library (no PySide6 / UE dependency) so it can be
unit-tested and reused from the scanner worker thread.
"""

import os
import re
import json

# A clean launcher version looks like "5.4" or "5.4.1".
_VERSION_RE = re.compile(r"^\d+\.\d+(?:\.\d+)?$")
# A GUID engine association is a long hex string (no dots).
_GUID_RE = re.compile(r"^[0-9a-fA-F]{20,}$")

_MAX_WALK = 8  # don't climb more than 8 parent dirs looking for a .uproject


class UEProject:
    """Resolved Unreal Engine project metadata."""

    __slots__ = ("uproject_path", "name", "engine_raw", "engine_label")

    def __init__(self, uproject_path, name, engine_raw, engine_label):
        self.uproject_path = uproject_path   # absolute path to the .uproject
        self.name = name                     # project name (= .uproject stem)
        self.engine_raw = engine_raw         # raw EngineAssociation string
        self.engine_label = engine_label     # human label, e.g. "UE 5.4"

    def __repr__(self):
        return "UEProject(name=%r, engine=%r)" % (self.name, self.engine_label)


def find_uproject(file_path, max_depth=_MAX_WALK):
    """Walk up from *file_path* looking for a ``*.uproject``.

    Returns the absolute path of the first ``.uproject`` found, or ``None``.
    """
    cur = os.path.dirname(os.path.abspath(file_path))
    for _ in range(max_depth):
        try:
            names = os.listdir(cur)
        except Exception:
            return None
        for f in names:
            if f.lower().endswith(".uproject"):
                return os.path.join(cur, f)
        parent = os.path.dirname(cur)
        if parent == cur:
            return None
        cur = parent
    return None


def _resolve_engine_label(engine_raw):
    """Turn a raw ``EngineAssociation`` into a human label like 'UE 5.4'."""
    if not engine_raw:
        return "UE"
    if _VERSION_RE.match(engine_raw):
        return "UE " + engine_raw
    if _GUID_RE.match(engine_raw):
        resolved = _resolve_custom_engine(engine_raw)
        return resolved or "UE 自定义版"
    # Anything else (odd string) — show it verbatim but prefixed.
    return "UE (%s)" % engine_raw


def _resolve_custom_engine(guid):
    """Resolve a GUID engine association via the Windows registry.

    Returns a label like 'UE 5.4' when the install path can be read and its
    ``Engine/Build/Build.version`` parsed; otherwise ``None``.
    """
    try:
        import winreg
    except Exception:
        return None
    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Epic Games\Unreal Engine\Builds")
        install_path, _ = winreg.QueryValueEx(key, guid)
    except Exception:
        return None
    if not install_path or not os.path.isdir(install_path):
        return None
    ver = _read_engine_version_from_path(install_path)
    if ver:
        return "UE " + ver
    # Fall back to the install folder name (often "UE_5.4" / "UnrealEngine").
    base = os.path.basename(os.path.normpath(install_path))
    m = re.search(r"(\d+\.\d+)", base)
    if m:
        return "UE " + m.group(1)
    return None


def _read_engine_version_from_path(engine_path):
    """Read MajorVersion.MinorVersion from an engine's Build.version."""
    bv = os.path.join(engine_path, "Engine", "Build", "Build.version")
    try:
        with open(bv, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        major = data.get("MajorVersion")
        minor = data.get("MinorVersion")
        if isinstance(major, int) and isinstance(minor, int):
            return "%d.%d" % (major, minor)
    except Exception:
        pass
    return None


def detect_ue_project(file_path):
    """Detect the UE project an asset belongs to.

    Returns a :class:`UEProject` if *file_path* sits inside a UE project tree,
    otherwise ``None``.
    """
    up = find_uproject(file_path)
    if not up or not os.path.isfile(up):
        return None
    name = os.path.splitext(os.path.basename(up))[0]
    engine_raw = ""
    try:
        with open(up, "r", encoding="utf-8-sig") as fh:
            data = json.load(fh)
        engine_raw = str(data.get("EngineAssociation", "") or "")
    except Exception:
        # Unreadable / malformed .uproject — still treat the project as valid,
        # just with an unknown engine version.
        pass
    label = _resolve_engine_label(engine_raw)
    return UEProject(up, name, engine_raw, label)


def project_folder_name(project):
    """Category (folder) name for a detected project.

    Format: ``"<ProjectName> [UE 5.4]"`` — the project name plus the engine
    version in brackets, so the sidebar shows both at a glance.
    """
    return "%s [%s]" % (project.name, project.engine_label)
