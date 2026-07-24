import os, sys, tempfile, time
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from PySide6.QtWidgets import QApplication, QMessageBox
QMessageBox.information = lambda *a, **k: None
QMessageBox.critical = lambda *a, **k: None
import app.config as cfg
CFGDIR = tempfile.mkdtemp(prefix="fxm_")
cfg.CONFIG_DIR = CFGDIR
cfg.CONFIG_FILE = os.path.join(cfg.CONFIG_DIR, "config.json")
cfg.DEFAULT_LIBRARY_DIR = os.path.join(cfg.CONFIG_DIR, "library")
cfg.DEFAULTS = {"library_dir": cfg.DEFAULT_LIBRARY_DIR}
from app.scanner import ScannerWorker
from app.ui.main_window import MainWindow
app = QApplication.instance() or QApplication(sys.argv)
app.setStyle("Fusion")
win = MainWindow()
win.resize(1100, 760)
win.show()
app.processEvents()
db = win.db
TMP = tempfile.mkdtemp()
S = os.path.join(TMP,"C","FX"); os.makedirs(S, exist_ok=True)
for t in ["Fire","Water","Smoke","Explosion","Magic","Blood","Electric","Slash","Dust","Ice"]:
    open(os.path.join(S,"NS_%s.uasset"%t),"wb").write(b"\x00\x01\x00\x00 header NiagaraSystem tail")
thumbs=os.path.join(cfg.DEFAULT_LIBRARY_DIR,"thumbs")
w=ScannerWorker(win._db_path,[S],thumbs,copy=False,fx_only=True)
res={}
w.finished.connect(lambda d:res.update(d)); w.failed.connect(lambda e:res.update({"e":e}))
w.start()
dl=time.time()+20
while not res and time.time()<dl: app.processEvents(); time.sleep(0.02)
win._reload_library(); app.processEvents()
for i,t in enumerate(["Fire","Water","Smoke","Explosion","Magic","Blood","Electric","Slash","Dust","Ice"]):
    db.set_tags(win._all_assets[i].source_path, t)
win._reload_library(); app.processEvents()
win._refresh_tag_browser(); app.processEvents()

print("tag_flow_widget size:", win.tag_flow_widget.width(), win.tag_flow_widget.height())
print("--- ALL children positions ---")
chips = [c for c in win.tag_flow_widget.children() if c.__class__.__name__=="QPushButton"]
for i,c in enumerate(chips):
    g = c.geometry()
    overlap = False
    for j,c2 in enumerate(chips):
        if i >= j: continue
        g2 = c2.geometry()
        if g.intersects(g2):
            overlap = True
            break
    print("chip[%d] %r pos=(%d,%d) w=%d h=%d overlap=%s" % (
        i, c.text().strip() if hasattr(c,'text') and callable(c.text) else '?',
        g.x(), g.y(), g.width(), g.height(), overlap))

# Also verify spacing
print("\n--- spacing verification ---")
for i in range(len(chips)-1):
    g1 = chips[i].geometry()
    g2 = chips[i+1].geometry()
    gap = g2.y() - (g1.y() + g1.height())
    print("gap chip[%d]→[%d] = %dpx" % (i, i+1, gap))
