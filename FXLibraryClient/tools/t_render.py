# tools/t_render.py -- DIAGNOSTIC: distinguish "data didn't update"
# from "view didn't repaint" when clicking a tag/folder filter.
# Runs in offscreen, where the widget *state tree* (show/setParent/geometry/
# isVisible) is real even though no pixels are drawn -- so we can inspect
# whether the grid's live cards are correctly created and positioned after a
# click, which is exactly what the user can't see on screen.
import os, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
app = QApplication.instance() or QApplication(sys.argv)

import app.config as cfg
CFGDIR = tempfile.mkdtemp(prefix="fxr_")
cfg.CONFIG_DIR = CFGDIR
cfg.CONFIG_FILE = os.path.join(CFGDIR, "config.json")
cfg.DEFAULT_LIBRARY_DIR = os.path.join(CFGDIR, "library")
cfg.DEFAULTS["library_dir"] = cfg.DEFAULT_LIBRARY_DIR

from app.database import Database as DB
from app.models import FXAsset as FX
from app.ui.main_window import MainWindow

win = MainWindow()
win.show()
db = DB(win._db_path, backup=False)

def mk(nm, ty, bp=False):
    p = os.path.join(CFGDIR, nm)
    return FX(source_path=p, name=nm, type=ty, class_name=ty,
              stored_path=p, thumb_path="", size=10,
              imported_at="2026-01-01", source="scan",
              blueprint=bp, has_thumb=False, tier=4)

for a in (mk("NS_Fire","Niagara"), mk("NS_Exp","Niagara"),
          mk("PS_Smoke","Cascade"), mk("BP_X","Niagara", bp=True)):
    db.upsert_asset(a)
win._reload_library()
fp = [a.source_path for a in win._all_assets if a.name=="NS_Fire"][0]
db.set_tags(fp, "fire")
win._reload_library()

print("=== BEFORE click ===")
print("total assets      :", len(win._all_assets))
print("grid.assets      :", len(win.grid.assets))
print("grid._live count :", len(win.grid._live))
print("first live card   :", end=" ")
if win.grid._live:
    c = next(iter(win.grid._live.values()))
    print("name=%s visible=%s pos=%s" % (c.asset.name, c.isVisible(), (c.pos().x(), c.pos().y())))
else:
    print("(none)")

print("\n=== SIMULATE tag click (win._set_tag_filter('fire')) ===")
win._set_tag_filter("fire")
app.processEvents()

print("active_tag       :", repr(win._active_tag))
print("grid.assets     :", len(win.grid.assets))
print("grid._live count:", len(win.grid._live))
print("live cards:")
for i, c in enumerate(win.grid._live.values()):
    print("  [%d] name=%s visible=%s pos=%s" % (
        i, c.asset.name, c.isVisible(), (c.pos().x(), c.pos().y())))

# Now simulate the user clicking a toolbar combo (which the user says
# "makes it refresh"): process pending events a few times.
print("\n=== SIMULATE toolbar click (extra processEvents) ===")
app.processEvents()
app.sendPostedEvents()
app.processEvents()
print("after extra events, grid._live count:", len(win.grid._live))
for i, c in enumerate(win.grid._live.values()):
    print("  [%d] name=%s visible=%s pos=%s" % (
        i, c.asset.name, c.isVisible(), (c.pos().x(), c.pos().y())))

ok = (win._active_tag == "fire") and (len(win.grid.assets) == 1) and len(win.grid._live) == 1
print("\nRESULT:", "DATA+WIDGET OK (problem is real-screen paint timing)"
      if ok else "DATA/WIDGET LAYER BROKEN (logic bug)")
