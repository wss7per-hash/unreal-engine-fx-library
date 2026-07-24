"""Decisive regression test for the "rapid clicks don't refresh" bug.

The user's debug log showed: after the FIRST tag click, the next 5 rapid
clicks produced NO set_assets call at all (the deferred QTimer.singleShot
was starved by a 4s sidebar rebuild blocking the event loop).

This test calls _set_tag_filter SYNCHRONOUSLY, back-to-back, with NO
event-loop pump between clicks (exactly the rapid-click case), and asserts
that grid.set_assets() is invoked ONCE PER CLICK. If the old deferred
path were still in place, only the first click would fire and the rest
would be starved -> FAIL.
"""
import os, sys, tempfile
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtWidgets import QApplication
app = QApplication.instance() or QApplication([])

from app.ui.main_window import MainWindow as MW


class FakeAsset:
    def __init__(self, name, type_, tags, fav=False):
        self.name = name
        self.type = type_
        self.tags = tags
        self.source_path = os.path.join(tempfile.gettempdir(), name + ".uasset")
        self.favorite = fav
        self.imported_at = None


class Stub:
    def __init__(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)


def main():
    assets = [
        FakeAsset("SM_Fire", "Niagara", "fire,1232"),
        FakeAsset("SM_Water", "Niagara", "water"),
        FakeAsset("BP_Enemy", "Blueprint", "炮"),
        FakeAsset("BP_Test", "Blueprint", "test,炮"),
    ]

    win = MW.__new__(MW)
    win._all_assets = assets
    win._active_tag = None
    win._current_view = "all"
    win._current_cat = None
    win._current_src = "all"
    win._current_folder = None
    win.folder_tree = Stub(clearSelection=lambda: None)
    win.tag_clear_btn = Stub(setVisible=lambda v: None)
    win._tag_chips = {}
    win._nav_map = {}
    for k in ("has_thumb", "no_thumb", "fav", "no_tag"):
        setattr(win, "nav_" + k, Stub(setChecked=lambda v: None))

    calls = {"n": 0}

    class FakeGrid:
        def __init__(s):
            s.assets = []
        def set_assets(s, items):
            s.assets = list(items)
            calls["n"] += 1
    win.grid = FakeGrid()

    # Real helpers from the class:
    win._update_nav_checked = MW._update_nav_checked.__get__(win)
    win._refresh_grid = MW._refresh_grid.__get__(win)
    # _apply_filters: real logic would need DB; stub it to filter by tag
    # and call the grid (this is all we need to prove "every click refreshes").
    def _apply_filters():
        if win._active_tag:
            out = [a for a in win._all_assets if win._active_tag in a.tags]
        else:
            out = list(win._all_assets)
        win.grid.set_assets(out)
    win._apply_filters = _apply_filters
    win._set_tag_filter = MW._set_tag_filter.__get__(win)

    clicks = ["1232", "1232", "fire", "炮", "test", "炮"]
    results = []
    for t in clicks:
        win._set_tag_filter(t)
        results.append((t, len(win.grid.assets)))

    print("rapid click sequence (no event-loop pump between clicks):")
    for t, n in results:
        print("  click %-6s -> %d assets" % (t, n))

    expected = len(clicks)
    ok = calls["n"] == expected and all(n >= 1 for _, n in results)
    print("\nGRID UPDATED ON EVERY CLICK:", "PASS" if ok else "FAIL",
          "(set_assets calls=%d expected=%d)" % (calls["n"], expected))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
