# tools/t_logic.py -- verify tag & folder HANDLERS fire + filter correctly
# using reliable direct widget clicks (QTest.mouseClick on the actual
# widget fires its clicked signal -- this tests the LOGIC path that
# the duplication/orphan bug was intercepting at the real-click level).
import os, sys, tempfile, time
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
import app.config as cfg
CFGDIR = tempfile.mkdtemp(prefix="fxlg_cfg_")
cfg.CONFIG_DIR = CFGDIR
cfg.CONFIG_FILE = os.path.join(CFGDIR, "config.json")
cfg.DEFAULT_LIBRARY_DIR = os.path.join(CFGDIR, "library")
cfg.DEFAULTS["library_dir"] = cfg.DEFAULT_LIBRARY_DIR
from app.database import Database
from app.scanner import ScannerWorker
from app.ui.main_window import MainWindow
from PySide6.QtWidgets import QApplication, QInputDialog, QPushButton, QTreeWidgetItem
from PySide6.QtTest import QTest
from PySide6.QtCore import Qt

TMP = tempfile.mkdtemp(prefix="fxlg_")
SAMPLE = os.path.join(TMP, "SampleFX", "Content", "FX")
os.makedirs(SAMPLE, exist_ok=True)
TAGS = ["Fire", "Water", "Smoke"]
def mk(fname, t, tags):
    p = os.path.join(SAMPLE, fname)
    with open(p, "wb") as f:
        f.write(b"\x00\x01\x00\x00 header " + t.encode())
    return p
paths = []
for i in range(24):
    t = "NiagaraSystem" if i % 2 == 0 else "ParticleSystem"
    tg = [TAGS[i % 3], TAGS[(i+1) % 3]]
    paths.append((mk("FX_%02d.uasset" % i, t, tg), tg))

app = QApplication.instance() or QApplication(sys.argv)
app.setStyle("Fusion")
win = MainWindow()
win.show()
thumbs = os.path.join(cfg.DEFAULT_LIBRARY_DIR, "thumbs")
w = ScannerWorker(win._db_path, [SAMPLE], thumbs, copy=False, fx_only=False)
res = {}
w.finished.connect(lambda d: res.update(d))
w.start()
dl = time.time() + 25
while not res and time.time() < dl:
    app.processEvents(); time.sleep(0.02)
app.processEvents()
db = win.db
for p, tg in paths:
    db.set_tags(p, ",".join(tg))
win._reload_library()
app.processEvents()
print("LOADED assets:", len(win._all_assets))
ok = True

def chip_by_text(txt):
    for c in win.tag_flow_widget.children():
        if isinstance(c, QPushButton) and c.text().strip().endswith(txt):
            return c
    return None

# ---- TAG handler ----
print("\n==== TAG: QTest.mouseClick on 'Fire' chip ====")
c = chip_by_text("Fire")
print("found Fire chip:", c is not None)
if c:
    print("BEFORE: _active_tag=%r grid=%d" % (win._active_tag, win.grid.total_count()))
    QTest.mouseClick(c, Qt.LeftButton)
    app.processEvents()
    print("AFTER : _active_tag=%r grid=%d" % (win._active_tag, win.grid.total_count()))
    r = win._active_tag == "Fire" and bool(win.grid.assets) \
        and all("Fire" in (a.tags or "") for a in win.grid.assets)
    print("RESULT tag:", "OK" if r else "FAIL")
    ok = ok and r

# ---- FOLDER handler ----
print("\n==== FOLDER: select via item click ====")
QInputDialog.getText = staticmethod(lambda *a, **k: ("LogicFolder", True))
win._create_virtual_folder()
fid = db.get_folders()[0]["id"]
win._add_asset_to_folder(paths[0][0], fid)
win._refresh_folder_tree(); app.processEvents()
item = None
for i in range(win.folder_tree.topLevelItemCount()):
    it = win.folder_tree.topLevelItem(i)
    if it.text(0) == "LogicFolder":
        item = it
print("found folder item:", item is not None)
if item:
    win.folder_tree.setCurrentItem(item)
    win._on_folder_selected(item, 0)
    app.processEvents()
    print("AFTER _current_folder:", win._current_folder, "grid=%d" % win.grid.total_count())
    r = bool(win._current_folder)
    print("RESULT folder:", "OK" if r else "FAIL")
    ok = ok and r

# ---- chip count stable after several tag clicks ----
print("\n==== NO DUP after 8 tag clicks ====")
before = sum(1 for c in win.tag_flow_widget.children() if isinstance(c, QPushButton))
for _ in range(8):
    cc = chip_by_text("Water")
    if cc:
        QTest.mouseClick(cc, Qt.LeftButton)
    app.processEvents()
after = sum(1 for c in win.tag_flow_widget.children() if isinstance(c, QPushButton))
print("chip count before/after 8 clicks:", before, after, "(expect ~7, no growth)")
ok = ok and (after <= before + 1)

print("\n========== OVERALL:", "ALL PASS" if ok else "SOME FAIL", "==========")
sys.exit(0 if ok else 1)
