# -*- coding: utf-8 -*-
"""Single source of truth for the product version.

All version strings (window title, about dialog, Windows version
resource, build artifact names) MUST be derived from here.
"""

__version__ = "0.2.0"

# Baked in at build time by build_exe.bat / tools/make_version_info.py.
# Empty in dev runs (UI falls back to executable/file mtime).
__build_date__ = ""
