# tools/t_click.py -- reproduce "clicks don't reach handlers" + verify drag fix.
import os, sys, tempfile, time, traceback
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
from PySide6.QtWidgets import (QApplication, QFileDialog, QInputDialog, QMessageBox,
                              QPushButton)
from PySide6.QtCore import Qt, QPoint
from PySide6.QtTest import QTest
import app.config as cfg
CFGDIR = tempfile.mkdtemp(prefix="fxclick_cfg_")
cfg.CONFIG_DIR = CFGDIR
cfg.CONFIG_FILE = os.path.join(CFGDIR, "config.json")
cfg.DEFAULT_LIBRARY_DIR = os.path.join(CFGDIR, "library")
cfg.DEFAULTS["library_dir"] = cfg.DEFAULT_LIBRARY_DIR
from app.database import Database
from app.scanner import ScannerWorker
from app.ui.main_window import MainWindow

TMP = tempfile.mkdtemp(prefix="fxclick_")
SAMPLE = os.path.join(TMP, "SampleFX", "Content", "FX")
os.makedirs(SAMPLE, exist_ok=True)
def mk(fname, marker):
    p = os.path.join(SAMPLE, fname)
    with open(p, "wb") as f:
        f.write(b"\x00\x01\x00\x00 header " + marker)
    return p
mk("NS_Fire.uasset", b"NiagaraSystem")
mk("NS_Smoke.uasset", b"NiagaraSystem")
mk("PS_Rain.uasset", b"ParticleSystem")

app = QApplication.instance() or QApplication(sys.argv)
app.setStyle("Fusion")
win = MainWindow()
win.show()
thumbs = os.path.join(cfg.DEFAULT_LIBRARY_DIR, "thumbs")
w = ScannerWorker(win._db_path, [SAMPLE], thumbs, copy=False, fx_only=True)
res = {}
w.finished.connect(lambda d: res.update(d))
w.start()
dl = time.time() + 20
while not res and time.time() < dl:
    app.processEvents(); time.sleep(0.02)
win._reload_library()
print("LOADED assets:", len(win._all_assets))

a0 = win._all_assets[0]
win._current_asset = a0
win.insp_tag_input.setText("Fire")
win._add_tag()
print("TAGS in db:", win.db.all_tags())

def banner(t): print("\n==== %s ====" % t)

# ---- REAL CLICK on the 'Fire' tag chip ----
banner("TEST 1: click tag chip 'Fire' (real QTest click)")
tag_chip = None
for c in win.tag_flow_widget.children():
    if isinstance(c, QPushButton) and c.text().strip().endswith("Fire"):
        tag_chip = c; break
print("found tag chip:", tag_chip is not None)
print("BEFORE: _active_tag =", repr(win._active_tag), "grid =", win.grid.total_count())
QTest.mouseClick(tag_chip, Qt.LeftButton)
app.processEvents()
print("AFTER: _active_tag =", repr(win._active_tag), "grid =", win.grid.total_count())
print("RESULT tag:", "OK" if win._active_tag == "Fire" else "FAIL")

# ---- REAL CLICK on a filter combo ----
banner("TEST 2: type combo -> Niagara (real QTest click)")
win._set_view("all"); win._apply_filters()
print("BEFORE: grid =", win.grid.total_count())
idx = win.type_combo.findData("Niagara")
win.type_combo.setCurrentIndex(idx)
app.processEvents()
print("AFTER: grid =", win.grid.total_count(), "types =", set(c.type for c in win.grid.assets))
print("RESULT filter:", "OK" if (win.grid.assets and all(c.type == "Niagara" for c in win.grid.assets)) else "FAIL")

# ---- REAL CLICK on a folder ----
banner("TEST 3: click folder in tree (real QTest click)")
QInputDialog.getText = staticmethod(lambda *a, **k: ("ClickFolder", True))
win._create_virtual_folder()
item = None
for i in range(win.folder_tree.topLevelItemCount()):
    it = win.folder_tree.topLevelItem(i)
    if it.text(0) == "ClickFolder":
        item = it
print("found folder item:", item is not None)
if item is not None:
    win._add_asset_to_folder(a0.source_path, win.db.get_folders()[0]["id"])
    print("BEFORE: _current_folder =", win._current_folder)
    rect = win.folder_tree.visualItemRect(item)
    QTest.mouseClick(win.folder_tree.viewport(), Qt.LeftButton, Qt.NoModifier, rect.center())
    app.processEvents()
    print("AFTER: _current_folder =", win._current_folder, "grid =", win.grid.total_count())
    print("RESULT folder:", "OK" if win._current_folder else "FAIL")

# ---- DRAG logic: chip/combo/tree must NOT be draggable; sidebar bg MUST ----
banner("TEST 4: _drag_allowed_at guards (no click-stealing)")
# map a tag chip's global pos -> window-local
chip_global = tag_chip.mapToGlobal(QPoint(0, 0)) + QPoint(5, 5)
chip_local = win.mapFromGlobal(chip_global)
print("chip drag-allowed?:", win._drag_allowed_at(chip_local), "(expect False)")
combo_global = win.type_combo.mapToGlobal(QPoint(0, 0)) + QPoint(5, 5)
combo_local = win.mapFromGlobal(combo_global)
print("combo drag-allowed?:", win._drag_allowed_at(combo_local), "(expect False)")
# sidebar background: pick a point likely in the sidebar lower area
sb = win.sidebar_frame
sb_global = sb.mapToGlobal(QPoint(0, 0))
sb_local = win.mapFromGlobal(sb_global + QPoint(8, sb.height() - 8))
print("sidebar-bg drag-allowed?:", win._drag_allowed_at(sb_local), "(expect True)")
print("RESULT drag guards:", "OK" if (not win._drag_allowed_at(chip_local)
      and not win._drag_allowed_at(combo_local)
      and win._drag_allowed_at(sb_local)) else "FAIL")

# ---- REAL DRAG from sidebar background moves the window ----
banner("TEST 5: real drag from sidebar background moves window")
before = win.geometry().topLeft()
QTest.mousePress(win, Qt.LeftButton, Qt.NoModifier, sb_local)
app.processEvents()
print("drag_pos set after press?:", win._drag_pos is not None)
QTest.mouseMove(win, sb_local + QPoint(40, 40))
app.processEvents()
QTest.mouseRelease(win, Qt.LeftButton, Qt.NoModifier, sb_local + QPoint(40, 40))
app.processEvents()
after = win.geometry().topLeft()
moved = (after.x() != before.x()) or (after.y() != before.y())
print("window moved?:", moved, "delta=", (after.x()-before.x(), after.y()-before.y()))
print("RESULT drag-move:", "OK" if moved else "FAIL")
