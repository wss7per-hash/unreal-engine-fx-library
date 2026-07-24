# 决定性测试：真实点击 tag chip → handler 触发 → 网格变窄
import os, sys, tempfile, time
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtTest import QTest
from PySide6.QtCore import Qt
QMessageBox.information = lambda *a, **k: None
QMessageBox.critical = lambda *a, **k: None
import app.config as cfg
CFGDIR = tempfile.mkdtemp(prefix="fxct_")
cfg.CONFIG_DIR = CFGDIR
cfg.CONFIG_FILE = os.path.join(cfg.CONFIG_DIR, "config.json")
cfg.DEFAULT_LIBRARY_DIR = os.path.join(cfg.CONFIG_DIR, "library")
cfg.DEFAULTS["library_dir"] = cfg.DEFAULT_LIBRARY_DIR
from app.database import Database
from app.scanner import ScannerWorker
from app.ui.main_window import MainWindow

TMP = tempfile.mkdtemp(prefix="fxct_")
SAMPLE = os.path.join(TMP, "SampleFX", "Content", "FX")
os.makedirs(SAMPLE, exist_ok=True)
def make_uasset(fname, marker):
    p = os.path.join(SAMPLE, fname)
    with open(p, "wb") as f:
        f.write(b"\x00\x01\x00\x00 header " + marker + b" tail")
    return p
make_uasset("NS_Fire.uasset", b"NiagaraSystem")
make_uasset("NS_Explosion.uasset", b"NiagaraSystem")
make_uasset("PS_Smoke.uasset", b"ParticleSystem")
make_uasset("BP_FXSpawner.uasset", b"NiagaraSystem" + b"BlueprintGeneratedClass")

app = QApplication.instance() or QApplication(sys.argv)
app.setStyle("Fusion")
win = MainWindow()
win.show()

thumbs = os.path.join(cfg.DEFAULT_LIBRARY_DIR, "thumbs")
w = ScannerWorker(win._db_path, [SAMPLE], thumbs, copy=False, fx_only=True)
res = {}
w.finished.connect(lambda d: res.update(d))
w.start()
deadline = time.time() + 20
while not res and time.time() < deadline:
    app.processEvents(); time.sleep(0.02)
win._reload_library()
print("扫描资产数:", len(win._all_assets))

# 给 NS_Fire 打 "fire" 标签
db = Database(win._db_path, backup=False)
fire_path = [a.source_path for a in win._all_assets if a.name == "NS_Fire"][0]
db.set_tags(fire_path, "fire")
win._reload_library()  # 重新加载，让 tag 生效
print("reload 后资产数:", len(win._all_assets))
print("all_tags_with_counts:", win.db.all_tags_with_counts())

# 找到 "fire" 这个 tag chip
chips = [c for c in win.tag_flow_widget.children()
         if c.__class__.__name__ == "QPushButton" and "fire" in (c.text() or "").lower()]
print("找到 fire chip 数:", len(chips))
if not chips:
    print("FAIL: 找不到 fire chip — 手动定位可能没生成 chip")
    sys.exit(1)
chip = chips[0]
print("chip 文本:", repr(chip.text()), "几何:", chip.geometry().getRect(),
      "可见:", chip.isVisible(), "启用:", chip.isEnabled())

before = len(win.grid.assets)
print("点击前 grid.assets 数:", before)

# ★ 真实点击 chip 控件本身（走 QTest 的鼠标事件投递）
QTest.mouseClick(chip, Qt.LeftButton)
app.processEvents()

after = len(win.grid.assets)
print("点击后 _active_tag:", repr(win._active_tag))
print("点击后 grid.assets 数:", after)

if win._active_tag == "fire" and after < before:
    print("==> PASS: 真实点击触发了 tag 过滤，网格 %d -> %d" % (before, after))
else:
    print("==> FAIL: 真实点击未触发过滤 (_active_tag=%r, grid %d->%d)" % (
        win._active_tag, before, after))
