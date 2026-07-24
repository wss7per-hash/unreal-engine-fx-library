import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

import unreal
import fx_common


def main():
    assets = fx_common.get_all_fx_assets()
    unreal.log("[FXLibrary] Found %d FX asset(s):" % len(assets))
    for a in assets:
        unreal.log("  - %s  (%s)" % (a.asset_name, a.package_path))


if __name__ == "__main__":
    main()
