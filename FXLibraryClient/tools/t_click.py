# tools/t_click.py -- verify the 3 core functions work after the
# native-window refactor, and that the architecture can no longer
# swallow clicks (deep-fix proof).
import os, sys, tempfile, time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from PySide6.QtWidgets import QApplication, QInputDialog, QPushButton
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
    app.processEvents()
    time.sleep(0.02)
win._reload_library()
print("LOADED assets:", len(win._all_assets))
ok = True


def banner(t):
    print("\n==== %s ====" % t)


# ---- 1) tag chip click really filters ----
banner("TEST 1: click 'Fire' tag chip -> grid filters")
a0 = win._all_assets[0]
win._current_asset = a0
win.insp_tag_input.setText("Fire")
win._add_tag()
tag_chip = None
for c in win.tag_flow_widget.children():
    if isinstance(c, QPushButton) and c.text().strip().endswith("Fire"):
        tag_chip = c
        break
print("found tag chip:", tag_chip is not None)
print("BEFORE: _active_tag =", repr(win._active_tag), "grid =", win.grid.total_count())
QTest.mouseClick(tag_chip, Qt.LeftButton)
app.processEvents()
print("AFTER : _active_tag =", repr(win._active_tag), "grid =", win.grid.total_count())
r = win._active_tag == "Fire" and all(
    "Fire" in (c.tags or []) for c in win.grid.assets)
print("RESULT tag:", "OK" if r else "FAIL")
ok = ok and r

# ---- 2) filter combo really filters ----
banner("TEST 2: type combo -> Niagara filters grid")
win._set_view("all")
win._apply_filters()
print("BEFORE: grid =", win.grid.total_count())
idx = win.type_combo.findData("Niagara")
win.type_combo.setCurrentIndex(idx)
app.processEvents()
print("AFTER : grid =", win.grid.total_count(),
      "types =", set(c.type for c in win.grid.assets))
r = bool(win.grid.assets) and all(c.type == "Niagara" for c in win.grid.assets)
print("RESULT filter:", "OK" if r else "FAIL")
ok = ok and r

# ---- 3) folder click really selects ----
banner("TEST 3: click folder in tree -> _current_folder set")
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
    QTest.mouseClick(win.folder_tree.viewport(), Qt.LeftButton,
                     Qt.NoModifier, rect.center())
    app.processEvents()
    print("AFTER : _current_folder =", win._current_folder,
          "grid =", win.grid.total_count())
    r = bool(win._current_folder)
    print("RESULT folder:", "OK" if r else "FAIL")
    ok = ok and r

# ---- 4) STRUCTURAL: MainWindow defines NO mousePressEvent ----
banner("TEST 4: MainWindow has no own mousePressEvent (no click-stealing)")
defines = "mousePressEvent" in MainWindow.__dict__
print("MainWindow defines mousePressEvent?:", defines, "(expect False)")
print("RESULT struct:", "OK" if not defines else "FAIL")
ok = ok and (not defines)

# ---- 5) STRUCTURAL: window is NOT frameless ----
banner("TEST 5: window uses native chrome (no FramelessWindowHint)")
frameless = bool(win.windowFlags() & Qt.FramelessWindowHint)
print("FramelessWindowHint set?:", frameless, "(expect False)")
print("RESULT native:", "OK" if not frameless else "FAIL")
ok = ok and (not frameless)

print("\n========== OVERALL:", "ALL PASS" if ok else "SOME FAIL", "==========")
sys.exit(0 if ok else 1)
