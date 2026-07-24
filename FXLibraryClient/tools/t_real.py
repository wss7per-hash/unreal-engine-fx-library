# tools/t_real.py -- REALISTIC stress test (many tags/folders/assets).
# Mirrors real library load; verifies (a) each tag chip receives real clicks,
# (b) each tag narrows the grid, (c) folder selection works, (d) no leak,
# (e) no exception during refresh/click cycles.
import os, sys, tempfile, time, traceback
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
from PySide6.QtWidgets import QApplication, QMessageBox
QMessageBox.information = lambda *a, **k: None
QMessageBox.critical = lambda *a, **k: None
import app.config as cfg
CFGDIR = tempfile.mkdtemp(prefix="fxreal_cfg_")
cfg.CONFIG_DIR = CFGDIR
cfg.CONFIG_FILE = os.path.join(cfg.CONFIG_DIR, "config.json")
cfg.DEFAULT_LIBRARY_DIR = os.path.join(cfg.CONFIG_DIR, "library")
cfg.DEFAULTS["library_dir"] = cfg.DEFAULT_LIBRARY_DIR
from app.database import Database
from app.scanner import ScannerWorker
from app.ui.main_window import MainWindow
from PySide6.QtCore import QPoint

app = QApplication.instance() or QApplication(sys.argv)
app.setStyle("Fusion")
win = MainWindow()
win.show()
app.processEvents()

TMP = tempfile.mkdtemp(prefix="fxreal_")
SAMPLE = os.path.join(TMP, "SampleFX", "Content", "FX")
os.makedirs(SAMPLE, exist_ok=True)
TYPES = ["NiagaraSystem", "ParticleSystem", "Material", "Blueprint"]
TAGS = ["Fire", "Water", "Smoke", "Explosion", "Magic", "Blood",
         "Electric", "Slash", "Dust", "Ice"]
def make_uasset(fname, marker):
    p = os.path.join(SAMPLE, fname)
    with open(p, "wb") as f:
        f.write(b"\x00\x01\x00\x00 header " + marker + b" tail")
    return p
paths = []
for i in range(50):
    t = TYPES[i % len(TYPES)]
    p = make_uasset("FX_%02d_%s.uasset" % (i, t), t.encode())
    paths.append((p, t))

thumbs = os.path.join(cfg.DEFAULT_LIBRARY_DIR, "thumbs")
w = ScannerWorker(win._db_path, [SAMPLE], thumbs, copy=False, fx_only=False)
res = {}
w.finished.connect(lambda d: res.update(d))
w.failed.connect(lambda e: res.update({"error": e}))
w.start()
deadline = time.time() + 30
while not res and time.time() < deadline:
    app.processEvents(); time.sleep(0.02)
win._reload_library()
app.processEvents()
print("SCAN total=%s  library=%d" % (res.get("total"), len(win._all_assets)))

db = win.db
# assign tags: each asset gets 1-3 tags from the pool
import random
random.seed(1)
for (p, t) in paths:
    ntags = random.randint(1, 3)
    chosen = random.sample(TAGS, ntags)
    db.set_tags(p, ",".join(chosen))
# ensure at least one asset has "Fire"
db.set_tags(paths[0][0], "Fire")
win._reload_library()
app.processEvents()

# 5 folders, distribute assets
fids = []
for i in range(5):
    fid = db.add_folder("Folder%d" % i, parent_id=None)
    fids.append(fid)
for i, (p, t) in enumerate(paths):
    db.add_asset_to_folder(p, fids[i % 5])
win._refresh_folder_tree()
win._refresh_tag_browser()
app.processEvents()

def chips():
    return [c for c in win.tag_flow_widget.children()
            if c.__class__.__name__ == "QPushButton"
            and getattr(c, "text", lambda: "")().strip() in TAGS]

print("\n=== A) REAL HIT-TEST on EVERY tag chip ===")
all_ok = True
for chip in chips():
    gp = chip.mapToGlobal(QPoint(5, chip.height() // 2))
    hit = QApplication.widgetAt(gp)
    cur = hit
    is_chip = False
    while cur is not None:
        if cur is chip:
            is_chip = True; break
        cur = cur.parent()
    if not is_chip:
        all_ok = False
        print("  !! chip %r at %s hit=%s" % (chip.text(), gp, hit))
print("  every tag chip receives real clicks:", all_ok)

print("\n=== B) Each tag narrows the grid correctly ===")
base = len(win.grid.assets)
fails = 0
for tag in TAGS:
    win._set_tag_filter(tag)
    app.processEvents()
    expected = sum(1 for a in win._all_assets
                   if tag in (a.tags or "").split(","))
    got = len(win.grid.assets)
    if got != expected:
        fails += 1
        print("  !! tag %r expected %d got %d" % (tag, expected, got))
    win._set_tag_filter(tag)  # toggle off
    app.processEvents()
print("  tag filters correct:", fails == 0, "(%d failures)" % fails)

print("\n=== C) Folder selection ===")
ffail = 0
for fid in fids:
    folder = {"kind": "virtual", "id": fid}
    win._current_folder = folder
    win._active_tag = None
    win._apply_filters()
    app.processEvents()
    expected = sum(1 for (p, t) in paths if db.get_asset_folders(p))
    # count assets actually in this folder
    in_f = len(db.get_folder_assets(fid))
    got = len(win.grid.assets)
    if got != in_f:
        ffail += 1
        print("  !! folder %d expected %d got %d" % (fid, in_f, got))
    win._current_folder = None
    win._apply_filters()
    app.processEvents()
print("  folder filters correct:", ffail == 0)

print("\n=== D) No leak across 10 refreshes ===")
def chip_n():
    return sum(1 for c in win.tag_flow_widget.children()
                if c.__class__.__name__ == "QPushButton")
before = chip_n()
for _ in range(10):
    win._refresh_tag_browser(); app.processEvents()
after = chip_n()
print("  chips before=%d after=%d stable=%s" % (before, after, after <= before))

print("\n=== E) Exception check during 20 click cycles ===")
err = None
try:
    for i in range(20):
        tag = TAGS[i % len(TAGS)]
        win._set_tag_filter(tag)
        app.processEvents()
        win._set_tag_filter(tag)
        # also toggle a folder
        win._current_folder = {"kind": "virtual", "id": fids[i % 5]}
        win._apply_filters()
        app.processEvents()
        win._current_folder = None
        win._apply_filters()
        app.processEvents()
except Exception:
    err = traceback.format_exc()
print("  no exception during cycles:", err is None)
if err:
    print(err)

print("\n=== SUMMARY ===")
print("hit-test ok:", all_ok, "| tag filters ok:", fails == 0,
      "| folder ok:", ffail == 0, "| no leak:", after <= before,
      "| no exc:", err is None)
