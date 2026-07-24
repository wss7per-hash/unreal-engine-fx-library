import os, sys, tempfile, time
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from PySide6.QtWidgets import QApplication, QMessageBox
QMessageBox.information = lambda *a, **k: None
QMessageBox.critical = lambda *a, **k: None
import app.config as cfg
CFGDIR = tempfile.mkdtemp(prefix="fxp_")
cfg.CONFIG_DIR = CFGDIR
cfg.CONFIG_FILE = os.path.join(cfg.CONFIG_DIR, "config.json")
cfg.DEFAULT_LIBRARY_DIR = os.path.join(cfg.CONFIG_DIR, "library")
cfg.DEFAULTS = cfg.DEFAULTS if hasattr(cfg,"DEFAULTS") else {}
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

tf = win.tag_flow
print("tag_flow class:", type(tf).__name__)
print("tag_flow spacing():", tf.spacing())
print("tag_flow count():", tf.count())
chips=[c for c in win.tag_flow_widget.children() if c.__class__.__name__=="QPushButton"]
print("num chip children:", len(chips))
for i,c in enumerate(chips[:6]):
    lay = c.layout()
    pl = c.parentWidget().layout()
    print("chip[%d] %r parentLay=%s ownLay=%s posInParent=(%d,%d) h=%d" % (
        i, c.text().strip(), type(pl).__name__ if pl else None,
        type(lay).__name__ if lay else None,
        c.pos().x(), c.pos().y(), c.height()))
# Is there possibly a SECOND layout on tag_flow_widget?
print("tag_flow_widget layout:", type(win.tag_flow_widget.layout()).__name__)
print("tag_flow_widget children count:", len(win.tag_flow_widget.children()))
# print ALL children types/positions
print("--- ALL children of tag_flow_widget ---")
for c in win.tag_flow_widget.children():
    print("  %s %r pos=(%d,%d) h=%d" % (type(c).__name__, getattr(c,'text',lambda:getattr(c,'objectName',lambda:'?')())(), c.pos().x(), c.pos().y(), c.height()))
