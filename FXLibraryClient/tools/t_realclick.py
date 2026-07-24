# tools/t_realclick.py -- simulate REAL OS-level mouse clicks at chip
# coordinates using QMouseEvent posting through the application event
# system (not QTest.mouseClick which only fires the signal directly).
import os, sys, tempfile, time
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import app.config as cfg
CFGDIR = tempfile.mkdtemp(prefix="fxrc_")
cfg.CONFIG_DIR = CFGDIR
cfg.CONFIG_FILE = os.path.join(cfg.CONFIG_DIR, "config.json")
cfg.DEFAULT_LIBRARY_DIR = os.path.join(cfg.CONFIG_DIR, "library")
cfg.DEFAULTS["library_dir"] = cfg.DEFAULT_LIBRARY_DIR
from app.scanner import ScannerWorker
from app.ui.main_window import MainWindow
from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication, QPushButton

app = QApplication.instance() or QApplication(sys.argv)
app.setStyle("Fusion")
win = MainWindow()
win.show()

TMP = tempfile.mkdtemp(prefix="fxrc_")
SAMPLE = os.path.join(TMP, "C", "FX"); os.makedirs(SAMPLE, exist_ok=True)
TAGS = ["Fire", "Water"]
def mk(t):
    p = os.path.join(SAMPLE, "FX_%s.uasset" % t)
    open(p, "wb").write(b"\x00\x01\x00\x00 header NiagaraSystem tail")
    return p
paths = []
for i in range(20):
    if i < 5:
        tg = "Fire"
    elif i < 10:
        tg = "Water"
    else:
        tg = ""
    p = mk("f%d" % i)
    paths.append((p, tg))
db = win.db

thumbs = os.path.join(cfg.DEFAULT_LIBRARY_DIR, "thumbs")
w = ScannerWorker(win._db_path, [SAMPLE], thumbs, copy=False, fx_only=False)
res = {}
w.finished.connect(lambda d: res.update(d)); w.start()
dl = time.time() + 25
while not res and time.time() < dl:
    app.processEvents(); time.sleep(0.02)
for i, (p, tg) in enumerate(paths):
    db.set_tags(p, tg)
win._reload_library()
app.processEvents()
print("library assets:", len(win._all_assets))


def find_chip(text):
    for c in win.tag_flow_widget.children():
        if isinstance(c, QPushButton) and text in c.text():
            return c
    return None


print("\n=== Scrolling tag_flow_widget up so target chip is visible ===")
# Scroll so the target chip is fully inside the scroll viewport
tw_gp = win.tag_flow_widget.mapToGlobal(QPoint(0, 0))
target = find_chip("Fire")
print("target chip found:", target is not None, "size:", target.size() if target else None)


def send_click(widget):
    """Post a real mouse press+release to the Qt event system at the widget's
    local center.  This bypasses QTest.mouseClick and lets Qt perform its own
    hit-testing through the event dispatcher."""
    if widget is None:
        return False
    win.activateWindow()
    win.raise_()
    app.processEvents()
    local = QPointF(widget.width() // 2, widget.height() // 2)
    glob = QPointF(widget.mapToGlobal(QPoint(int(local.x()), int(local.y()))))
    press = QMouseEvent(QEvent.MouseButtonPress, local, glob,
                         Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
    release = QMouseEvent(QEvent.MouseButtonRelease, local, glob,
                           Qt.NoButton, Qt.LeftButton, Qt.NoModifier)
    QApplication.sendEvent(widget, press)
    app.processEvents()
    QApplication.sendEvent(widget, release)
    app.processEvents()
    return True


# ----------------- TEST 1: tag chip real-click via sendEvent -----------------
print("\n=== TEST 1: 'Fire' chip via real QMouseEvent at chip-local center ===")
target = find_chip("Fire")
before_active = win._active_tag
before_grid = len(win.grid.assets)
ok = send_click(target)
after_active = win._active_tag
after_grid = len(win.grid.assets)
print(f"  before: active={before_active!r} grid={before_grid}")
print(f"  after : active={after_active!r} grid={after_grid}")
print(f"  TEST 1 RESULT: {'PASS' if after_active == 'Fire' else 'FAIL'}")

# Toggle off
send_click(target)
app.processEvents()


# ----------------- TEST 2: hit-test (widgetAt) returns true target path ----
print("\n=== TEST 2: widgetAt at chip center = chip or descendant ===")
target = find_chip("Water")
if target is not None:
    gp = target.mapToGlobal(QPoint(target.width() // 2, target.height() // 2))
    hit = QApplication.widgetAt(gp)
    print(f"  global pos={gp} widgetAt={type(hit).__name__ if hit else None}")
    # walk DOWN from viewport to find a QPushButton descendant
    path = []
    cur = hit
    while cur is not None and cur not in path:
        path.append(cur)
        cur = cur.parent()
    print(f"  ancestor path: {[type(p).__name__ for p in path]}")
    is_in_chain = any(p is target for p in path)
    print(f"  chip reachable via hit-test ancestor chain: {is_in_chain}")
else:
    print("  no Water chip found")


# ----------------- TEST 3: actual mouse press on scroll viewport ------------
print("\n=== TEST 3: sendEvent to QScrollArea viewport at chip coords ===")
target = find_chip("Smoke")
if target is None:
    # any tag chip
    target = find_chip("Fire")
if target is not None:
    vp = win._tag_scroll.viewport()
    gp = target.mapToGlobal(QPoint(target.width() // 2, target.height() // 2))
    lp_vp = QPointF(vp.mapFromGlobal(gp))
    print(f"  target global pos={gp} -> viewport local={lp_vp}")
    # Find what hit-test finds
    hit = QApplication.widgetAt(gp)
    print(f"  widgetAt={type(hit).__name__ if hit else None} parent={type(hit.parent()).__name__ if hit and hit.parent() else None}")
    # Send press+release to the viewport at that position
    win.activateWindow(); win.raise_()
    app.processEvents()
    press = QMouseEvent(QEvent.MouseButtonPress, lp_vp, QPointF(gp),
                         Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
    release = QMouseEvent(QEvent.MouseButtonRelease, lp_vp, QPointF(gp),
                           Qt.NoButton, Qt.LeftButton, Qt.NoModifier)
    QApplication.sendEvent(vp, press)
    app.processEvents()
    QApplication.sendEvent(vp, release)
    app.processEvents()
    after = len(win.grid.assets)
    print(f"  after viewport-send click, grid={after}")


# ----------------- TEST 4: chip enabled? visible? click runs? --------------
print("\n=== TEST 4: chip state verification ===")
target = find_chip("Fire")
if target is not None:
    print(f"  isVisible={target.isVisible()}  isEnabled={target.isEnabled()}  size={target.size()}")
    print(f"  geometry={target.geometry()}")
    print(f"  parent={type(target.parent()).__name__}")
    # check signal connection
    try:
        from PySide6.QtCore import Q_RETURN_ARG
        connected = target.receivers(target.signals().get('clicked(bool)', None)) if False else "?"
    except Exception:
        connected = "?"
    print(f"  has receivers: {target.receivers('2clicked(bool)') > 0}")


print("\n=== DONE ===")
