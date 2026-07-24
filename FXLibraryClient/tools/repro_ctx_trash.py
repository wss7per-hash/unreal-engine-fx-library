# tools/repro_ctx_trash.py -- 复现「多选后右键移到回收站只删一个」的 bug
import os, sys, tempfile, time
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from PySide6.QtWidgets import QApplication, QMenu, QPoint
from PySide6.QtCore import Qt
QMenu_ori_add = QMenu.addAction
QMenu_ori_exec = QMenu.exec

import app.config as cfg
CFGDIR = tempfile.mkdtemp(prefix="fxqa_cfg_")
cfg.CONFIG_DIR = CFGDIR
cfg.CONFIG_FILE = os.path.join(cfg.CONFIG_DIR, "config.json")
cfg.DEFAULT_LIBRARY_DIR = os.path.join(cfg.CONFIG_DIR, "library")
cfg.DEFAULTS["library_dir"] = cfg.DEFAULT_LIBRARY_DIR

from app.database import Database
from app.scanner import ScannerWorker
from app.ui.main_window import MainWindow
from app import i18n

TMP = tempfile.mkdtemp(prefix="fxqa_")
SAMPLE = os.path.join(TMP, "SampleFX", "Content", "FX")
os.makedirs(SAMPLE, exist_ok=True)
def make_uasset(fname, marker):
    p = os.path.join(SAMPLE, fname)
    with open(p, "wb") as f:
        f.write(b"\x00\x01\x00\x00 header " + marker + b" tail")
    return p
for n in ("NS_A.uasset","NS_B.uasset","NS_C.uasset","NS_D.uasset","NS_E.uasset"):
    make_uasset(n, b"NiagaraSystem")

app = QApplication.instance() or QApplication(sys.argv)
app.setStyle("Fusion")
win = MainWindow()
win.show()

w = ScannerWorker(win._db_path, [SAMPLE], os.path.join(cfg.DEFAULT_LIBRARY_DIR,"thumbs"),
                 copy=False, fx_only=True)
res = {}
w.finished.connect(lambda d: res.update(d)); w.failed.connect(lambda e: res.update({"error":e}))
w.start()
deadline = time.time()+20
while not res and time.time()<deadline:
    app.processEvents(); time.sleep(0.02)

# 全选（模拟多选）
win.grid.select_all(); app.processEvents()
selected = win.grid.selected_assets()
print("selected count =", len(selected))
clicked = selected[0]

# 记录 _move_to_trash 被调用了几次、各作用于谁
trashed = []
def fake_move(asset):
    trashed.append(asset.source_path if asset else None)
win._move_to_trash = fake_move

# 捕获菜单里「移到回收站」那一项，让 menu.exec 返回它
captured = []
def patched_add(self, *a, **k):
    act = QMenu_ori_add(self, *a, **k)
    captured.append(act); return act
def patched_exec(self, *a, **k):
    want = i18n.tr("ctx_trash")
    for act in captured:
        if act.text() == want:
            return act
    return None
QMenu.addAction = patched_add
QMenu.exec = patched_exec

win._on_asset_context(clicked, QPoint(0,0))

QMenu.addAction = QMenu_ori_add
QMenu.exec = QMenu_ori_exec

print("MOVE_TO_TRASH calls =", len(trashed))
print("trashed assets      =", trashed)
print("EXPECTED (correct)  = all %d selected should be trashed" % len(selected))
if len(trashed) == 1 and trashed[0] == clicked.source_path:
    print("RESULT: BUG CONFIRMED -- 多选后右键只删除了被右击的那 1 个，其余 %d 个未删"
          % (len(selected)-1))
else:
    print("RESULT: OK -- 批量删除生效，共 %d 个" % len(trashed))
