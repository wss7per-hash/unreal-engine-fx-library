import os, sys, tempfile, time
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from PySide6.QtWidgets import QApplication, QMessageBox, QSizePolicy
QMessageBox.information = lambda *a, **k: None
QMessageBox.critical = lambda *a, **k: None
import app.config as cfg
CFGDIR = tempfile.mkdtemp(prefix="fxm_")
cfg.CONFIG_DIR = CFGDIR
cfg.CONFIG_FILE = os.path.join(cfg.CONFIG_DIR, "config.json")
cfg.DEFAULT_LIBRARY_DIR = os.path.join(cfg.CONFIG_DIR, "library")
cfg.DEFAULTS["library_dir"] = cfg.DEFAULT_LIBRARY_DIR
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

chips=[c for c in win.tag_flow_widget.children() if c.__class__.__name__=="QPushButton"]
print("num chips:", len(chips))
for i,c in enumerate(chips[:4]):
    it = win.tag_flow.itemAt(i)
    ig = it.geometry() if it else None
    sp = c.sizePolicy()
    print("chip[%d] %r" % (i, c.text().strip()))
    print("   widget geom: x=%d y=%d w=%d h=%d" % (c.geometry().x(),c.geometry().y(),c.geometry().width(),c.geometry().height()))
    print("   layout item geom:", ig)
    print("   height=%d sizeHintH=%d minH=%d maxH=%d minSz=%s maxSz=%s" % (
        c.height(), c.sizeHint().height(), c.minimumHeight(), c.maximumHeight(),
        c.minimumSize(), c.maximumSize()))
    print("   vPolicy=%s hPolicy=%s" % (sp.verticalPolicy(), sp.horizontalPolicy()))
