# app/ui/main_window.py -- the standalone FX Library client main window.
# Three-column layout mirroring the HTML prototype: left sidebar, central grid,
# right inspector. Includes light/dark theme, i18n, batch selection, lightbox.

import os
import sys
import json
import subprocess
import tempfile
import zipfile
import random
from datetime import datetime

from PySide6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                               QLabel, QLineEdit, QPushButton, QFileDialog,
                               QMessageBox, QStatusBar, QDockWidget, QMenu,
                               QInputDialog, QApplication, QComboBox, QFrame,
                               QDialog, QScrollArea, QSizePolicy, QDialogButtonBox,
                               QSplitter, QTextEdit, QGridLayout, QSpacerItem,
                               QTreeWidget, QTreeWidgetItem, QProgressDialog,
                               QProgressBar, QCheckBox, QTableWidget,
                               QTableWidgetItem, QHeaderView, QStackedWidget,
                               QAbstractItemView, QGraphicsOpacityEffect,
                               QGraphicsDropShadowEffect, QSizePolicy,
                               QListView)
from PySide6.QtCore import (Qt, QPoint, QRect, QTimer, QSize, Signal, QEvent,
                            QPropertyAnimation, QEasingCurve)
from PySide6.QtGui import (QPixmap, QIcon, QImage, QColor, QPainter, QFont,
                            QPen, QKeySequence, QShortcut)

from app import config as cfg, ue_bridge
from app import uasset_thumb
from app.database import Database
from app.models import FXAsset, FxPackEntry, TYPE_NIAGARA, TYPE_CASCADE
from app.workers import BridgeWorker
from app.scanner import ScannerWorker, EngineBackfillWorker
from app import ue_export
from app.ui.asset_grid import (AssetGrid, _crop_to_square, _placeholder,
                                 DEFAULT_CHIP, TYPE_CHIP, TIER_LABEL)
from app.ui.log_panel import LogPanel
from app.ui.settings_dialog import SettingsDialog
from app.ui.base_dialog import BaseDialog
from app.style import get_stylesheet, resolve_theme, THEMES
from app.i18n import tr, reset_language_cache
from app.icons import icon, app_icon, type_glyph_pixmap
from app.version import __version__ as _APP_VER

CONFIG_DIR = os.path.join(os.path.expanduser("~"), ".fxlibrary")

TYPE_ORDER = [TYPE_NIAGARA, TYPE_CASCADE]
FX_TYPES = {TYPE_NIAGARA, TYPE_CASCADE}
TAGS = ["Fire", "Water", "Explosion", "Magic", "Smoke", "Ice"]
TAG_COLORS = {
    "Fire": "#ff6b3d", "Water": "#3da5ff", "Explosion": "#ffb03d",
    "Magic": "#a78bfa", "Smoke": "#8b94a7", "Ice": "#7fe3ff",
}

# --------------------------------------------------------------------------
# Diagnostic logging + headless self-test (proves the frozen build's
# click->filter->grid chain works; run FXLibraryClient.exe --selftest).
# --------------------------------------------------------------------------
import datetime as _dt
_DBG_PATH = os.path.join(os.environ.get("TEMP", os.path.expanduser("~")),
                       "fxlibrary_debug.log")
def dbg(*a):
    try:
        with open(_DBG_PATH, "a", encoding="utf-8") as _f:
            _f.write("[%s] %s\n" % (
                _dt.datetime.now().strftime("%H:%M:%S.%f")[:-3],
                " ".join(str(x) for x in a)))
            _f.flush()
    except Exception:
        pass

def _self_test():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    import tempfile, time, traceback
    from PySide6.QtWidgets import QApplication as _QA
    app = _QA.instance() or _QA(sys.argv)
    from PySide6.QtTest import QTest
    from PySide6.QtCore import Qt
    import app.config as _cfg
    from app.database import Database as _DB
    from app.models import FXAsset as _FX
    dbg("=== SELFTEST START ===")
    try:
        CFGDIR = tempfile.mkdtemp(prefix="fxst_")
        _cfg.CONFIG_DIR = CFGDIR
        _cfg.CONFIG_FILE = os.path.join(CFGDIR, "config.json")
        _cfg.DEFAULT_LIBRARY_DIR = os.path.join(CFGDIR, "library")
        _cfg.DEFAULTS["library_dir"] = _cfg.DEFAULT_LIBRARY_DIR
        win = MainWindow()
        win.show()
        db = _DB(win._db_path, backup=False)
        def _mk(nm, ty, bp=False):
            p = os.path.join(CFGDIR, nm)
            return _FX(source_path=p, name=nm, type=ty,
                       class_name=ty, stored_path=p, thumb_path="",
                       size=10, imported_at="2026-01-01", source="scan",
                       blueprint=bp, has_thumb=False, tier=4)
        for a in (_mk("NS_Fire", "Niagara"),
                  _mk("NS_Exp", "Niagara"),
                  _mk("PS_Smoke", "Cascade"),
                  _mk("BP_X", "Niagara", bp=True)):
            db.upsert_asset(a)
        win._reload_library()
        fp = [a.source_path for a in win._all_assets if a.name == "NS_Fire"][0]
        db.set_tags(fp, "fire")
        win._reload_library()
        chips = [c for c in win.tag_flow_widget.children()
                 if c.__class__.__name__ == "QPushButton"
                 and "fire" in (c.text() or "").lower()]
        if not chips:
            dbg("SELFTEST FAIL: no fire chip found")
            print("SELFTEST FAIL: fire chip not found")
            return 1
        before = len(win.grid.assets)
        QTest.mouseClick(chips[0], Qt.LeftButton)
        app.processEvents()
        after = len(win.grid.assets)
        ok = (win._active_tag == "fire") and (after < before)
        dbg("SELFTEST tag=%r before=%d after=%d -> %s" % (
            win._active_tag, before, after, "PASS" if ok else "FAIL"))
        print("SELFTEST tag=%r grid %d->%d : %s" % (
            win._active_tag, before, after, "PASS" if ok else "FAIL"))
        return 0 if ok else 1
    except Exception as e:
        dbg("SELFTEST EXCEPTION:\n" + traceback.format_exc())
        print("SELFTEST EXCEPTION:", e)
        return 1
    finally:
        dbg("=== SELFTEST END ===")


# --------------------------------------------------------------------------
# Lightbox dialog
# --------------------------------------------------------------------------
class LightboxDialog(QDialog):
    def __init__(self, asset, theme, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)
        self.setModal(True)
        self.setMinimumSize(440, 540)
        self._build(asset, theme)

    def _build(self, asset, theme):
        from app.style import THEMES
        tok = THEMES.get(theme, THEMES["light"])
        self.setStyleSheet("background:%s;" % tok["overlay"])
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addStretch(1)

        card = QFrame()
        card.setStyleSheet("background:%s; border-radius:18px;" % tok["bg2"])
        cl = QVBoxLayout(card)
        cl.setContentsMargins(22, 22, 22, 22)
        cl.setSpacing(14)

        hero = QLabel()
        hero.setFixedHeight(320)
        hero.setAlignment(Qt.AlignCenter)
        pm = QPixmap()
        if asset.thumb_path and os.path.exists(asset.thumb_path):
            pm = _crop_to_square(asset.thumb_path, 360, 320)
        if pm.isNull():
            pm = _placeholder(asset.type, 360, 320)
        hero.setPixmap(pm)
        hero.setStyleSheet("border-radius:14px;")

        title = QLabel(asset.name)
        title.setStyleSheet("font-size:20px; font-weight:700; color:%s" % tok["text"])
        sub = QLabel(asset.object_path)
        sub.setStyleSheet("font-size:13px; color:%s" % tok["muted"])
        sub.setWordWrap(True)

        meta = QHBoxLayout()
        meta.setAlignment(Qt.AlignCenter)
        tier_key = getattr(asset, "tier", 1) or 1
        tier = QLabel(tr(TIER_LABEL.get(tier_key, "tier_engine")))
        tier.setStyleSheet("background:rgba(10,20,30,.55); color:#fff; border-radius:7px; padding:3px 8px; font-size:10px; font-weight:700;")
        chip = QLabel(asset.type)
        from app.ui.asset_grid import TYPE_CHIP
        tcolor, tbg = TYPE_CHIP.get(asset.type, (("#5a6b82", "rgba(90,107,130,.14)")))
        chip.setStyleSheet("background:%s; color:%s; border-radius:6px; padding:3px 9px; font-weight:600; font-size:12px" % (tbg, tcolor))
        hp = QLabel(tr("hp_" + (getattr(asset, "health", "ok") or "ok")))
        hc = {"ok": "#1aa179", "warn": "#f5a623", "bad": "#e25950"}.get(getattr(asset, "health", "ok") or "ok", "#94a3b8")
        hp.setStyleSheet("background:%s; border-radius:8px; padding:3px 10px; font-weight:700; font-size:12px" % ("rgba(26,161,121,.12)" if hc == "#1aa179" else "rgba(245,166,35,.14)" if hc == "#f5a623" else "rgba(226,89,80,.12)"))
        hp.setStyleSheet(hp.styleSheet() + "; color:%s" % hc)
        meta.addWidget(tier)
        meta.addWidget(chip)
        meta.addWidget(hp)

        cl.addWidget(hero)
        cl.addWidget(title)
        cl.addWidget(sub)
        cl.addLayout(meta)
        root.addWidget(card, alignment=Qt.AlignCenter)
        root.addStretch(1)

    def mousePressEvent(self, e):
        if not self.childAt(e.pos()):
            self.reject()
        super().mousePressEvent(e)

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Escape:
            self.reject()
        super().keyPressEvent(e)


# --------------------------------------------------------------------------
# Non-modal render result dialog (can be minimized / closed)
# --------------------------------------------------------------------------


# --------------------------------------------------------------------------
# Collapsible sidebar section (click the header to expand/collapse).
# --------------------------------------------------------------------------
class CollapsibleSection(QWidget):
    def __init__(self, title, content, extra=None, parent=None):
        super().__init__(parent)
        self._content = content
        self._collapsed = False
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        self._chev = QLabel("▾")           # ▾ expanded / ▸ collapsed
        self._chev.setObjectName("collchev")
        self._chev.setFixedWidth(14)
        self._title = QLabel(title)
        self._title.setObjectName("colltitle")

        hdr = QHBoxLayout()
        hdr.setContentsMargins(0, 0, 0, 0)
        hdr.setSpacing(6)
        hdr.addWidget(self._chev)
        hdr.addWidget(self._title)
        hdr.addStretch(1)
        # extra widgets (e.g. a clear / new-folder button) live in the header
        # but keep their own click behaviour — they don't toggle collapse.
        if extra:
            for w in extra:
                hdr.addWidget(w)
        self._header = QWidget()
        self._header.setObjectName("collheader")
        self._header.setLayout(hdr)
        self._header.setCursor(Qt.PointingHandCursor)
        self._header.mousePressEvent = lambda e: self.toggle()
        lay.addWidget(self._header)
        lay.addWidget(content, 1)

    def toggle(self):
        self.set_collapsed(not self._collapsed)

    def set_collapsed(self, c):
        self._collapsed = c
        self._chev.setText("▸" if c else "▾")
        if c:
            self._content.hide()
            # The outer sidebar QVBoxLayout gives the Folders section
            # stretch=1, so without this cap the section would still
            # claim all leftover vertical space when collapsed — leaving
            # a tall empty area below the chevron (the bug the user
            # saw in the screenshot). Cap the section's own max height
            # to the header so a collapsed section is exactly header-tall.
            self.setMaximumHeight(self._header.sizeHint().height())
        else:
            self._content.show()
            # QWIDGETSIZE_MAX == 16777215 — restore the default "no cap".
            self.setMaximumHeight(16777215)


# --------------------------------------------------------------------------
# Main window
# --------------------------------------------------------------------------
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        # Use the NATIVE window chrome (title bar / borders / resize grips).
        # The previous FramelessWindowHint + custom drag/resize logic was the
        # root cause of the filter/tag/folder click failures: intercepting
        # mouse events on the QMainWindow to fake drag/resize kept stealing
        # clicks from child widgets. Going native means the OS handles
        # move/resize flawlessly and NO click can ever be swallowed.
        # We only darken the native title bar via the Windows DWM API so it
        # still matches the dark theme (see _apply_dark_title_bar).
        self.setWindowTitle("%s v%s" % (tr("app_title"), _APP_VER))
        self.setWindowIcon(app_icon())
        self.resize(1440, 900)
        self.setMinimumSize(1100, 700)
        self.setAcceptDrops(True)

        self.cfg = cfg.load()
        self.theme = "dark"  # dark-only: no light/theme toggle
        self.lang = self.cfg.get("language", "auto")
        if self.lang not in ("zh", "en"):
            self.lang = "zh"
        self.db = self._open_db()
        # One-time migration: soft-delete any leftover blueprint records from
        # pre-ROUND-22 scans (the scanner now excludes blueprints, but old
        # data may still be in the library).  Idempotent: safe every startup.
        _bp_purged = self.db.purge_blueprints()
        if _bp_purged:
            self.log.append(tr("bp_purged", n=_bp_purged))
        self.bridge_dir = self.cfg.get("ue_bridge_dir") or None
        self._active_worker = None
        self._backfill_worker = None
        self._ue_available = False
        self._render_queue = []
        self._export_queue = []
        self._export_out_dir = self.cfg.get("library_dir") or tempfile.gettempdir()
        self._all_assets = []
        self._current_asset = None
        self._current_view = "all"
        self._active_tag = None
        self._current_cat = None
        self._current_src = "all"
        self._current_folder = None
        # View mode: icons / list / details  (Windows-Explorer style)
        self._view_mode = self.cfg.get("view_mode", "icons")
        if self._view_mode not in ("icons", "list", "details"):
            self._view_mode = "icons"
        self._icon_size = self.cfg.get("icon_size", "medium")
        if self._icon_size not in ("small", "medium", "large"):
            self._icon_size = "medium"

        self._build_ui()
        self._install_shortcuts()
        self._apply_dark_title_bar()  # native title bar -> dark (no-op off Windows)
        self._apply_theme(self.theme, save=False)
        self._refresh_ue_state()
        self._set_busy(False)
        self._reload_library()
        self._start_engine_backfill()

    def tok(self):
        """Active theme token set for the main window."""
        return THEMES.get(self.theme, THEMES["light"])

    def _start_engine_backfill(self):
        """Kick off a one-shot background backfill of ``engine_version`` for
        assets imported before the feature existed. Safe to call repeatedly
        (a no-op when nothing needs filling)."""
        try:
            needs = sum(1 for _ in self.db.iter_assets_for_engine_backfill())
        except Exception as e:
            self.log.append(tr("backfill_probe_failed"), err=str(e))
            return
        if needs <= 0:
            return
        self._backfill_worker = EngineBackfillWorker(self._db_path)
        self._backfill_worker.finished.connect(self._on_engine_backfill_done)
        self._backfill_worker.start()
        self.statusBar().showMessage(tr("backfill_started", n=needs))

    def _on_engine_backfill_done(self, info):
        """Reload the grid once the background backfill finishes so the new
        ``engine_version`` values light up the thumbnail badges."""
        self._backfill_worker = None
        filled = info.get("filled", 0)
        ue = info.get("ue", 0)
        if filled > 0:
            self._reload_library()
            self.log.append(tr("backfill_done", n=filled, ue=ue))
        self.statusBar().showMessage(tr("ready"))

    # ---------- shortcuts ----------
    def _install_shortcuts(self):
        """Keyboard shortcuts: Ctrl+A selects all visible cards, Ctrl+D clears
        selection, Delete/Backspace moves the current selection to trash.
        Text-field focus is respected so typing is never hijacked."""
        QShortcut(QKeySequence("Ctrl+A"), self).activated.connect(self._shortcut_select_all)
        QShortcut(QKeySequence("Ctrl+D"), self).activated.connect(self.grid.clear_selection)
        QShortcut(QKeySequence("Delete"), self).activated.connect(self._shortcut_delete)
        QShortcut(QKeySequence("Backspace"), self).activated.connect(self._shortcut_delete)

    @staticmethod
    def _focus_in_text():
        fw = QApplication.focusWidget()
        return isinstance(fw, (QLineEdit, QTextEdit, QComboBox))

    def _shortcut_select_all(self):
        if self._focus_in_text():
            return
        self.grid.select_all()

    def _shortcut_delete(self):
        if self._focus_in_text():
            return
        sel = self.grid.selected_assets()
        if sel:
            self._trash_assets(sel)

    # ---------- drag & drop import ----------
    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()
        else:
            e.ignore()

    def dragMoveEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()
        else:
            e.ignore()

    def dropEvent(self, e):
        urls = e.mimeData().urls()
        roots = []
        for u in urls:
            p = u.toLocalFile()
            if not p:
                continue
            if os.path.isdir(p):
                roots.append(p)
            elif p.lower().endswith(".uasset") and os.path.exists(p):
                d = os.path.dirname(p)
                if d not in roots:
                    roots.append(d)
        if not roots:
            e.ignore()
            return
        e.acceptProposedAction()
        mode = self.cfg.get("import_mode", "reference")
        self.log.append(tr("drop_import", n=len(roots)))
        self._run_scan(roots, mode)

    # ---------- setup ----------
    def _build_ui(self):
        QApplication.instance().setStyleSheet(get_stylesheet(self.theme))
        central = QWidget()
        self.setCentralWidget(central)
        vmain = QVBoxLayout(central)
        vmain.setContentsMargins(0, 0, 0, 0)
        vmain.setSpacing(0)

        # The window now uses the NATIVE title bar (which we darken via the
        # Windows DWM API in _apply_dark_title_bar).  No custom title widget
        # means the toolbar below is the first visible row — and, crucially,
        # move/resize are handled by Windows itself, so mouse clicks on the
        # filter combo, tag chips and folder tree are never intercepted.

        # ---- body columns (no top header — search/settings live in toolbar) ----
        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.setObjectName("mainsplitter")
        self.splitter.setHandleWidth(1)

        # left sidebar
        sidebar = self._build_sidebar()
        self.splitter.addWidget(sidebar)
        # main area
        main_area = self._build_main_area()
        self.splitter.addWidget(main_area)
        # right inspector
        self.inspector = self._build_inspector()
        self.splitter.addWidget(self.inspector)

        self.splitter.setSizes([240, 780, 320])
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setCollapsible(0, False)
        self.splitter.setCollapsible(2, True)  # inspector may collapse (e.g. no selection)
        vmain.addWidget(self.splitter, 1)

        # bottom log dock (hidden by default, toggled via toolbar button)
        self.log = LogPanel()
        self.log_dock = QDockWidget(tr("activity_log"), self)
        self.log_dock.setWidget(self.log)
        self.addDockWidget(Qt.BottomDockWidgetArea, self.log_dock)
        self.log_dock.setVisible(False)
        self.log_dock.visibilityChanged.connect(self._on_log_visibility_changed)

        self.setStatusBar(QStatusBar())

        # batch bar (floating, centered)
        self.batchbar = self._build_batchbar()
        vmain.addWidget(self.batchbar, alignment=Qt.AlignCenter)

        # Panel soft shadows (Stripe 柔光 layered depth — QSS box-shadow
        # is silently ignored by Qt, so we use real graphics effects).
        self._apply_soft_shadow(self.toolbar, blur=10, y_off=2, alpha=25)
        self._apply_soft_shadow(self.sidebar_frame, blur=12, y_off=0, alpha=18)
        self._apply_soft_shadow(self.inspector, blur=14, y_off=0, alpha=22)

    # ---------- native title bar: darken via Windows DWM ----------
    def _apply_dark_title_bar(self):
        """Paint the native title bar dark to match the app theme.

        We use FramelessWindowHint's opposite: a normal window with the
        OS chrome, then ask DWM (Desktop Window Manager) to render its
        title bar in dark mode.  This is the correct, robust fix for the
        old white-title-bar complaint — and, unlike a custom frameless
        title bar, it never interferes with child-widget mouse events.
        """
        try:
            import ctypes
            from ctypes import c_int, byref, sizeof
            hwnd = int(self.winId())
        except Exception:
            return
        try:
            dwm = ctypes.windll.dwmapi
        except Exception:
            return
        # 20 = DWMWA_USE_IMMERSIVE_DARK_MODE (Win10 1809+)
        # 38 = Win11 dark-title-bar attribute (same effect, newer builds)
        value = c_int(1)
        for attr in (20, 38):
            try:
                dwm.DwmSetWindowAttribute(
                    hwnd, attr, byref(value), sizeof(value))
            except Exception:
                pass

    def showEvent(self, e):
        """Once the native window exists, ask DWM to darken its title bar."""
        super().showEvent(e)
        self._apply_dark_title_bar()

    def _build_sidebar(self):
        from app.style import THEMES
        tok = THEMES.get(self.theme, THEMES["light"])
        frame = QFrame()
        frame.setObjectName("sidebar")
        self.sidebar_frame = frame
        frame.setFixedWidth(240)
        outer = QVBoxLayout(frame)
        outer.setContentsMargins(12, 14, 12, 14)
        outer.setSpacing(0)

        # ---- Eagle-style library selector (single clean row) ----
        lib_row = QHBoxLayout()
        lib_row.setContentsMargins(0, 0, 0, 0)
        lib_row.setSpacing(0)

        self.lib_btn = QPushButton()
        self.lib_btn.setObjectName("libbtn")
        self.lib_btn.setText(" " + tr("my_library"))
        self.lib_btn.setIcon(icon("library", size=14))
        self.lib_btn.setIconSize(QSize(14, 14))
        self.lib_btn.setLayoutDirection(Qt.RightToLeft)
        self.lib_btn.setCursor(Qt.PointingHandCursor)
        self.lib_btn.clicked.connect(self._show_library_menu)
        self._round_button(self.lib_btn)
        lib_row.addWidget(self.lib_btn)
        outer.addLayout(lib_row)
        outer.addSpacing(12)

        # ---- Brand + stats hero card (fills the former top dead-zone;
        #      adds product identity + at-a-glance library stats) ----
        hero = QFrame()
        hero.setObjectName("sidehero")
        hero.setCursor(Qt.PointingHandCursor)
        hero.setToolTip(tr("hero_tip"))
        hero.mousePressEvent = lambda e: self._set_view("all")
        hv = QVBoxLayout(hero)
        hv.setContentsMargins(14, 12, 14, 12)
        hv.setSpacing(8)
        htop = QHBoxLayout()
        htop.setSpacing(8)
        self.hero_mono = QLabel("FX")
        self.hero_mono.setObjectName("heromono")
        htop.addWidget(self.hero_mono)
        htop.addStretch(1)
        self.hero_lib = QLabel(tr("my_library"))
        self.hero_lib.setObjectName("herolib")
        htop.addWidget(self.hero_lib)
        hv.addLayout(htop)
        self.hero_stat = QLabel("0")
        self.hero_stat.setObjectName("herostat")
        hv.addWidget(self.hero_stat)
        self.hero_sub = QLabel(tr("hero_assets"))
        self.hero_sub.setObjectName("herosuB")
        hv.addWidget(self.hero_sub)
        self.hero_meta = QLabel("")
        self.hero_meta.setObjectName("herometa")
        hv.addWidget(self.hero_meta)
        # Hero is a STAT card, not a flex spacer — pin it to a sane fixed
        # height so that when the three collapsible sections below are all
        # collapsed (folders.maxHeight == headerHeight) the leftover
        # vertical space in the sidebar outer layout doesn't get re-distributed
        # proportionally to all widgets (which used to blow hero up to fill
        # the entire sidebar height, pushing the chevrons/trash down).
        hero.setMaximumHeight(140)
        hero.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        outer.addWidget(hero)
        outer.addSpacing(12)

        # ---- Filters / Tags / Folders as independently collapsible sections ----
        self._build_tag_browser()
        outer.addWidget(self.filter_section)
        outer.addWidget(self.tag_section)

        # Folders (Eagle-style user-created folders) — collapsible
        self.btn_new_folder = QPushButton()
        self.btn_new_folder.setObjectName("iconghost")
        self.btn_new_folder.setIcon(icon("plus", size=14))
        self.btn_new_folder.setIconSize(QSize(14, 14))
        self.btn_new_folder.setFixedSize(24, 24)
        self.btn_new_folder.setToolTip(tr("new_folder"))
        self.btn_new_folder.setCursor(Qt.PointingHandCursor)
        self.btn_new_folder.clicked.connect(self._create_virtual_folder)
        self.folder_tree = self._build_folder_tree()
        self.folder_section = CollapsibleSection(
            tr("folders"), self.folder_tree, [self.btn_new_folder])
        # No stretch=1 here on purpose: a stretch on folder_section used to
        # blow out the hero card above when all sections were collapsed.
        # Instead the leftover space goes to the addStretch(1) below the
        # folder section, which pins the trash to the bottom and keeps the
        # hero card a fixed height.
        outer.addWidget(self.folder_section)

        # ---- Trash pinned at bottom, separated by a divider so it reads as a footer ----
        outer.addStretch(1)
        outer.addSpacing(6)
        footer_sep = QFrame()
        footer_sep.setObjectName("seph")
        outer.addWidget(footer_sep)
        outer.addSpacing(6)
        self.nav_trash = self._nav_btn(tr("trash"), "trash", lambda: self._set_view("trash"))
        outer.addWidget(self.nav_trash)

        # (Only Trash is left as a special nav destination now that the
        # tag/smart-folder/management sections were removed.)
        self._nav_map = {
            "trash": self.nav_trash,
            "has_thumb": self.nav_thumb,
            "no_thumb": self.nav_nothumb,
            "fav": self.nav_fav,
        }
        self._sync_nav()
        self._refresh_sidebar_stats()
        return frame

    def _make_chip_scroll(self, widget):
        """Build a chip scroll area that hosts a manually-positioned flow."""
        scroll = QScrollArea()
        scroll.setObjectName("tagscroll")
        scroll.setWidgetResizable(False)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setWidget(widget)
        return scroll

    def _build_tag_browser(self):
        """Build the two collapsible sidebar sections — Filters (smart-filter
        chips) and Tags (real DB tags) — and store them on self so _build_sidebar
        can lay them out. Sections are: self.filter_section / self.tag_section.
        """
        # ---- Filters content (smart-filter chips) ----
        self.filter_flow_widget = QWidget()
        self.filter_scroll = self._make_chip_scroll(self.filter_flow_widget)
        self.filter_section = CollapsibleSection(tr("filters"), self.filter_scroll, None)

        # ---- Tags content (real DB tags) ----
        self.tag_flow_widget = QWidget()
        self.tag_scroll = self._make_chip_scroll(self.tag_flow_widget)
        self.tag_clear_btn = QPushButton()
        self.tag_clear_btn.setObjectName("iconghost")
        self.tag_clear_btn.setIcon(icon("close", size=12))
        self.tag_clear_btn.setIconSize(QSize(12, 12))
        self.tag_clear_btn.setFixedSize(22, 22)
        self.tag_clear_btn.setToolTip(tr("clear_tag_filter"))
        self.tag_clear_btn.setCursor(Qt.PointingHandCursor)
        self.tag_clear_btn.clicked.connect(lambda _c: self._set_tag_filter(None))
        self.tag_clear_btn.setVisible(False)
        self.tag_section = CollapsibleSection(tr("tags"), self.tag_scroll, [self.tag_clear_btn])
        # Keep a reference so the refresh path can read the viewport width.
        self._tag_scroll = self.tag_scroll
        self._refresh_tag_browser()

    def _refresh_tag_browser(self):
        """Repopulate the Filters and Tags sidebar flows from the DB.

        Chips are positioned *manually* with setGeometry() instead of using
        any layout.  QVBoxLayout combined with QSS `min-height` and
        setFixedHeight() produced chip slots that were SHORTER than the
        rendered widget height, so chips overlapped vertically and a real
        mouse click landed on the neighbour instead of the intended tag —
        which made tags, folders, and filters all appear "broken".  Manual
        positioning guarantees every chip occupies exactly its own vertical
        band with zero overlap.
        """
        ffw = getattr(self, "filter_flow_widget", None)
        tfw = getattr(self, "tag_flow_widget", None)
        if ffw is None or tfw is None:
            return
        # Reset the chip lookup so _update_nav_checked() always points at
        # the LIVE chips (the old ones are removed/recreated just below).
        self._tag_chips = {}

        # --- clear all old widgets from both flows ---
        for tw in (ffw, tfw):
            for c in list(tw.children()):
                c.setParent(None)
                c.deleteLater()

        # Always use the scroll viewport's width.  Using the flow widget's own
        # width() was unreliable — without a layout the widget defaults to ~640
        # which is wider than the sidebar, so chips extended into the main grid
        # area and AssetCards there painted on top of them, intercepting clicks.
        _scroll = getattr(self, "_tag_scroll", None)
        FW = _scroll.viewport().width() if _scroll else 240
        if FW < 80:
            FW = 240

        # Chip height is observed to be 38px by QSS #nav (padding 5px + icon 14 +
        # font 12.5px).  Hardcode to that so we don't have to call
        # QApplication.processEvents() inside a click handler.
        CHIP_H = 38
        SPACING = 6

        def _place(w, tw, y, h=None):
            """Place widget w at (0, y) with width FW and given/measured height;
            returns the next y."""
            if h is None:
                h = w.sizeHint().height() or w.height() or CHIP_H
            if h < 10:
                h = CHIP_H
            w.setParent(tw)
            w.setGeometry(0, y, FW, h)
            w.show()
            return y + h + SPACING

        # --- Filters flow: smart-filter chips (thumbnails / favs / untagged) ---
        yf = [0]

        def _make_filter(text, icon_name, view_key):
            chip = QPushButton(icon(icon_name, size=14), " " + text)
            chip.setObjectName("nav")
            chip.setCheckable(True)
            chip.setCursor(Qt.PointingHandCursor)
            chip.setEnabled(True)
            chip.setFocusPolicy(Qt.NoFocus)
            chip.setChecked(self._current_view == view_key)
            chip.clicked.connect(lambda checked, k=view_key: (
                self._set_view(k) if checked else self._clear_smart_filter()
            ))
            yf[0] = _place(chip, ffw, yf[0], CHIP_H)
            return chip

        self.nav_thumb = _make_filter(tr("has_thumb"), "thumbnail", "has_thumb")
        self.nav_nothumb = _make_filter(tr("no_thumb"), "no_thumb", "no_thumb")
        self.nav_fav = _make_filter(tr("favorites"), "fav", "fav")
        ffw.setFixedSize(FW, yf[0])

        # --- Tags flow: real DB tags ---
        yt = 0
        tags = self.db.all_tags_with_counts()
        if not tags:
            hint = QLabel(tr("no_tags_hint"))
            hint.setObjectName("taghint")
            hint.setWordWrap(True)
            yt = _place(hint, tfw, yt, 40)
            self.tag_clear_btn.setVisible(False)
            tfw.setFixedSize(FW, yt)
            return

        for tag, count in tags:
            chip = QPushButton(icon("tag", size=14), " " + tag)
            chip.setObjectName("nav")
            chip.setCheckable(True)
            chip.setCursor(Qt.PointingHandCursor)
            chip.setEnabled(True)
            chip.setFocusPolicy(Qt.NoFocus)
            chip.setToolTip("%s · %d %s" % (tag, count, tr("tag_count_suffix")))
            chip.setChecked(self._active_tag == tag)
            chip.clicked.connect(lambda _checked, t=tag: self._set_tag_filter(t))
            yt = _place(chip, tfw, yt, CHIP_H)
            self._tag_chips[tag] = chip

        self.tag_clear_btn.setVisible(bool(self._active_tag))
        tfw.setFixedSize(FW, yt)

    def _size_tag_flow_to_content(self):
        # Kept as no-op stub; manual positioning handles sizing inline now.
        pass

    def _refresh_grid(self):
        """Apply current filters and repaint the grid.

        Safe to call directly from any click handler. Any exception is logged
        to the diagnostic file instead of being swallowed, so a future
        failure is never silent again.
        """
        try:
            self._apply_filters()
        except Exception as e:
            import traceback as _tb
            dbg("ERR _apply_filters: %r\n%s" % (e, _tb.format_exc()))

    def _update_nav_checked(self):
        """Toggle only the checked-state of existing sidebar chips — no rebuild.

        Rebuilding the whole tag browser on every click (DB query +
        recreating every chip) was the real root cause of "click does nothing
        until I click a toolbar widget": it blocked the event loop for
        seconds, starving the deferred _apply_filters() and the grid repaint.
        This path is O(#chips) and instant, and never touches the DB.
        """
        for t, chip in getattr(self, "_tag_chips", {}).items():
            try:
                chip.setChecked(t == self._active_tag)
            except Exception:
                pass
        # Map view key -> chip attribute name. NOTE: the chip attributes are
        # `nav_thumb` / `nav_nothumb` / `nav_fav` (not `nav_has_thumb` /
        # `nav_no_thumb`), so the previous `getattr(self, "nav_" + k)` lookup
        # silently missed nav_thumb and nav_nothumb, leaving them stuck
        # checked after the user switched to another chip.
        _smart_chip_attr = {"has_thumb": "nav_thumb", "no_thumb": "nav_nothumb", "fav": "nav_fav"}
        for k, attr in _smart_chip_attr.items():
            chip = getattr(self, attr, None)
            if chip is not None:
                try:
                    chip.setChecked(self._current_view == k)
                except Exception:
                    pass
        try:
            self.tag_clear_btn.setVisible(bool(self._active_tag))
        except Exception:
            pass
        try:
            self._sync_nav()
        except Exception as e:
            dbg("ERR _sync_nav: %r" % e)

    def _set_tag_filter(self, tag):
        """Toggle the active tag filter and re-apply the grid filters."""
        dbg("TAG_CLICK tag=%r (was %r)" % (tag, getattr(self, "_active_tag", None)))
        if self._active_tag == tag:
            self._active_tag = None
        else:
            self._active_tag = tag
        self._current_view = "all"
        self._current_cat = None
        self._current_folder = None
        self.folder_tree.clearSelection()
        # Lightweight: only toggle checked-state of the existing chips.
        # Rebuilding the ENTIRE sidebar here (DB query + recreating every
        # chip) blocked the event loop for seconds and starved the grid
        # repaint — which is why clicks "did nothing" until a toolbar
        # widget was clicked. We never rebuild on a plain click anymore.
        self._update_nav_checked()
        self._refresh_grid()

    def _refresh_sidebar_stats(self):
        """Keep the brand/stat hero card in sync with the loaded library."""
        assets = list(getattr(self, "_all_assets", []) or [])
        total = len(assets)
        fav = sum(1 for a in assets if getattr(a, "favorite", False))
        self.hero_stat.setText(str(total))
        self.hero_sub.setText(tr("hero_assets"))
        self.hero_meta.setText("★ %d" % fav)

    def _show_library_menu(self):
        """Eagle-style: clicking the library name shows a small menu
        (library settings, switch library, etc.)."""
        menu = QMenu(self.lib_btn)
        menu.addAction(icon("settings", size=14), " " + tr("settings_short"),
                       self._open_settings)
        menu.addAction(icon("folder", size=14), " " + tr("select_scan_root"),
                       self._auto_scan)
        menu.exec(self.lib_btn.mapToGlobal(QPoint(0, self.lib_btn.height())))

    def _open_about(self):
        from app.ui.about_dialog import AboutDialog
        AboutDialog(self).exec()

    def _open_settings(self):
        from app.ui.settings_dialog import SettingsDialog
        from app.style import resolve_theme
        old_theme = self.theme
        old_lang = self.lang
        dlg = SettingsDialog(self)
        if dlg.exec():
            self.cfg = cfg.load()
            if self.cfg.get("library_dir"):
                try:
                    self.db = self._open_db()
                    _bp = self.db.purge_blueprints()
                    if _bp:
                        self.log.append(tr("bp_purged", n=_bp))
                except Exception as e:
                    self.log.append(tr("db_reopen_warning"), err=e)
            self._refresh_ue_state()
            # Apply theme/language immediately — they used to require a restart,
            # which felt like "nothing happened" after saving in Settings.
            new_lang = self.cfg.get("language", "auto")
            if new_lang in ("zh", "en") and new_lang != old_lang:
                self._set_language(new_lang)
            new_theme = resolve_theme(self.cfg.get("theme", "auto"))
            if new_theme != old_theme:
                self._apply_theme(new_theme, save=False)
            self._reload_library()

    def _toggle_log_dock(self, checked=None):
        if checked is None:
            checked = not self.log_dock.isVisible()
        self.log_dock.setVisible(checked)

    def _on_log_visibility_changed(self, visible):
        if self.btn_log:
            self.btn_log.setChecked(visible)

    # (Resource community entry point intentionally omitted — see audit report
    # P1: it was an unimplemented "coming soon" dead-end with no caller.)

    def _nav_title(self, text):
        lbl = QLabel(text)
        lbl.setObjectName("navtitle")
        return lbl

    def _nav_btn(self, text, icon_name, callback):
        btn = QPushButton(icon(icon_name, size=16), " " + text)
        btn.setObjectName("nav")
        btn.setCheckable(True)
        btn.setLayoutDirection(Qt.LeftToRight)
        btn.clicked.connect(callback)
        self._round_button(btn)
        return btn

    def _refresh_folder_tree(self):
        self.folder_tree.clear()
        folders = self.db.get_folders()
        if not folders:
            hint = QTreeWidgetItem(self.folder_tree)
            hint.setText(0, tr("no_virtual_folders"))
            hint.setData(0, Qt.UserRole, {"kind": "hint"})
            hint.setFlags(hint.flags() & ~Qt.ItemIsSelectable & ~Qt.ItemIsEnabled)
            return

        folder_items = {}
        for f in folders:
            f_item = QTreeWidgetItem()
            f_item.setText(0, f["name"])
            f_item.setData(0, Qt.UserRole, {"kind": "virtual", "id": f["id"]})
            f_item.setIcon(0, icon("folder", size=14))
            f_item.setToolTip(0, f["name"])
            folder_items[f["id"]] = f_item
        for f in folders:
            item = folder_items[f["id"]]
            parent_id = f.get("parent_id")
            if parent_id and parent_id in folder_items:
                folder_items[parent_id].addChild(item)
            else:
                self.folder_tree.addTopLevelItem(item)
        self.folder_tree.expandAll()

    def _on_folder_selected(self, item, column):
        data = item.data(0, Qt.UserRole) or {}
        dbg("FOLDER_CLICK data=%r" % (data,))
        if data.get("kind") == "hint":
            return
        # Toggle off when clicking the already selected folder
        if self._current_folder and self._current_folder.get("id") == data.get("id"):
            self.folder_tree.clearSelection()
            self._current_folder = None
            self._current_view = "all"
            self._current_cat = None
            self._update_nav_checked()
            self._refresh_grid()
            return
        self._current_folder = data
        self._current_view = "all"
        self._current_cat = None
        self._active_tag = None
        self._update_nav_checked()
        self._refresh_grid()

    def _deselect_folder(self):
        """Clear folder selection and return to the All view."""
        if (not self._current_folder
                and self._current_view == "all" and not self._current_cat):
            return
        self.folder_tree.clearSelection()
        self._current_folder = None
        self._current_view = "all"
        self._current_cat = None
        self._active_tag = None
        self._update_nav_checked()
        self._refresh_grid()

    def _on_folder_tree_context(self, pos):
        item = self.folder_tree.itemAt(pos)
        data = item.data(0, Qt.UserRole) if item else {}
        kind = data.get("kind") if data else None

        menu = QMenu(self.folder_tree)
        from app.style import THEMES
        tok = THEMES.get(self.theme, THEMES["light"])
        menu.setStyleSheet(
            "QMenu { background: %s; border: 1px solid %s; border-radius: 8px; padding: 6px; color: %s; }"
            "QMenu::separator { background: %s; height: 1px; margin: 4px 8px; }"
            "QMenu::item { padding: 7px 18px 7px 12px; border-radius: 6px; }"
            "QMenu::item:selected { background: %s; color: #fff; }"
            "QMenu::item:disabled { color: %s; }" % (
                tok["bg2"], tok["border"], tok["text"], tok["border"],
                tok["accent"], tok["muted2"]
            )
        )
        a_new = menu.addAction(icon("plus", size=14), tr("new_folder"))
        a_new.triggered.connect(self._create_virtual_folder)
        if kind == "virtual":
            a_del = menu.addAction(icon("trash", size=14), tr("delete_folder"))
            a_del.triggered.connect(lambda: self._delete_virtual_folder(data.get("id")))
            a_rename = menu.addAction(tr("rename_folder"))
            a_rename.triggered.connect(lambda: self._rename_virtual_folder(data.get("id")))
        menu.exec(self.folder_tree.mapToGlobal(pos))

    def _create_virtual_folder(self):
        name, ok = QInputDialog.getText(self, tr("new_folder"), tr("new_folder_name"))
        if not ok or not name.strip():
            return
        parent_id = None
        item = self.folder_tree.currentItem()
        if item:
            data = item.data(0, Qt.UserRole) or {}
            if data.get("kind") == "virtual":
                parent_id = data.get("id")
        self.db.add_folder(name.strip(), parent_id=parent_id, virtual=1)
        self._refresh_folder_tree()

    def _delete_virtual_folder(self, folder_id):
        if folder_id is None:
            return
        reply = QMessageBox.question(self, tr("delete_folder"),
                                     tr("delete_folder_confirm"),
                                     QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            self.db.delete_folder(folder_id)
            if self._current_folder and self._current_folder.get("id") == folder_id:
                self._current_folder = None
                self._apply_filters()
            self._refresh_folder_tree()

    def _rename_virtual_folder(self, folder_id):
        if folder_id is None:
            return
        name, ok = QInputDialog.getText(self, tr("rename_folder"), tr("new_folder_name"))
        if not ok or not name.strip():
            return
        self.db.rename_folder(folder_id, name.strip())
        self._refresh_folder_tree()

    def _add_asset_to_folder(self, source_path, folder_id):
        self.db.add_asset_to_folder(source_path, folder_id)
        self._folder_asset_cache.pop(source_path, None)
        if self._current_folder and self._current_folder.get("id") == folder_id:
            self._apply_filters()

    def _sync_nav(self):
        in_folder = bool(self._current_folder)
        in_cat = bool(self._current_cat)
        for k, btn in self._nav_map.items():
            btn.setChecked(k == self._current_view)
        for k, btn in getattr(self, "view_seg_btns", {}).items():
            btn.setChecked(k == self._current_view and not in_folder
                           and not in_cat)

    def _build_folder_tree(self):
        from app.style import THEMES
        tok = THEMES.get(self.theme, THEMES["light"])

        class _FolderTree(QTreeWidget):
            def __init__(self, win, *a, **k):
                super().__init__(*a, **k)
                self._win = win

            def mousePressEvent(self, e):
                # Clicking empty area of the tree clears the current selection
                if e.button() == Qt.LeftButton and self.itemAt(e.pos()) is None:
                    self._win._deselect_folder()
                super().mousePressEvent(e)

        tree = _FolderTree(self)
        tree.setObjectName("foldertree")
        tree.setHeaderHidden(True)
        tree.setRootIsDecorated(True)
        tree.setIndentation(14)
        tree.setAnimated(True)
        tree.setSelectionMode(QTreeWidget.SingleSelection)
        tree.setContextMenuPolicy(Qt.CustomContextMenu)
        tree.customContextMenuRequested.connect(self._on_folder_tree_context)
        tree.itemClicked.connect(self._on_folder_selected)
        # styling is owned by the global #foldertree rule in style.py —
        # any inline setStyleSheet here would freeze the build-time theme
        # and override the active token set on theme switch.
        tree.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        tree.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        # Fill the folder pane; internal scrollbar appears if many folders.
        tree.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        return tree

    def _build_main_area(self):
        frame = QFrame()
        frame.setStyleSheet("background:transparent;")
        v = QVBoxLayout(frame)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)

        # toolbar: row 1 = primary actions + view switch, row 2 = filter combos.
        # Splitting into two rows keeps the controls readable and prevents the
        # segment buttons from being squeezed under the combos when the window
        # is narrow.
        tb = QFrame()
        tb.setObjectName("toolbar")
        tb_layout = QVBoxLayout(tb)
        tb_layout.setContentsMargins(0, 0, 0, 0)
        tb_layout.setSpacing(0)
        tb_actions = QHBoxLayout()
        tb_actions.setContentsMargins(14, 8, 14, 4)
        tb_actions.setSpacing(10)
        tb_filters = QHBoxLayout()
        tb_filters.setContentsMargins(14, 4, 14, 8)
        tb_filters.setSpacing(10)

        # Add button (moved from sidebar to match Eagle's top-bar action pattern)
        # Uses the global #primary style (tokenized) — no inline QSS so it stays
        # in sync with the active theme.
        self.btn_add = QPushButton(icon("plus", size=16), " " + tr("scan_dir"))
        self.btn_add.setObjectName("toolbarprimary")
        self.btn_add.setFixedHeight(32)
        self.btn_add.setCursor(Qt.PointingHandCursor)
        self.btn_add.setToolTip(tr("scan_dir_tip"))
        self.btn_add.clicked.connect(self._add_folder)
        self._round_button(self.btn_add)
        tb_actions.addWidget(self.btn_add)
        tb_actions.addWidget(self._sep())  # cluster: primary action | library ops

        # One-click read embedded thumbnails for all current assets
        self.btn_read_thumbs = QPushButton(icon("thumbnail", size=16), " " + tr("read_thumbs"))
        self.btn_read_thumbs.setObjectName("act")
        self.btn_read_thumbs.setFixedHeight(32)
        self.btn_read_thumbs.setCursor(Qt.PointingHandCursor)
        self.btn_read_thumbs.setToolTip(tr("read_thumbs_tip"))
        self.btn_read_thumbs.clicked.connect(self._read_all_embedded_thumbs)
        self._round_button(self.btn_read_thumbs)
        tb_actions.addWidget(self.btn_read_thumbs)

        # Export selected assets as a portable .fxpack (self-contained archive)
        self.btn_export_fxpack = QPushButton(icon("box", size=16), " " + tr("exp_fxpack"))
        self.btn_export_fxpack.setObjectName("act")
        self.btn_export_fxpack.setFixedHeight(32)
        self.btn_export_fxpack.setCursor(Qt.PointingHandCursor)
        self.btn_export_fxpack.setToolTip(tr("exp_fxpack"))
        self.btn_export_fxpack.clicked.connect(self._export_fxpack_selected)
        self._round_button(self.btn_export_fxpack)
        tb_actions.addWidget(self.btn_export_fxpack)

        # One-click library health check (missing files / duplicate names)
        self.btn_health = QPushButton(icon("health", size=16), " " + tr("health_check"))
        self.btn_health.setObjectName("act")
        self.btn_health.setFixedHeight(32)
        self.btn_health.setCursor(Qt.PointingHandCursor)
        self.btn_health.setToolTip(tr("health_check"))
        self.btn_health.clicked.connect(self._run_health_scan)
        self._round_button(self.btn_health)
        tb_actions.addWidget(self.btn_health)
        tb_actions.addWidget(self._sep())  # cluster: library ops | search

        # separator: action cluster | search + settings
        tb_actions.addWidget(self._sep())

        # search bar (moved from removed top header into toolbar row 1)
        self.search = QLineEdit()
        self.search.setPlaceholderText(tr("search_ph"))
        self.search.setClearButtonEnabled(True)
        self.search.setMinimumWidth(200)
        self.search.setMaximumWidth(360)
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(250)
        self._search_timer.timeout.connect(self._apply_filters)
        self.search.textChanged.connect(self._on_search_changed)
        self._round_lineedit(self.search)
        self.search.setFixedHeight(32)
        tb_actions.addWidget(self.search, 1)

        # settings button
        self.btn_settings = QPushButton()
        self.btn_settings.setObjectName("icon")
        self.btn_settings.setIcon(icon("settings", size=18))
        self.btn_settings.setFixedSize(32, 32)
        self.btn_settings.clicked.connect(self._open_settings)
        self._round_button(self.btn_settings)
        tb_actions.addWidget(self.btn_settings)

        # about button
        self.btn_about = QPushButton()
        self.btn_about.setObjectName("icon")
        self.btn_about.setIcon(icon("info", size=18))
        self.btn_about.setFixedSize(32, 32)
        self.btn_about.setToolTip(tr("about_title"))
        self.btn_about.clicked.connect(self._open_about)
        self._round_button(self.btn_about)
        tb_actions.addWidget(self.btn_about)

        tb_actions.addStretch(1)

        # Filters (row 2)
        self.type_combo = QComboBox()
        self.type_combo.addItem(tr("f_type"), "")
        for t in TYPE_ORDER:
            self.type_combo.addItem(t, t)
        self.type_combo.currentIndexChanged.connect(self._apply_filters)
        self.src_combo = QComboBox()
        self.src_combo.setToolTip(tr("f_source_tip"))
        self.src_combo.addItem(tr("src_all"), "all")
        self.src_combo.addItem(tr("src_pure"), "pure")
        self.src_combo.currentIndexChanged.connect(self._apply_filters)
        self.sort_combo = QComboBox()
        self.sort_combo.addItem(tr("s_name"), "name")
        self.sort_combo.addItem(tr("s_type"), "type")
        self.sort_combo.addItem(tr("s_date"), "date")
        self.sort_combo.addItem(tr("s_size"), "size")
        self.sort_combo.addItem(tr("s_rating"), "rating")
        self.sort_combo.addItem(tr("s_random"), "random")
        self.sort_combo.currentIndexChanged.connect(self._apply_filters)
        # view mode (Windows-Explorer style): Icons / List / Details
        self.view_combo = QComboBox()
        for _k, _lbl in (("icons", tr("vm_icons")), ("list", tr("vm_list")),
                        ("details", tr("vm_details"))):
            self.view_combo.addItem(_lbl, _k)
        self.view_combo.setCurrentIndex(
            max(0, self.view_combo.findData(self._view_mode)))
        self.view_combo.currentIndexChanged.connect(
            lambda: self._on_view_mode_changed(self.view_combo.currentData()))
        # icon-size sub-selector (only meaningful in Icons mode)
        self.size_combo = QComboBox()
        for _k, _lbl in (("small", tr("vm_small")), ("medium", tr("vm_medium")),
                        ("large", tr("vm_large"))):
            self.size_combo.addItem(_lbl, _k)
        self.size_combo.setCurrentIndex(
            max(0, self.size_combo.findData(self._icon_size)))
        self.size_combo.currentIndexChanged.connect(self._on_icon_size_changed)
        # make the filter combos share width equally (F4: no more lopsided dropdowns)
        self._filter_combos = []
        for _c in (self.type_combo, self.src_combo, self.sort_combo,
                   self.view_combo, self.size_combo):
            _c.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            _c.setMinimumWidth(90)
            self._round_combo(_c)
            self._filter_combos.append(_c)
        tb_filters.addWidget(self.type_combo)
        tb_filters.addWidget(self.src_combo)
        tb_filters.addWidget(self.sort_combo)
        tb_filters.addWidget(self.view_combo)
        tb_filters.addWidget(self.size_combo)
        tb_filters.addStretch(1)
        tb_filters.addWidget(self._sep())  # cluster: filters | tools

        # UE Bridge log toggle (default hidden, click to show)
        self.btn_log = QPushButton()
        self.btn_log.setObjectName("icon")
        self.btn_log.setCheckable(True)
        self.btn_log.setChecked(False)
        self.btn_log.setIcon(icon("terminal", size=18))
        self.btn_log.setIconSize(QSize(18, 18))
        self.btn_log.setFixedSize(30, 30)
        self.btn_log.setToolTip(tr("toggle_log"))
        self.btn_log.clicked.connect(self._toggle_log_dock)
        self._round_button(self.btn_log)
        tb_filters.addWidget(self.btn_log)

        tb_layout.addLayout(tb_actions)
        tb_layout.addLayout(tb_filters)
        tb.setMinimumHeight(76)
        self.toolbar = tb
        v.addWidget(self.toolbar)

        # section head
        head = QFrame()
        head.setStyleSheet("background:transparent;")
        hl = QHBoxLayout(head)
        hl.setContentsMargins(16, 10, 16, 4)
        self.section_title = QLabel(tr("all_fx"))
        self.section_title.setObjectName("section")
        self.section_count = QLabel("")
        self.section_count.setObjectName("count")
        hl.addWidget(self.section_title)
        hl.addWidget(self.section_count)
        # View segmented control (All / Favorites / Recent) — inline with the
        # current view's header so it reads as a per-view filter, not chrome.
        self._build_view_segment(hl)
        hl.addStretch(1)

        # Selection controls moved to the top toolbar (next to Scan) so this
        # header stays to just title + count + view segment. They remain always
        # visible for select-without-batch-bar workflows.
        self.sel_hint_lbl = QLabel(tr("sel_hint"))
        self.sel_hint_lbl.setObjectName("selhint")
        self.sel_hint_lbl.setVisible(False)  # hidden until a selection exists
        hl.addWidget(self.sel_hint_lbl)

        v.addWidget(head)

        # grid (icons / list modes)
        self.grid = AssetGrid()
        self.grid.set_theme(self.theme)
        self.grid.asset_activated.connect(self._on_asset_activated)
        self.grid.asset_context.connect(self._on_asset_context)
        self.grid.reveal_requested.connect(self._open_location)
        self.grid.selection_changed.connect(self._on_selection_changed)
        self.grid.empty_action.connect(self._add_folder)
        self.grid.fav_changed.connect(self._on_grid_fav_changed)
        # details table (Windows-Explorer style: columns)
        self.details_table = self._build_details_table()
        # stacked: page0 = grid, page1 = details table
        self.content_stack = QStackedWidget()
        self.content_stack.addWidget(self.grid)
        self.content_stack.addWidget(self.details_table)
        # initial page + grid view-mode from saved config
        if self._view_mode == "details":
            self.content_stack.setCurrentWidget(self.details_table)
        else:
            self.content_stack.setCurrentWidget(self.grid)
            self.grid.view_mode = "list" if self._view_mode == "list" else self._icon_size
        v.addWidget(self.content_stack, 1)

        return frame

    def _build_view_segment(self, layout):
        """Top-bar segmented view switch: All / Favorites / Recent.
        Clicking the already-active segment turns it off and returns to All."""
        seg = QFrame()
        seg.setObjectName("segctl")
        seg.setMinimumWidth(220)
        segl = QHBoxLayout(seg)
        segl.setContentsMargins(0, 0, 0, 0)
        segl.setSpacing(0)
        self.view_seg_btns = {}
        for key, label, ic in (("all", tr("all_fx"), "grid"),
                                ("fav", tr("favorites"), "fav"),
                                ("recent", tr("recent"), "recent")):
            b = QPushButton(icon(ic, size=15), " " + label)
            b.setObjectName("seg")
            b.setIconSize(QSize(15, 15))
            b.setCheckable(True)
            b.setFixedHeight(32)
            b.clicked.connect(lambda _c, k=key: self._on_seg_clicked(k))
            self._round_button(b)
            self.view_seg_btns[key] = b
            segl.addWidget(b)
        layout.addWidget(seg)
        # Sync the segment to the current view on build. _sync_nav() (invoked
        # from _set_view) keeps it in step with the sidebar nav buttons.
        for k, b in self.view_seg_btns.items():
            b.setChecked(k == self._current_view)

    def _on_seg_clicked(self, key):
        """Toggle behavior: clicking the active segment returns to All."""
        in_folder = bool(self._current_folder)
        in_cat = bool(self._current_cat)
        if self._current_view == key and not in_folder and not in_cat:
            self._set_view("all")
        else:
            self._set_view(key)

    def _act_btn(self, text, icon_name, callback, primary=False):
        btn = QPushButton(icon(icon_name, size=16), " " + text)
        btn.setObjectName("primary" if primary else "act")
        btn.setFixedHeight(32)
        btn.clicked.connect(callback)
        self._round_button(btn)
        return btn

    def _sep(self):
        """Vertical cluster separator — slightly taller for breathing room."""
        s = QFrame()
        s.setObjectName("sep")
        s.setFixedSize(1, 28)
        return s

    def _build_inspector(self):
        from app.style import THEMES
        frame = QScrollArea()
        frame.setWidgetResizable(True)
        frame.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        # min-width 0 (not 280) so the auto-collapse actually reaches 0 instead
        # of leaving a blank 280px panel (F9).
        frame.setMinimumWidth(0)
        frame.setStyleSheet("background:transparent; border:none;")
        self._insp_row_labels = []
        w = QWidget()
        w.setMinimumWidth(260)
        w.setStyleSheet("background:transparent;")
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)

        # hero
        self.insp_hero = QLabel()
        self.insp_hero.setFixedHeight(170)
        self.insp_hero.setAlignment(Qt.AlignCenter)
        self.insp_hero.setObjectName("insphero")
        # border color comes from the #insphero QSS rule (tokenized) so it
        # stays correct in both themes — previously hardcoded #e6e9ef (white
        # line in dark mode).
        self.insp_hero.setStyleSheet("")
        self.insp_hero.mouseDoubleClickEvent = lambda e: self._open_lightbox(self._current_asset)
        v.addWidget(self.insp_hero)

        # pad
        pad = QWidget()
        pl = QVBoxLayout(pad)
        pl.setContentsMargins(16, 16, 16, 22)
        pl.setSpacing(14)

        self.insp_title = QLabel(tr("no_asset"))
        self.insp_title.setObjectName("title")
        self.insp_title.setWordWrap(True)
        pl.addWidget(self.insp_title)

        self.insp_path = QLabel("")
        self.insp_path.setObjectName("subtitle")
        self.insp_path.setWordWrap(True)
        pl.addWidget(self.insp_path)

        # type row
        self.insp_type_row = self._insp_row(tr("type_label"))
        self.insp_type_chip = QLabel("—")
        self.insp_type_row.addWidget(self.insp_type_chip)
        self.insp_bp_chip = QLabel(tr("bp_badge"))
        self.insp_bp_chip.setObjectName("inspbpchip")
        self.insp_bp_chip.setToolTip(tr("bp_tip"))
        self.insp_bp_chip.setVisible(False)
        self.insp_type_row.addWidget(self.insp_bp_chip)
        self.insp_type_row.addStretch(1)
        pl.addLayout(self.insp_type_row)

        # health (populated by the "资产体检" scan; defaults to ok)
        self.insp_health_row = self._insp_row(tr("insp_health"))
        self.insp_health_lbl = QLabel("—")
        self.insp_health_lbl.setObjectName("insphp")
        self.insp_health_row.addWidget(self.insp_health_lbl)
        self.insp_health_row.addStretch(1)
        pl.addLayout(self.insp_health_row)

        # tags
        self.insp_tags_row = self._insp_row(tr("insp_tags"))
        pl.addLayout(self.insp_tags_row)
        self.insp_tags_flow = QHBoxLayout()
        self.insp_tags_flow.setSpacing(6)
        pl.addLayout(self.insp_tags_flow)
        self.insp_tag_input = QLineEdit()
        self.insp_tag_input.setObjectName("taginput")
        self.insp_tag_input.setPlaceholderText(tr("add_tag_ph"))
        self.insp_tag_input.setFixedHeight(30)
        self.insp_tag_input.returnPressed.connect(self._add_tag)
        self._round_lineedit(self.insp_tag_input)
        pl.addWidget(self.insp_tag_input)

        # rating
        self.insp_rating_row = self._insp_row(tr("insp_rating"))
        self.insp_rating = QHBoxLayout()
        self.insp_rating.setSpacing(2)
        self.insp_stars = []
        for i in range(5):
            s = QPushButton("☆")
            s.setObjectName("star")
            s.setFixedSize(28, 28)
            s.setCursor(Qt.PointingHandCursor)
            s.clicked.connect(lambda _c, idx=i + 1: self._set_rating(idx))
            self.insp_stars.append(s)
            self.insp_rating.addWidget(s)
        self.insp_rating.addStretch(1)
        self.insp_rating_row.addLayout(self.insp_rating)
        pl.addLayout(self.insp_rating_row)

        # note — give it a clear, helpful placeholder and a taller
        # height so it reads as an editable input (not a tiny "…" box).
        self.insp_note_row = self._insp_row(tr("insp_note"))
        pl.addLayout(self.insp_note_row)
        self.insp_note = QTextEdit()
        self.insp_note.setObjectName("inspnote")
        self.insp_note.setFixedHeight(100)
        self.insp_note.setPlaceholderText(tr("insp_note_ph"))
        self.insp_note.textChanged.connect(self._on_note_changed)
        pl.addWidget(self.insp_note)

        # ---- inspector action buttons (single column, all the same width) ----
        # Previously a QGridLayout mixed 2-col rows with 1-col rows which read
        # as "messy" once the panel got narrow. Single column is consistent
        # and matches the file/folder/source rows above.
        self.insp_open = QPushButton("  " + tr("open_location_btn"))
        self.insp_open.setObjectName("secondary")
        self.insp_open.setIcon(icon("open", THEMES.get(self.theme, THEMES["light"])["text"], 14))
        self.insp_open.setIconSize(QSize(14, 14))
        self.insp_open.clicked.connect(lambda: self._open_location(self._current_asset))
        self.insp_open.setToolTip(tr("open_location_btn"))
        pl.addWidget(self.insp_open)
        self.insp_copy = QPushButton("  " + tr("copy_path_btn"))
        self.insp_copy.setObjectName("secondary")
        self.insp_copy.setIcon(icon("copy", THEMES.get(self.theme, THEMES["light"])["text"], 14))
        self.insp_copy.setIconSize(QSize(14, 14))
        self.insp_copy.clicked.connect(lambda: self._copy_path(self._current_asset))
        pl.addWidget(self.insp_copy)

        # favorite + thumbnail (both #secondary so they get the same look
        # as open/copy above)
        self.insp_fav = QPushButton("  " + tr("add_fav"))
        self.insp_fav.setObjectName("secondary")
        self.insp_fav.setIcon(icon("fav", THEMES.get(self.theme, THEMES["light"])["text"], 14))
        self.insp_fav.setIconSize(QSize(14, 14))
        self.insp_fav.clicked.connect(self._insp_toggle_fav)
        pl.addWidget(self.insp_fav)
        self.insp_set = QPushButton("  " + tr("set_thumb"))
        self.insp_set.setObjectName("secondary")
        self.insp_set.setIcon(icon("thumbnail", THEMES.get(self.theme, THEMES["light"])["text"], 14))
        self.insp_set.setIconSize(QSize(14, 14))
        self.insp_set.clicked.connect(lambda: self._set_manual_thumb(self._current_asset))
        pl.addWidget(self.insp_set)

        # export-to-UE + export-fxpack keep the gradient CTA look (#inspexp),
        # import uses #secondary so the gradient isn't repeated 3x.
        self.insp_exp = QPushButton("⤓ " + tr("exp_ue"))
        self.insp_exp.setObjectName("inspexp")
        self.insp_exp.clicked.connect(lambda: self._export_one(self._current_asset))
        pl.addWidget(self.insp_exp)
        self.insp_pack = QPushButton("⤓ " + tr("exp_fxpack"))
        self.insp_pack.setObjectName("inspexp")
        self.insp_pack.clicked.connect(lambda: self._export_fxpack_one(self._current_asset))
        pl.addWidget(self.insp_pack)
        self.insp_imp = QPushButton("⤒ " + tr("imp_pack"))
        self.insp_imp.setObjectName("secondary")
        self.insp_imp.clicked.connect(self._import)
        pl.addWidget(self.insp_imp)

        pl.addStretch(1)
        v.addWidget(pad)
        frame.setWidget(w)
        self._show_empty_inspector()
        return frame

    def _insp_row(self, label):
        from app.style import THEMES
        tok = THEMES.get(self.theme, THEMES["light"])
        row = QHBoxLayout()
        row.setSpacing(8)
        row.setAlignment(Qt.AlignLeft)
        lbl = QLabel(label)
        lbl.setStyleSheet("color:%s; font-size:12px; text-transform:uppercase; letter-spacing:.5px; min-width:60px;" % tok["muted2"])
        row.addWidget(lbl)
        self._insp_row_labels.append(lbl)
        return row

    def _show_empty_inspector(self):
        from app.style import THEMES
        tok = THEMES.get(self.theme, THEMES["light"])
        self.insp_hero.setPixmap(QPixmap())
        self.insp_hero.setStyleSheet("background:%s; border-bottom:1px solid %s;" % (tok["bg"], tok["border"]))
        self.insp_title.setText(tr("no_asset"))
        self.insp_path.clear()
        self.insp_type_chip.setText("—")
        self.insp_type_chip.setStyleSheet("color:%s;" % tok["muted2"])
        self.insp_bp_chip.setVisible(False)
        self.insp_health_lbl.setText("—")
        self.insp_health_lbl.setStyleSheet("color:%s;" % tok["muted2"])
        self._refresh_stars(0)
        self._clear_layout(self.insp_tags_flow)
        self.insp_note.clear()
        for w in (self.insp_fav, self.insp_set, self.insp_exp, self.insp_pack,
                  self.insp_imp, self.insp_open, self.insp_copy):
            w.setEnabled(False)

    def _clear_layout(self, layout):
        # Detach children IMMEDIATELY via setParent(None) BEFORE deleteLater.
        # Relying on deleteLater() alone leaks: PyQt keeps the C++ object
        # alive (and thus a child of the parent widget) when a Python
        # reference or the parent still holds it, so the old widgets pile up
        # as orphaned children across repeated refreshes -> the sidebar's
        # tag/folder area grows unbounded and pushes real controls out of
        # view. setParent(None) removes them from parent.children()
        # synchronously, which is what actually stops the leak.
        while layout.count():
            item = layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()
            else:
                sub = item.layout()
                if sub is not None:
                    self._clear_layout(sub)

    def _build_batchbar(self):
        from app.style import THEMES
        tok = THEMES.get(self.theme, THEMES["light"])
        bar = QFrame()
        bar.setObjectName("batchbar")
        bar.setVisible(False)
        bar.setFixedHeight(48)
        bar.setMinimumWidth(520)
        bar.setMaximumWidth(720)
        hl = QHBoxLayout(bar)
        hl.setContentsMargins(12, 6, 12, 6)
        hl.setSpacing(0)

        # Left: selected count badge + label (kept as one visual unit)
        left = QHBoxLayout()
        left.setSpacing(8)
        left.setAlignment(Qt.AlignVCenter)
        self.batch_count = QLabel("0")
        self.batch_count.setObjectName("batchcount")
        self.batch_label = QLabel(tr("selected_suffix"))
        self.batch_label.setObjectName("subtitle")
        left.addWidget(self.batch_count)
        left.addWidget(self.batch_label)
        left.addStretch(1)

        # Right: action buttons (consistent height / radius)
        right = QHBoxLayout()
        right.setSpacing(8)
        right.setAlignment(Qt.AlignVCenter)

        self.b_select_all = self._batch_btn(tr("sel_all"))
        self.b_select_all.clicked.connect(self._on_select_all)
        self.b_invert = self._batch_btn(tr("sel_invert"))
        self.b_invert.clicked.connect(self._on_invert_selection)
        self.b_export = self._batch_btn("⤓ " + tr("batch_export"), primary=True)
        self.b_export.clicked.connect(self._export_selected)
        self.b_trash = self._batch_btn(tr("batch_trash"), danger=True)
        self.b_trash.clicked.connect(
            lambda: self._trash_assets(self.grid.selected_assets()))
        self.b_clear = self._batch_btn(tr("clear_sel"))
        self.b_clear.clicked.connect(self.grid.clear_selection)
        self.b_restore = self._batch_btn(tr("restore_sel"))
        self.b_restore.clicked.connect(self._restore_selected)
        self.b_delete_perm = self._batch_btn(tr("delete_perm_sel"), danger=True)
        self.b_delete_perm.clicked.connect(self._permanently_delete_selected)
        self.b_empty_trash = self._batch_btn(tr("empty_trash"), danger=True)
        self.b_empty_trash.clicked.connect(self._empty_trash)

        self.b_restore.hide()
        self.b_delete_perm.hide()
        self.b_empty_trash.hide()
        self.b_trash.hide()

        right.addWidget(self.b_select_all)
        right.addWidget(self.b_invert)
        right.addWidget(self.b_export)
        right.addWidget(self.b_trash)
        right.addWidget(self.b_restore)
        right.addWidget(self.b_delete_perm)
        right.addWidget(self.b_clear)
        right.addWidget(self.b_empty_trash)

        hl.addLayout(left, 1)
        hl.addLayout(right, 0)

        # D-3 micro-interaction: fade + slide the batch bar in when a
        # selection appears (Qt QSS has no `transition`, so animate directly).
        self._batch_opacity = QGraphicsOpacityEffect(bar)
        self._batch_opacity.setOpacity(1.0)
        bar.setGraphicsEffect(self._batch_opacity)
        self._batch_fade = QPropertyAnimation(self._batch_opacity, b"opacity", self)
        self._batch_fade.setDuration(180)
        self._batch_fade.setEasingCurve(QEasingCurve.OutCubic)
        return bar

    def _animate_batchbar_in(self):
        """Fade the batch bar from transparent to solid on appearance."""
        if not hasattr(self, "_batch_fade"):
            return
        self._batch_fade.stop()
        self._batch_fade.setStartValue(0.0)
        self._batch_fade.setEndValue(1.0)
        self._batch_fade.start()

    # ---- Panel soft shadows (Qt QSS box-shadow is silently ignored) ----
    def _apply_soft_shadow(self, widget, blur=12, y_off=2, alpha=35,
                           color=None):
        """Attach a real QGraphicsDropShadowEffect to a panel frame.
        Gives the 'Stripe 柔光' layered depth that QSS cannot provide."""
        eff = QGraphicsDropShadowEffect(widget)
        eff.setBlurRadius(float(blur))
        eff.setXOffset(0.0)
        eff.setYOffset(float(y_off))
        if color is None:
            color = QColor(10, 37, 64, alpha) if self.theme == "light" else QColor(0, 0, 0, alpha * 3)
        eff.setColor(color)
        widget.setGraphicsEffect(eff)

    def _round_combo(self, combo):
        """Force rounded corners + themed popup on a QComboBox.

        On Windows (even with Fusion style), the global QSS border-radius is
        often ignored by the native combo-box paint engine.  Applying a
        direct stylesheet with *all* sub-controls styled inline works
        around this — the per-widget setStyleSheet takes priority over
        the global sheet and forces the custom paint path.

        Colors are resolved from self.tok() so the combo adapts to the
        active light/dark theme instead of being locked to dark values.
        """
        t = self.tok()
        view = QListView(combo)
        combo.setView(view)

        # --- Style the list view inside the popup ---
        view.setStyleSheet(f"""
            QListView {{
                background: {t["input_bg"]};
                color: {t["text"]};
                border: 1px solid {t["border"]};
                border-radius: 8px;
                padding: 4px;
                outline: none;
            }}
            QListView::item {{
                padding: 6px 10px;
                border-radius: 4px;
            }}
            QListView::item:selected {{
                background: {t["accent"]};
                color: #ffffff;
            }}
            QListView::item:hover {{
                background: {t["accent_tint"]};
            }}
        """)
        combo.setStyleSheet(f"""
            QComboBox {{
                background: {t["input_bg"]};
                border: 1px solid {t["border"]};
                border-radius: 8px;
                padding: 6px 10px;
                min-height: 30px;
                color: {t["text"]};
            }}
            QComboBox:hover {{
                border: 1px solid {t["accent"]};
            }}
            QComboBox:focus {{
                border: 1px solid {t["accent"]};
            }}
            QComboBox::drop-down {{
                border: none;
                border-top-right-radius: 8px;
                border-bottom-right-radius: 8px;
                width: 24px;
            }}
            QComboBox::down-arrow {{
                image: none;
                border-left: 5px solid transparent;
                border-right: 5px solid transparent;
                border-top: 6px solid {t["muted"]};
                margin-right: 8px;
            }}
            QComboBox QAbstractItemView {{
                background: {t["input_bg"]};
                color: {t["text"]};
                border: 1px solid {t["border"]};
                border-radius: 8px;
                selection-background-color: {t["accent"]};
                selection-color: #ffffff;
                padding: 4px;
            }}
        """)

        # --- Style the POPUP CONTAINER (removes white window frame) ---
        # The QComboBox popup is a separate top-level window (container).
        # On Windows it gets a native light/white frame unless we override.
        _container_ss = (
            f"* {{ background: {t['input_bg']}; border: 1px solid {t['border']}; border-radius: 8px; }}"
        )

        def _style_container():
            try:
                v = combo.view()
                if not v:
                    return
                c = v.parentWidget()
                if c:
                    c.setStyleSheet(_container_ss)
                    c.setWindowFlags(Qt.Popup | Qt.FramelessWindowHint)
                    c.setAttribute(Qt.WA_TranslucentBackground, False)
            except (RuntimeError, AttributeError):
                pass  # C++ object may be temporarily unavailable

        # Re-style on every show (container is created lazily by Qt)
        _orig_showEvent = getattr(combo, "_orig_showEvent", combo.showEvent)

        def _hooked_show(e):
            _orig_showEvent(e)
            QTimer.singleShot(0, _style_container)

        combo.showEvent = _hooked_show  # type: ignore[method-assign]
        combo._orig_showEvent = _orig_showEvent  # type: ignore[attr-defined]

    def _round_button(self, btn):
        """Force rounded corners on a QPushButton.

        Belt-and-suspenders: even though the global QSS has border-radius,
        Windows Fusion style can clip or ignore it for certain widget states.
        A per-widget setStyleSheet with explicit border-radius guarantees
        the rounded appearance. Includes explicit border to prevent global
        QSS QPushButton#objectName rules from overriding due to selector
        specificity.
        """
        obj_name = btn.objectName()
        # Preserve objectName-specific styling by reading current text/color hints
        curr = btn.styleSheet() or ""
        if "border-radius" in curr:
            return  # already has explicit rounding
        # Use full border+radius declaration so global #primary / #act rules
        # (which match by objectName ID selector) cannot override the radius.
        btn.setStyleSheet("border: 1px solid rgba(255,255,255,.08); border-radius: 8px;")

    def _round_lineedit(self, edit):
        """Force rounded corners on a QLineEdit (search box / tag input).

        Uses self.tok() so the background adapts to light/dark theme.
        """
        t = self.tok()
        edit.setFixedHeight(36)
        edit.setStyleSheet(f"""
            background: {t["input_bg"]};
            border: 1px solid {t["border"]};
            border-radius: 8px;
            padding: 4px 10px;
            color: {t["text"]};
        """)

    def _batch_btn(self, text, primary=False, danger=False):
        btn = QPushButton(text)
        btn.setFixedHeight(32)
        btn.setCursor(Qt.PointingHandCursor)
        if primary:
            btn.setObjectName("batchbtnprimary")
        elif danger:
            btn.setObjectName("batchbtndanger")
        else:
            btn.setObjectName("batchbtn")
        self._round_button(btn)
        return btn

    # ---------- helpers ----------
    def _open_db(self):
        lib = self.cfg.get("library_dir")
        db_dir = lib if lib else CONFIG_DIR
        self._db_path = os.path.join(db_dir, "fxlibrary.db")
        return Database(self._db_path)

    def _refresh_ue_state(self):
        """Silently detect whether a local UnrealEditor is available (used for
        optional UE-bridge operations). Auto-probes common install paths."""
        self._ue_available = bool(ue_bridge.find_ue_editor(""))

    def _set_busy(self, busy, msg=""):
        for w in (self.btn_add, self.search,
                  self.btn_settings):
            w.setEnabled(not busy)
        if busy:
            self.statusBar().showMessage(msg or tr("working"))
        else:
            self.statusBar().showMessage(msg or tr("ready"))
            self._refresh_ue_state()

    # ---------- theme / language ----------
    # Theme toggle removed — app is dark-only.
    def _apply_theme(self, theme, save=False):
        self.theme = theme
        qapp = QApplication.instance()
        # Clear first then re-set so every widget gets re-polished against the
        # new token set. Without the empty setStyleSheet round-trip, widgets
        # that already have an inline stylesheet (or that were created before
        # the QSS change) keep the previous theme's colors — which is why
        # the main window stayed light while a freshly-opened dialog rendered
        # dark, or vice versa.
        qapp.setStyleSheet("")
        qapp.setStyleSheet(get_stylesheet(theme))
        # Belt-and-suspenders: re-polish every visible top-level window so
        # cached style state on its child widgets also refreshes.
        for w in qapp.topLevelWidgets():
            if w.isVisible():
                w.style().unpolish(w)
                w.style().polish(w)
                w.update()
        self.grid.set_theme(theme)
        # Re-apply panel shadows with updated colors for the new theme
        self._apply_soft_shadow(self.toolbar, blur=10, y_off=2, alpha=25)
        self._apply_soft_shadow(self.sidebar_frame, blur=12, y_off=0, alpha=18)
        self._apply_soft_shadow(self.inspector, blur=14, y_off=0, alpha=22)
        # Re-apply direct combo-box rounded styles (per-widget setStyleSheet
        # is NOT updated by the global qapp.setStyleSheet round-trip).
        for _c in getattr(self, "_filter_combos", []):
            self._round_combo(_c)
        # Re-apply search box + inspector tag input rounded styles (cleared
        # by global QSS reset — per-widget setStyleSheet is NOT auto-updated).
        self._round_lineedit(self.search)
        if hasattr(self, "insp_tag_input"):
            self._round_lineedit(self.insp_tag_input)
        # details table reads its palette via the global #detailstable token
        self._update_insp_row_labels()
        if self._current_asset:
            self._show_inspector(self._current_asset)
        else:
            self._show_empty_inspector()
        if save:
            self.cfg["theme"] = theme
            cfg.save(self.cfg)

    def _update_insp_row_labels(self):
        from app.style import THEMES
        tok = THEMES.get(self.theme, THEMES["light"])
        for lbl in getattr(self, "_insp_row_labels", []):
            lbl.setStyleSheet("color:%s; font-size:12px; text-transform:uppercase; letter-spacing:.5px; min-width:60px;" % tok["muted2"])

    def _toggle_language(self):
        new_lang = "en" if self.lang == "zh" else "zh"
        self._set_language(new_lang)

    def _set_language(self, lang):
        if self.lang == lang:
            return
        self.lang = lang
        self.cfg["language"] = lang
        cfg.save(self.cfg)
        reset_language_cache()
        self._retranslate_ui()

    def _retranslate_ui(self):
        self.setWindowTitle("%s v%s" % (tr("app_title"), _APP_VER))
        # search (lives in toolbar row 1 now)
        self.search.setPlaceholderText(tr("search_ph"))
        # toolbar (filters + selection controls; the Scan/Add button is top-left)
        # filter combos
        self.type_combo.setItemText(0, tr("f_type"))
        self.src_combo.setItemText(0, tr("src_all"))
        self.src_combo.setItemText(1, tr("src_pure"))
        self.src_combo.setToolTip(tr("f_source_tip"))
        self.sort_combo.setItemText(0, tr("s_name"))
        self.sort_combo.setItemText(1, tr("s_type"))
        self.sort_combo.setItemText(2, tr("s_date"))
        self.sort_combo.setItemText(3, tr("s_size"))
        self.sort_combo.setItemText(4, tr("s_rating"))
        self.sort_combo.setItemText(5, tr("s_random"))
        self.view_combo.setItemText(0, tr("vm_icons"))
        self.view_combo.setItemText(1, tr("vm_list"))
        self.view_combo.setItemText(2, tr("vm_details"))
        self.size_combo.setItemText(0, tr("vm_small"))
        self.size_combo.setItemText(1, tr("vm_medium"))
        self.size_combo.setItemText(2, tr("vm_large"))
        # section
        self._update_section_head(list(self.grid.assets))
        # sidebar nav (only Trash left; tag/smart-folder/management sections removed)
        self.lib_btn.setText(" " + tr("my_library"))
        self.nav_trash.setText(" " + tr("trash"))
        # Nav/filter chips are rebuilt by _refresh_tag_browser() on language switch;
        # these setattr calls are a lightweight fallback for text-only refresh.
        if hasattr(self, "nav_thumb"):
            self.nav_thumb.setText(" " + tr("has_thumb"))
        if hasattr(self, "nav_nothumb"):
            self.nav_nothumb.setText(" " + tr("no_thumb"))
        if hasattr(self, "nav_fav"):
            self.nav_fav.setText(" " + tr("favorites"))
        self.btn_add.setText(" " + tr("scan_dir"))
        if hasattr(self, "btn_about"):
            self.btn_about.setToolTip(tr("about_title"))
        if hasattr(self, "btn_read_thumbs"):
            self.btn_read_thumbs.setText(" " + tr("read_thumbs"))
            self.btn_read_thumbs.setToolTip(tr("read_thumbs_tip"))
        # top view segmented control
        if hasattr(self, "view_seg_btns"):
            self.view_seg_btns["all"].setText(" " + tr("all_fx"))
            self.view_seg_btns["fav"].setText(" " + tr("favorites"))
            self.view_seg_btns["recent"].setText(" " + tr("recent"))
        self._refresh_folder_tree()
        # inspector labels (must match the 4 rows actually built: type / tags / rating / note)
        # 5 rows now (health added at position 2). Keep this list in
        # lockstep with the row build order in _build_inspector.
        labels = [tr("type_label"), tr("insp_health"), tr("insp_tags"),
                 tr("insp_rating"), tr("insp_note")]
        for lbl, text in zip(getattr(self, "_insp_row_labels", []), labels):
            lbl.setText(text)
        self.insp_fav.setText(("★ " if getattr(self._current_asset, "favorite", False) else "☆ ") + tr("add_fav"))
        self.insp_set.setText(tr("set_thumb"))
        self.insp_exp.setText("⤓ " + tr("exp_ue"))
        self.insp_imp.setText("⤒ " + tr("imp_pack"))
        # batch bar
        self.batch_label.setText(tr("selected_suffix"))
        # dock / status
        self.log_dock.setWindowTitle(tr("activity_log"))
        self.statusBar().showMessage(tr("ready"))
        self._refresh_ue_state()
        # refresh current inspector content
        if self._current_asset:
            self._show_inspector(self._current_asset)
        else:
            self._show_empty_inspector()

    def _sync_lang_buttons(self):
        pass

    # ---------- details (table) view ----------
    def _build_details_table(self):
        """Windows-Explorer style details table: one row per asset,
        columns = Name / Type / Tags / Size / Source / Rating."""
        tbl = QTableWidget(0, 6)
        tbl.setObjectName("detailstable")
        tbl.setSelectionBehavior(QAbstractItemView.SelectRows)
        tbl.setSelectionMode(QAbstractItemView.SingleSelection)
        tbl.setEditTriggers(QAbstractItemView.NoEditTriggers)
        tbl.verticalHeader().setVisible(False)
        tbl.setSortingEnabled(True)
        tbl.setAlternatingRowColors(True)
        # Right-click context menu
        tbl.setContextMenuPolicy(Qt.CustomContextMenu)
        tbl.customContextMenuRequested.connect(self._on_details_context)
        # Keyboard: Enter to open asset in UE
        tbl.itemDoubleClicked.connect(self._on_details_double)

        hdr = tbl.horizontalHeader()
        hdr.setSectionsClickable(True)
        hdr.setHighlightSections(True)
        hdr.setSortIndicatorShown(True)
        # Column resize modes — all Interactive so user can drag-resize
        hdr.setSectionResizeMode(0, QHeaderView.Interactive)   # Name
        hdr.setSectionResizeMode(1, QHeaderView.Interactive)   # Type
        hdr.setSectionResizeMode(2, QHeaderView.Interactive)   # Tags
        hdr.setSectionResizeMode(3, QHeaderView.Interactive)   # Size
        hdr.setSectionResizeMode(4, QHeaderView.Interactive)   # Source
        hdr.setSectionResizeMode(5, QHeaderView.Interactive)   # Rating
        # Sensible initial widths (user can drag to resize)
        tbl.setColumnWidth(0, 260)  # Name — widest
        tbl.setColumnWidth(1, 90)   # Type
        tbl.setColumnWidth(2, 160)  # Tags
        tbl.setColumnWidth(3, 80)   # Size
        tbl.setColumnWidth(4, 70)   # Source
        tbl.setColumnWidth(5, 90)   # Rating
        # Minimum widths so columns don't collapse
        tbl.horizontalHeader().setMinimumSectionSize(50)
        # Name column should stretch if there's extra space
        hdr.setStretchLastSection(False)

        # headers (set again in _retranslate_ui / set on populate)
        tbl.setHorizontalHeaderLabels([
            tr("dt_name"), tr("dt_type"), tr("dt_tags"),
            tr("dt_size"), tr("dt_source"), tr("dt_rating"),
        ])
        tbl.currentItemChanged.connect(self._on_details_current_changed)
        self._details_assets = []
        self._details_row_sel = -1
        return tbl

    def _populate_details(self, assets):
        tbl = self.details_table
        tbl.setHorizontalHeaderLabels([
            tr("dt_name"), tr("dt_type"), tr("dt_tags"),
            tr("dt_size"), tr("dt_source"), tr("dt_rating"),
        ])
        # Block signals to prevent sort-triggered redraws during populate → much faster
        tbl.blockSignals(True)
        tbl.setSortingEnabled(False)
        tbl.setRowCount(len(assets))
        self._details_assets = list(assets)
        prev_sel = self._details_row_sel
        for i, a in enumerate(assets):
            name = QTableWidgetItem(a.name)
            name.setData(Qt.UserRole, a.source_path)
            tbl.setItem(i, 0, name)
            tbl.setItem(i, 1, QTableWidgetItem(a.type or tr("uncategorized")))
            tags = (getattr(a, "tags", "") or "").strip()
            tbl.setItem(i, 2, QTableWidgetItem(tags if tags else "—"))
            sz = getattr(a, "size", 0) or 0
            tbl.setItem(i, 3, QTableWidgetItem(self._fmt_size(sz)))
            src = getattr(a, "source", "scan") or "scan"
            tbl.setItem(i, 4, QTableWidgetItem(tr("src_pure") if src == "scan" else tr("imported")))
            rating = getattr(a, "rating", 0) or 0
            tbl.setItem(i, 5, QTableWidgetItem("★" * rating + "☆" * (5 - rating) if rating else "—"))
        # Fixed row height — avoids expensive resizeRowsToContents() on every populate
        tbl.verticalHeader().setDefaultSectionSize(32)
        # Re-enable sorting and signals after data is in
        tbl.setSortingEnabled(True)
        tbl.blockSignals(False)
        # restore prior selection if still present
        if 0 <= prev_sel < len(assets):
            self._details_row_sel = prev_sel
            tbl.selectRow(prev_sel)

    @staticmethod
    def _fmt_size(n):
        if n >= 1024 * 1024:
            return "%.1f MB" % (n / (1024 * 1024))
        if n >= 1024:
            return "%.1f KB" % (n / 1024)
        return "%d B" % n

    def _details_asset_at(self, row):
        """Look up the asset behind a details-table row.

        Sort-safe: after the user sorts the table, the visual row order no
        longer matches `self._details_assets`, so we must resolve the asset
        via the source_path stored in column 0's UserRole rather than by index.
        """
        if not (0 <= row < self.details_table.rowCount()):
            return None
        item = self.details_table.item(row, 0)
        if item is None:
            return None
        sp = item.data(Qt.UserRole)
        for a in self._details_assets:
            if a.source_path == sp:
                return a
        return None

    def _on_details_current_changed(self, current, _previous):
        """Row selection changed via click or keyboard in details table."""
        if current is None:
            return
        a = self._details_asset_at(current.row())
        if a is None:
            return
        self._details_row_sel = current.row()
        self._current_asset = a
        self._show_inspector(a)
        # mirror selection into the grid (so batch bar / fav stay in sync)
        self.grid.select_only(a)

    def _on_details_context(self, pos):
        """Right-click context menu on details table — reuses the grid's context handler."""
        item = self.details_table.itemAt(pos)
        if item is None:
            return
        row = item.row()
        asset = self._details_asset_at(row)
        if asset is None:
            return
        # Select the right-clicked row if not already selected
        self.details_table.selectRow(row)
        self._details_row_sel = row
        # Map table-local pos to global for menu placement
        global_pos = self.details_table.viewport().mapToGlobal(pos)
        self._on_asset_context(asset, global_pos)

    def _on_details_double(self, item):
        a = self._details_asset_at(item.row())
        if a is None:
            return
        self._on_asset_activated(a)

    # ---------- navigation / filtering ----------
    def _set_view(self, view):
        self._current_view = view
        self._current_cat = None
        self._current_folder = None
        self._active_tag = None
        self.folder_tree.clearSelection()
        self._update_nav_checked()
        self._refresh_grid()
        # Update batch bar for trash view
        self._on_selection_changed(len(self.grid._selected))

    def _clear_smart_filter(self):
        """Clear the sidebar smart-filter (has_thumb / no_thumb / fav) without
        disturbing the current folder / category / tag selection.

        Used by the three sidebar chips so that clicking an already-active
        chip turns it OFF and removes its filter, while keeping the user
        exactly where they are in the folder/tag tree.
        """
        if self._current_view == "all":
            return
        self._current_view = "all"
        self._update_nav_checked()
        self._refresh_grid()

    def _set_cat(self, cat):
        if self._current_cat == cat:
            self._current_cat = None
        else:
            self._current_cat = cat
        self._current_view = "all"
        self._current_folder = None
        self._active_tag = None
        self.folder_tree.clearSelection()
        self._update_nav_checked()
        self._refresh_grid()

    @staticmethod
    def _set_combo_by_data(combo, data):
        if data is None:
            combo.setCurrentIndex(0)
            return
        idx = combo.findData(data)
        combo.setCurrentIndex(idx if idx >= 0 else 0)

    def _on_search_changed(self, text):
        # Debounce: avoid a full grid rebuild on every keystroke.
        self._search_timer.start()

    def _apply_filters(self):
        try:
            return self._apply_filters_inner()
        except Exception as _e:
            import traceback as _tb
            dbg("APPLY_FILTERS EXCEPTION:", repr(_e))
            dbg(_tb.format_exc())
            return

    def _apply_filters_inner(self):
        q = self.search.text().strip().lower()
        t = self.type_combo.currentData()
        src = self.src_combo.currentData()
        sort = self.sort_combo.currentData()
        filtered = []

        # Trash view: show deleted assets from DB directly
        if self._current_view == "trash":
            filtered = self.db.get_trash()
            self.grid.set_assets(filtered)
            self._populate_details(filtered)
            self._update_section_head(filtered)
            if self._current_asset and self._current_asset not in filtered:
                self._current_asset = None
                self._show_empty_inspector()
            return


 # Uncategorized view: assets with no type or unknown
        if self._current_view == "uncategorized":
            filtered = [a for a in self._all_assets
                        if not a.type or a.type in ("Unknown", "")]
            filtered = self._apply_grid_filters(filtered, q, t, src)
            self._apply_sort(filtered, sort)
            self.grid.set_assets(filtered)
            self._populate_details(filtered)
            self._update_section_head(filtered)
            return

        # Real-thumbnail predicate.
        #   ``tier`` is the SINGLE source of truth after scanner / repair fixes:
        #     1 = engine-extracted,  2 = peak-frame,  3 = manual  -> REAL image
        #     4 = generated placeholder (colorful gradient + glyph)    -> NO image
        #   ``has_thumb`` must also be True as a cross-check; this prevents
        #   stale rows where tier defaulted to 1 (legacy) but the on-disk
        #   thumbnail file is actually a placeholder PNG.
        def _has_real_thumb(a):
            t = getattr(a, "tier", 4) or 4
            if t == 4:
                return False
            return bool(getattr(a, "has_thumb", False))

        # Has-thumbnail view: assets with a REAL embedded thumbnail
        if self._current_view == "has_thumb":
            filtered = [a for a in self._all_assets if _has_real_thumb(a)]
            filtered = self._apply_grid_filters(filtered, q, t, src)
            self._apply_sort(filtered, sort)
            self.grid.set_assets(filtered)
            self._populate_details(filtered)
            self._update_section_head(filtered)
            return

        # No-thumbnail view: only generated-placeholder thumbnails
        if self._current_view == "no_thumb":
            filtered = [a for a in self._all_assets if not _has_real_thumb(a)]
            filtered = self._apply_grid_filters(filtered, q, t, src)
            self._apply_sort(filtered, sort)
            self.grid.set_assets(filtered)
            self._populate_details(filtered)
            self._update_section_head(filtered)
            return

        # Recent view: last 60 imported/scanned, sorted by imported_at desc
        if self._current_view == "recent":
            filtered = [a for a in self._all_assets if a.imported_at]
            filtered.sort(key=lambda a: a.imported_at, reverse=True)
            filtered = filtered[:60]
            filtered = self._apply_grid_filters(filtered, q, t, src)
            self.grid.set_assets(filtered)
            self._populate_details(filtered)
            self._update_section_head(filtered)
            return

        # Default: apply the regular nav filtering
        for a in self._all_assets:
            if self._current_view == "fav" and not getattr(a, "favorite", False):
                continue
            if self._current_folder and not self._asset_in_folder(a, self._current_folder):
                continue
            filtered.append(a)

        # Apply the rest of the grid filters (type combo, source combo, tags, search)
        filtered = self._apply_grid_filters(filtered, q, t, src)
        self._apply_sort(filtered, sort)
        self.grid.set_assets(filtered)
        self._populate_details(filtered)
        self._update_section_head(filtered)
        if self._current_asset and self._current_asset not in filtered:
            self._current_asset = None
            self._show_empty_inspector()
        dbg("APPLY_FILTERS done: view=%r tag=%r folder=%r type=%r -> %d assets" % (
            self._current_view, self._active_tag,
            (self._current_folder or {}).get("id") if self._current_folder else None,
            t, len(filtered)))

    def _asset_in_folder(self, asset, folder_data):
        kind = folder_data.get("kind")
        if kind == "real":
            path = folder_data.get("path")
            if path:
                prefix = path.rstrip(os.sep) + os.sep
                return asset.source_path.startswith(prefix)
        elif kind == "virtual":
            folder_id = folder_data.get("id")
            if folder_id:
                return folder_id in self._asset_folder_ids(asset.source_path)
        return False

    def _asset_folder_ids(self, source_path):
        if not hasattr(self, "_folder_asset_cache"):
            self._folder_asset_cache = {}
        if source_path not in self._folder_asset_cache:
            self._folder_asset_cache[source_path] = set(self.db.get_asset_folders(source_path))
        return self._folder_asset_cache[source_path]

    def _apply_grid_filters(self, items, q, t, src):
        """Apply type / source / tags / search filtering to a list of assets."""
        out = []
        for a in items:
            if self._active_tag and self._active_tag not in (a.tags or "").split(","):
                continue
            if self._current_cat and a.type != self._current_cat:
                continue
            if t and a.type != t:
                continue
            if src == "pure" and getattr(a, "blueprint", False):
                continue
            if q and q not in a.name.lower() and q not in a.object_path.lower() \
                    and q not in (a.tags or "").lower() \
                    and q not in (a.note or "").lower() \
                    and q not in (a.type or "").lower():
                continue
            out.append(a)
        return out

    def _apply_sort(self, items, sort):
        if sort == "name":
            items.sort(key=lambda a: a.name.lower())
        elif sort == "type":
            items.sort(key=lambda a: (a.type or "", a.name.lower()))
        elif sort == "date":
            items.sort(key=lambda a: a.imported_at or "", reverse=True)
        elif sort == "size":
            items.sort(key=lambda a: a.size or 0, reverse=True)
        elif sort == "rating":
            items.sort(key=lambda a: (a.rating or 0, a.name.lower()), reverse=True)
        elif sort == "random":
            random.shuffle(items)

    def _on_view_mode_changed(self, mode):
        if not mode:
            return
        self._view_mode = mode
        self.cfg["view_mode"] = mode
        cfg.save(self.cfg)
        # toggle stacked widget: details table vs grid
        if mode == "details":
            self.content_stack.setCurrentWidget(self.details_table)
            self.size_combo.setEnabled(False)
        else:
            self.content_stack.setCurrentWidget(self.grid)
            self.size_combo.setEnabled(True)
            # grid uses "list" for list mode, icon-size for icons mode
            self.grid.view_mode = "list" if mode == "list" else self._icon_size
        # Reset cached card dimensions so _relayout() re-measures for the new mode.
        # Without this, stale _card_h from the previous mode (e.g. 84px list height
        # leaking into icon mode) causes overlapping or huge gaps.
        self.grid._card_h = 0
        self.grid._card_w = 0
        self._apply_filters()

    def _on_icon_size_changed(self, _=None):
        size = self.size_combo.currentData()
        if not size:
            return
        self._icon_size = size
        self.cfg["icon_size"] = size
        cfg.save(self.cfg)
        if self._view_mode == "icons":
            self.grid.view_mode = size
            # Reset cached card dimensions so _relayout() re-measures for new size.
            self.grid._card_h = 0
            self.grid._card_w = 0
            self._apply_filters()

    def _update_section_head(self, filtered):
        if self._current_folder:
            self.section_title.setText(self._current_folder.get("name", tr("folder")))
            self.section_count.setText("· %d%s" % (len(filtered), tr("found")))
            return
        if self._active_tag:
            self.section_title.setText("%s：%s" % (tr("tags"), self._active_tag))
            self.section_count.setText("· %d%s" % (len(filtered), tr("found")))
            return
        title_map = {
            "all": "all_fx", "fav": "favorites",
            "trash": "trash", "uncategorized": "uncategorized",
            "recent": "recent",
            "has_thumb": "has_thumb", "no_thumb": "no_thumb",
        }
        key = title_map.get(self._current_view, "all_fx")
        if self._current_cat:
            key = self._current_cat.lower()
        self.section_title.setText(tr(key))
        self.section_count.setText("· %d%s" % (len(filtered), tr("found")))

    def _on_selection_changed(self, n):
        self.batch_count.setText(str(n))
        self.statusBar().showMessage(tr("sel_count", n=n))
        is_trash = self._current_view == "trash"
        was_visible = self.batchbar.isVisible()
        should_show = n > 0 or is_trash
        self.batchbar.setVisible(should_show)
        if should_show and not was_visible:
            self._animate_batchbar_in()
        # In trash view, always show even with 0 selection (to show "empty trash")
        self.b_restore.setVisible(is_trash and n > 0)
        self.b_delete_perm.setVisible(is_trash and n > 0)
        self.b_empty_trash.setVisible(is_trash)
        self.b_trash.setVisible(n > 0 and not is_trash)
        self.sel_hint_lbl.setVisible(n > 0)
        self._auto_inspector(n)

    def _auto_inspector(self, n):
        """Collapse the right inspector when nothing is selected; re-expand on selection."""
        sizes = self.splitter.sizes()
        if n == 0:
            sizes[2] = 0
        elif sizes[2] < 40:
            give = 320
            sizes[2] = give
            sizes[1] = max(200, sizes[1] - give)
        else:
            return
        self.splitter.setSizes(sizes)

    # ---------- selection controls (section-head buttons) ----------
    def _on_select_all(self):
        self.grid.select_all()
        self.statusBar().showMessage(tr("sel_all_done", n=len(self.grid.selected_assets())))

    def _on_invert_selection(self):
        self.grid.invert_selection()
        self.statusBar().showMessage(tr("sel_invert_done", n=len(self.grid.selected_assets())))

    def _on_clear_selection(self):
        self.grid.clear_selection()

    # ---------- library loading & scanning ----------
    def _reload_library(self):
        # This app only catalogs Niagara / Cascade effects.
        self._all_assets = [a for a in self.db.get_assets() if a.type in FX_TYPES]
        self._folder_asset_cache = {}
        self._refresh_folder_tree()
        self._apply_filters()
        self._refresh_sidebar_stats()
        self._refresh_tag_browser()
        # Total count is already shown in the content header ("· N 个结果"),
        # so the status bar shows a transient ready state instead of repeating it.
        self.statusBar().showMessage(tr("ready"))

    def _add_folder(self):
        folder = QFileDialog.getExistingDirectory(
            self, tr("select_scan_folder"), self.cfg.get("library_dir", ""))
        if not folder:
            return
        folder = os.path.abspath(folder)
        roots = set(self.cfg.get("scan_roots") or [])
        roots.add(folder)
        self.cfg["scan_roots"] = sorted(roots)
        cfg.save(self.cfg)
        # Show the folder immediately in the sidebar before the scan finishes
        self._refresh_folder_tree()
        if self.cfg.get("skip_import_dialog"):
            mode = self.cfg.get("import_mode", "reference")
        else:
            mode = self._ask_import_mode()
        self._run_scan([folder], mode)

    def _auto_scan(self):
        roots = list(self.cfg.get("scan_roots") or [])
        if not roots:
            d = QFileDialog.getExistingDirectory(
                self, tr("select_scan_root"), self.cfg.get("library_dir", ""))
            if not d:
                return
            roots = [d]
            self.cfg["scan_roots"] = roots
            cfg.save(self.cfg)
        self._run_scan(roots, self.cfg.get("import_mode", "reference"))

    def _ask_import_mode(self):
        cur = self.cfg.get("import_mode", "reference")
        read_thumbs = self.cfg.get("read_thumbs_on_import", True)
        dlg = BaseDialog(self)
        dlg.setWindowTitle(tr("import_mode_title"))
        dlg.setMinimumWidth(360)
        vl = QVBoxLayout(dlg)
        vl.setContentsMargins(20, 20, 20, 20)
        vl.setSpacing(10)
        vl.addWidget(QLabel(tr("import_mode_prompt")))
        for m, label in (("reference", tr("mode_reference")),
                         ("copy", tr("mode_copy"))):
            b = QPushButton(label)
            # #sfbtn = the design system's left-aligned option-row button.
            # The old bare QPushButton picked up the generic solid-purple rule
            # and the two choices looked like a pair of loud CTAs.
            b.setObjectName("sfbtn")
            b.setCheckable(True)
            b.setChecked(m == cur)
            b.setMinimumHeight(38)
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _c, mm=m: (
                self.cfg.__setitem__("import_mode", mm), cfg.save(self.cfg), dlg.accept()))
            vl.addWidget(b)
        cb = QCheckBox(tr("read_thumbs_on_import"))
        cb.setChecked(read_thumbs)
        cb.stateChanged.connect(lambda s: (
            self.cfg.__setitem__("read_thumbs_on_import", s == Qt.Checked),
            cfg.save(self.cfg)))
        vl.addWidget(cb)
        dlg.exec()
        return self.cfg.get("import_mode", "reference")

    def _run_scan(self, roots, mode):
        copy = (mode == "copy")
        lib = self.cfg.get("library_dir") or os.path.join(CONFIG_DIR, "library")
        thumbs_dir = os.path.join(lib, "thumbs")
        files_dir = os.path.join(lib, "files") if copy else None
        self._set_busy(True, tr("scanning"))
        self.statusBar().showMessage(tr("scan_start", n=len(roots)), 0)
        read_thumbs = self.cfg.get("read_thumbs_on_import", True)
        w = ScannerWorker(self._db_path, roots, thumbs_dir, copy=copy, files_dir=files_dir,
                          fx_only=self.cfg.get("import_fx_only", True),
                          read_thumbs=read_thumbs)
        self._active_worker = w

        def _prog(done, total, name):
            self.statusBar().showMessage(
                tr("scan_progress", done=done, total=total, name=name))

        def _ok(data):
            self._active_worker = None
            self._set_busy(False, tr("scanned_n", total=data["total"],
                                    niagara=data["niagara"], cascade=data["cascade"],
                                    unknown=data["unknown"]))
            self.log.append(tr("scanned_n", total=data["total"], niagara=data["niagara"],
                               cascade=data["cascade"], unknown=data["unknown"]))
            if data.get("skipped", 0):
                self.log.append(tr("skipped_n", n=data["skipped"]))
            ue_cats = data.get("ue_categorized", 0)
            auto_cats = data.get("auto_categorized", 0)
            if auto_cats:
                folders = ", ".join(data.get("ue_folders", []))
                self.log.append(tr("cat_ue_auto", n=auto_cats, ue=ue_cats, folders=folders))
            self._reload_library()
            # ScannerWorker already extracts embedded thumbnails locally; never
            # auto-launch UnrealEditor (user opted for pure-Python reading).

        def _err(e):
            # Per-file scan error. The worker now isolates failures and
            # keeps going, so this fires once per skipped file -- showing a
            # modal here would spam a dialog per bad file. Just record it;
            # the full error summary is logged when the scan finishes.
            self.log.append("[scan] skipped: " + e)

        w.progress.connect(_prog)
        w.finished.connect(_ok)
        w.failed.connect(_err)
        w.start()

    # ---------- inspector ----------
    def _on_asset_activated(self, asset):
        self._current_asset = asset
        self._show_inspector(asset)

    def _show_inspector(self, asset):
        from app.style import THEMES
        tok = THEMES.get(self.theme, THEMES["light"])

        # hero
        pm = QPixmap()
        if asset.thumb_path and os.path.exists(asset.thumb_path):
            pm = _crop_to_square(asset.thumb_path, 320, 170)
        if pm.isNull():
            pm = _placeholder(asset.type, 320, 170)
        self.insp_hero.setPixmap(pm.scaled(320, 170, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        self.insp_hero.setStyleSheet("border-bottom:1px solid %s;" % tok["border"])

        self.insp_title.setText(asset.name)
        self.insp_path.setText(asset.object_path)

        tcolor, tbg = TYPE_CHIP.get(asset.type, DEFAULT_CHIP)
        self.insp_type_chip.setText(asset.type)
        self.insp_type_chip.setStyleSheet(
            "background:%s; color:%s; border-radius:6px; padding:3px 9px; font-weight:600; font-size:12px" % (tbg, tcolor))
        self.insp_bp_chip.setVisible(getattr(asset, "blueprint", False))

        # health
        h = getattr(asset, "health", "ok") or "ok"
        self.insp_health_lbl.setText(tr("hp_" + h))
        hc = {"ok": "#1aa179", "warn": "#f5a623", "bad": "#e25950"}.get(h, "#94a3b8")
        self.insp_health_lbl.setStyleSheet("color:%s; font-weight:700;" % hc)

        # tags
        self._clear_layout(self.insp_tags_flow)
        for tag in (asset.tags.split(",") if asset.tags else []):
            tag = tag.strip()
            if not tag:
                continue
            chip = QPushButton(tag)
            chip.setObjectName("tagchip")
            chip.setStyleSheet(
                "font-size:11px; padding:3px 9px; border-radius:7px; background:%s; border:1px solid %s; color:%s" %
                (tok["panel2"], tok["border"], tok["muted"]))
            chip.clicked.connect(lambda _c, t=tag: self._remove_tag(t))
            self.insp_tags_flow.addWidget(chip)
        self.insp_tags_flow.addStretch(1)

        # rating
        rating = getattr(asset, "rating", 0) or 0
        self._refresh_stars(rating)

        self.insp_note.blockSignals(True)
        self.insp_note.setPlainText(getattr(asset, "note", "") or "")
        self.insp_note.blockSignals(False)
        for w in (self.insp_fav, self.insp_set, self.insp_exp, self.insp_pack,
                  self.insp_imp, self.insp_open, self.insp_copy):
            w.setEnabled(True)
        self._sync_insp_fav()

    def _sync_insp_fav(self):
        if not self._current_asset:
            return
        fav = getattr(self._current_asset, "favorite", False)
        self.insp_fav.setText(("★ " if fav else "☆ ") + tr("add_fav"))

    def _insp_toggle_fav(self):
        if not self._current_asset:
            return
        a = self._current_asset
        a.favorite = not getattr(a, "favorite", False)
        self.db.set_favorite(a.source_path, a.favorite)
        self._sync_insp_fav()
        self._refresh_card_fav(a.source_path, a.favorite)
        self._apply_filters()

    def _refresh_card_fav(self, source_path, fav):
        # The shared asset object (also held in grid.assets) is
        # mutated by the caller, so a recycled card re-reads it.
        # Here we only repaint the card if it is currently windowed.
        for c in self.grid._live.values():
            if c.asset.source_path == source_path:
                c._fav = fav
                c._style_fav()
                break

    def _on_grid_fav_changed(self, asset, fav):
        """Called when a card's favorite star is toggled directly on the card."""
        asset.favorite = fav
        self.db.set_favorite(asset.source_path, fav)
        if self._current_asset and self._current_asset.source_path == asset.source_path:
            self._sync_insp_fav()

    # ---------- tag / note / rating editing ----------
    def _add_tag(self):
        if not self._current_asset:
            return
        t = self.insp_tag_input.text().strip()
        if not t:
            return
        tags = [x.strip() for x in self._current_asset.tags.split(",") if x.strip()]
        if t not in tags:
            tags.append(t)
            self._current_asset.tags = ",".join(tags)
            self.db.set_tags(self._current_asset.source_path, self._current_asset.tags)
            self.insp_tag_input.clear()
            self._show_inspector(self._current_asset)
            try:
                self._refresh_tag_browser()
            except Exception as e:
                dbg("ERR _refresh_tag_browser: %r" % e)
            self._refresh_grid()

    def _remove_tag(self, tag):
        if not self._current_asset:
            return
        tags = [x.strip() for x in self._current_asset.tags.split(",")
                if x.strip() and x.strip() != tag]
        self._current_asset.tags = ",".join(tags)
        self.db.set_tags(self._current_asset.source_path, self._current_asset.tags)
        self._show_inspector(self._current_asset)
        try:
            self._refresh_tag_browser()
        except Exception as e:
            dbg("ERR _refresh_tag_browser: %r" % e)
        self._refresh_grid()

    def _on_note_changed(self):
        if not self._current_asset:
            return
        self._current_asset.note = self.insp_note.toPlainText()
        self.db.set_note(self._current_asset.source_path, self._current_asset.note)

    def _refresh_stars(self, rating):
        for i, s in enumerate(self.insp_stars):
            on = i < rating
            s.setText("★" if on else "☆")
            s.setProperty("on", on)
            s.style().unpolish(s)
            s.style().polish(s)

    def _set_rating(self, idx):
        if not self._current_asset:
            return
        if getattr(self._current_asset, "rating", 0) == idx:
            idx = 0
        self._current_asset.rating = idx
        self.db.set_rating(self._current_asset.source_path, idx)
        self._show_inspector(self._current_asset)

    def _open_lightbox(self, asset):
        if asset is None:
            return
        dlg = LightboxDialog(asset, self.theme, self)
        dlg.exec()

    # ---------- source navigation (jump back to the real file) ----------
    def _source_of(self, asset):
        return asset.stored_path or asset.source_path

    def _find_uproject(self, src):
        """Walk up from a file's directory looking for a .uproject."""
        cur = os.path.dirname(src)
        for _ in range(8):
            try:
                names = os.listdir(cur)
            except Exception:
                return None
            for f in names:
                if f.lower().endswith(".uproject"):
                    return os.path.join(cur, f)
            parent = os.path.dirname(cur)
            if parent == cur:
                return None
            cur = parent
        return None

    def _reveal_in_explorer(self, path):
        d = os.path.dirname(path)
        try:
            if os.name == "nt":
                subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
            elif sys.platform == "darwin":
                subprocess.Popen(["open", d])
            else:
                subprocess.Popen(["xdg-open", d])
        except Exception as e:
            QMessageBox.warning(self, tr("open_location"), str(e))

    def _open_location(self, asset):
        if asset is None:
            return
        src = self._source_of(asset)
        if not os.path.isfile(src):
            QMessageBox.warning(self, tr("open_location"), tr("src_file_missing"))
            return
        self._reveal_in_explorer(src)

    def _copy_path(self, asset):
        if asset is None:
            return
        src = self._source_of(asset)
        QApplication.clipboard().setText(src)
        self.statusBar().showMessage(tr("path_copied"))

    # ---------- export (to UE project Content folder) ----------
    def _export_one(self, asset):
        if asset is None:
            return
        self._export_selected(assets=[asset])

    def _export_selected(self, assets=None):
        # Without a detected Unreal Editor, the export still copies files to the
        # chosen folder but cannot link into a live UE project — tell the user
        # once so "export succeeded" isn't mistaken for "imported into UE".
        if not getattr(self, "_ue_available", False):
            QMessageBox.information(
                self, tr("export"), tr("ue_not_configured"))
        if assets is None:
            assets = self.grid.selected_assets()
        if not assets:
            if self._current_asset:
                assets = [self._current_asset]
            else:
                QMessageBox.information(self, tr("export"),
                                        tr("select_assets_first"))
                return
        target_dir = QFileDialog.getExistingDirectory(
            self, tr("select_ue_content_dir"), "")
        if not target_dir:
            return
        # The user should point to the target project's Content/ folder
        target_content = target_dir
        # If they pointed at the project root, auto-detect Content/
        if not os.path.basename(target_dir).lower() == "content":
            candidate = os.path.join(target_dir, "Content")
            if os.path.isdir(candidate):
                target_content = candidate

        source_roots = list(self.cfg.get("scan_roots") or [])
        if not source_roots:
            # Fall back to parent Content directories of each asset
            for a in assets:
                cd, _ = ue_export.find_content_dir(a.source_path)
                if cd:
                    source_roots.append(cd)

        self._set_busy(True, tr("exporting_to_ue"))

        def _progress(done, total, name):
            self.statusBar().showMessage(
                tr("export_progress", done=done, total=total, name=name))

        def _log(msg):
            self.log.append("[export] " + msg)

        try:
            n = ue_export.export_to_ue_project(
                assets, source_roots, target_content,
                progress_callback=_progress, log_callback=_log)
            self.statusBar().showMessage(tr("exported_n_files", n=n))
            self.log.append(tr("exported_n_files", n=n) + " -> " + target_content)
        except Exception as e:
            QMessageBox.critical(self, tr("export_failed"), str(e))
            self.log.append("[export] ERROR: " + str(e))
        finally:
            self._set_busy(False)

    # ---------- import ----------
    # ---------- import (local .fxpack: unzip into library) ----------
    def _import(self):
        path, _ = QFileDialog.getOpenFileName(self, tr("select_fxpack"),
                                              self.cfg.get("library_dir", ""),
                                              "FX Pack (*.fxpack)")
        if not path:
            return
        try:
            n = self._import_from_fxpack(path)
            self._reload_library()
            QMessageBox.information(self, tr("import_complete"),
                                    tr("imported_n", n=n))
            self.log.append(tr("imported_n", n=n) + " <- " + path)
        except Exception as e:
            QMessageBox.critical(self, tr("import_failed"), str(e))

    def _import_from_fxpack(self, path):
        lib = self.cfg.get("library_dir") or os.path.join(CONFIG_DIR, "library")
        thumbs_dir = os.path.join(lib, "thumbs")
        files_dir = os.path.join(lib, "files")
        os.makedirs(thumbs_dir, exist_ok=True)
        os.makedirs(files_dir, exist_ok=True)
        imported = 0
        with zipfile.ZipFile(path, "r") as z:
            names = set(z.namelist())
            manifest = json.loads(z.read("manifest.json"))
            for item in manifest.get("assets", []):
                atype = item.get("type", "Unknown")
                if atype not in FX_TYPES:
                    continue
                fname = item.get("file", "")
                if not fname or ("assets/" + fname) not in names:
                    continue
                base = os.path.splitext(fname)[0]
                dst = os.path.join(files_dir, fname)
                # extract the .uasset and its sibling chunks
                for zn in names:
                    if zn.startswith("assets/") and os.path.splitext(os.path.basename(zn))[0] == base:
                        with z.open(zn) as zi, open(os.path.join(files_dir, os.path.basename(zn)), "wb") as fo:
                            fo.write(zi.read())
                thumb_dst = None
                tname = item.get("thumb", "")
                if tname and ("thumbs/" + tname) in names:
                    thumb_dst = os.path.join(thumbs_dir, tname)
                    with z.open("thumbs/" + tname) as zi, open(thumb_dst, "wb") as fo:
                        fo.write(zi.read())
                # dependencies bundled by export_to_fxpack
                for dn in (item.get("deps") or []):
                    if ("assets/" + dn) in names:
                        with z.open("assets/" + dn) as zi, \
                                open(os.path.join(files_dir, os.path.basename(dn)), "wb") as fo:
                            fo.write(zi.read())
                a = FXAsset(
                    source_path=dst, name=item.get("name", os.path.splitext(fname)[0]),
                    type=item.get("type", "Unknown"), class_name=item.get("class_name", ""),
                    stored_path=dst, thumb_path=thumb_dst,
                    tags=item.get("tags", ""), rating=item.get("rating", 0),
                    note=item.get("note", ""), size=item.get("size", 0),
                    imported_at=item.get("imported_at", ""), source="fxpack",
                    engine_version=item.get("engine_version", ""),
                    has_thumb=bool(thumb_dst))
                self.db.upsert_asset(a)
                imported += 1
                # Persist engine version so the thumbnail badge renders on
                # fxpack-imported assets too (set on a after upsert above).
                self.db.set_engine_version(dst, a.engine_version)
                # Re-create the source UE project category when the pack
                # recorded one (so a pack moved to another machine keeps its
                # auto-grouping). Uses the same folder name as the scan path.
                _uf = item.get("_ue_folder") or None
                if _uf:
                    fid = self.db.ensure_folder(_uf, path=item.get("uproject_path"), virtual=1)
                    self.db.add_asset_to_folder(dst, fid)
        return imported

    # ---------- export .fxpack (portable, self-contained archive) ----------
    def _export_fxpack_selected(self, assets=None):
        if assets is None:
            assets = self.grid.selected_assets()
        if not assets:
            if self._current_asset:
                assets = [self._current_asset]
            else:
                QMessageBox.information(self, tr("exp_fxpack"),
                                        tr("select_assets_first"))
                return
        self._export_fxpack(assets)

    def _export_fxpack_one(self, asset):
        if asset is None:
            return
        self._export_fxpack([asset])

    def _export_fxpack(self, assets):
        default_name = (assets[0].name if assets else "fxlibrary") + ".fxpack"
        out_path, _ = QFileDialog.getSaveFileName(
            self, tr("select_fxpack_out"), default_name,
            "FX Pack (*.fxpack)")
        if not out_path:
            return
        if not out_path.lower().endswith(".fxpack"):
            out_path += ".fxpack"
        lib = self.cfg.get("library_dir") or os.path.join(CONFIG_DIR, "library")
        self._set_busy(True, tr("exp_fxpack"))
        try:
            n = ue_export.export_to_fxpack(
                assets, out_path, library_dir=lib,
                progress_callback=lambda d, t, nm: self.statusBar().showMessage(
                    tr("export_progress", done=d, total=t, name=nm)),
                log_callback=lambda m: self.log.append("[fxpack] " + m))
            self.statusBar().showMessage(tr("fxpack_n", n=n))
            self.log.append(tr("fxpack_n", n=n) + " -> " + out_path)
            QMessageBox.information(self, tr("exp_fxpack"),
                                    tr("fxpack_saved", path=out_path))
        except Exception as e:
            QMessageBox.critical(self, tr("export_failed"), str(e))
            self.log.append("[fxpack] ERROR: " + str(e))
        finally:
            self._set_busy(False)

    # ---------- health scan (missing files / duplicate names) ----------
    def _run_health_scan(self):
        assets = list(self._all_assets)
        if not assets:
            QMessageBox.information(self, tr("health_report_title"),
                                    tr("health_empty"))
            return
        issues = []  # (asset, kind, detail)
        name_map = {}
        for a in assets:
            if not os.path.isfile(a.source_path):
                self.db.set_health(a.source_path, "bad")
                issues.append((a, "missing", a.source_path))
                continue
            self.db.set_health(a.source_path, "ok")
            key = (a.name or "").strip().lower()
            name_map.setdefault(key, []).append(a)
        for key, group in name_map.items():
            if len(group) > 1:
                for a in group:
                    self.db.set_health(a.source_path, "warn")
                    issues.append((a, "dup", tr("health_dup_name")))
        if not issues:
            QMessageBox.information(self, tr("health_report_title"),
                                    tr("health_ok"))
            self.statusBar().showMessage(tr("health_done"))
            self._reload_library()
            return
        dlg = BaseDialog(self)
        dlg.setWindowTitle(tr("health_report_title"))
        dlg.setMinimumWidth(460)
        root = QVBoxLayout(dlg)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(10)
        summary = QLabel(tr("health_report_title") + " · " + str(len(issues)))
        summary.setObjectName("title")
        root.addWidget(summary)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        box = QWidget()
        # bare QWidget container inherits the global QWidget {bg} rule —
        # on the dialog's lighter bg2 it painted a big dark block behind
        # the issue rows. Keep it transparent so rows sit on the dialog bg.
        box.setStyleSheet("background: transparent;")
        bl = QVBoxLayout(box)
        bl.setContentsMargins(0, 0, 0, 0)
        bl.setSpacing(6)
        for a, kind, detail in issues:
            row = QHBoxLayout()
            row.setSpacing(8)
            badge = QLabel(tr("health_missing_file") if kind == "missing"
                          else tr("health_dup_name"))
            bc = "#e25950" if kind == "missing" else "#f5a623"
            badge.setStyleSheet(
                "background:%s; color:%s; border-radius:6px; padding:2px 8px; "
                "font-size:11px; font-weight:700;" % (
                    "rgba(226,89,80,.16)" if kind == "missing"
                    else "rgba(245,166,35,.16)", bc))
            name = QLabel(a.name)
            name.setWordWrap(True)
            row.addWidget(badge)
            row.addWidget(name, 1)
            bl.addLayout(row)
        bl.addStretch(1)
        scroll.setWidget(box)
        root.addWidget(scroll, 1)
        btn = QPushButton(tr("ok"))
        btn.setObjectName("primary")
        btn.setFixedHeight(32)
        btn.clicked.connect(dlg.accept)
        root.addWidget(btn)
        dlg.exec()
        self._reload_library()

    # ---------- rename (display name only; on-disk file untouched) ----------
    def _rename_asset(self, asset):
        if asset is None:
            return
        new_name, ok = QInputDialog.getText(
            self, tr("rename_asset"), tr("rename_asset_ph"),
            QLineEdit.Normal, asset.name or "")
        if not ok or not new_name.strip():
            return
        new_name = new_name.strip()
        old_name = asset.name
        self.db.rename_asset(asset.source_path, new_name)
        for a in self._all_assets:
            if a.source_path == asset.source_path:
                a.name = new_name
                break
        asset.name = new_name
        self.log.append(tr("rename_done", old=old_name, new=new_name))
        if (self._current_asset
                and self._current_asset.source_path == asset.source_path):
            self.insp_title.setText(new_name)
        self._reload_library()

    # NOTE: the old "import Content folder into a UE project" flow was removed.
    # The library now catalogs LOCAL .uasset files directly (see _add_folder /
    # _auto_scan). UE is only used as an optional thumbnail renderer.

    # ---------- settings ----------
    # ---------- worker plumbing ----------
    def _run_worker(self, worker, on_finished, on_failed, ctx=None):
        self._last_ctx = ctx
        self._active_worker = worker

        def _done(r):
            try:
                on_finished(r)
            finally:
                self._cleanup(worker)

        def _fail(e):
            try:
                on_failed(e)
            finally:
                self._cleanup(worker)

        worker.log_line.connect(self.log.append)
        worker.finished.connect(_done)
        worker.failed.connect(_fail)
        worker.start()

    def _cleanup(self, worker):
        if worker:
            worker.deleteLater()
        if self._active_worker is worker:
            self._active_worker = None

    # ---------- grid interactions ----------
    def _on_asset_context(self, asset, pos):
        menu = QMenu(self)
        from app.style import THEMES
        tok = THEMES.get(self.theme, THEMES["light"])
        menu.setStyleSheet(
            "QMenu { background: %s; border: 1px solid %s; border-radius: 8px; padding: 6px; color: %s; }"
            "QMenu::separator { background: %s; height: 1px; margin: 4px 8px; }"
            "QMenu::item { padding: 7px 18px 7px 12px; border-radius: 6px; }"
            "QMenu::item:selected { background: %s; color: #fff; }"
            "QMenu::item:disabled { color: %s; }" % (
                tok["bg2"], tok["border"], tok["text"], tok["border"],
                tok["accent"], tok["muted2"]
            )
        )
        # --- selection semantics (Eagle-like) ---
        # Right-clicking a card that is part of the current multi-selection acts
        # on the whole selection; right-clicking an unselected card isolates it.
        sel = self.grid.selected_assets()
        if sel and asset in sel:
            targets = sel
        else:
            self.grid.select_only(asset)
            targets = [asset]
        n = len(targets)

        a_reveal = menu.addAction(tr("ctx_reveal"))
        a_copy = menu.addAction(tr("ctx_copy_path"))
        a_rename = menu.addAction(icon("tag", size=14), tr("rename_asset"))
        menu.addSeparator()
        a_export = menu.addAction(tr("ctx_export_sel", n=n) if n > 1 else tr("ctx_export_ue"))
        a_export_pack = menu.addAction(tr("ctx_export_fxpack"))
        a_manual = menu.addAction(tr("ctx_manual_thumb"))
        if n > 1:
            a_gen = menu.addAction(tr("ctx_thumb_sel", n=n))
        else:
            a_gen = menu.addAction(tr("ctx_thumb"))
        # Add-to-folder submenu (only virtual folders) — applies to all targets
        folders = self.db.get_folders()
        if folders:
            folder_menu = QMenu(tr("add_to_folder"), menu)
            folder_menu.setStyleSheet(menu.styleSheet())
            srcs = [t.source_path for t in targets]
            for f in folders:
                a = folder_menu.addAction(f["name"])
                a.triggered.connect(
                    lambda _c, fid=f["id"], sps=srcs:
                    [self._add_asset_to_folder(sp, fid) for sp in sps])
            menu.addMenu(folder_menu)
        # Rating submenu — applies to every target
        rating_menu = QMenu(tr("ctx_rating"), menu)
        rating_menu.setStyleSheet(menu.styleSheet())
        srcs_rt = [t.source_path for t in targets]
        def _apply_rating(r):
            for sp in srcs_rt:
                self.db.set_rating(sp, r)
            self._reload_library()
        for _r in range(0, 6):
            label = tr("rating_none") if _r == 0 else ("★" * _r + "☆" * (5 - _r))
            a = rating_menu.addAction(label)
            a.triggered.connect(lambda _c, rr=_r: _apply_rating(rr))
        menu.addMenu(rating_menu)
        # Batch tag — applies to every target
        a_tag = menu.addAction(tr("ctx_batch_tag"))
        a_tag.triggered.connect(lambda _c: self._batch_add_tag(targets))
        menu.addSeparator()
        a_trash = menu.addAction(tr("ctx_trash_sel", n=n) if n > 1 else tr("ctx_trash"))
        action = menu.exec(pos)
        if action == a_reveal:
            self._open_location(asset)
        elif action == a_copy:
            self._copy_path(asset)
        elif action == a_export:
            self._export_selected(assets=targets)
        elif action == a_export_pack:
            self._export_fxpack_selected(targets)
        elif action == a_rename:
            self._rename_asset(asset)
        elif action == a_manual:
            self._set_manual_thumb(asset)
        elif action == a_gen:
            self._gen_embedded_thumb(asset)
        elif action == a_trash:
            self._trash_assets(targets)

    def _set_manual_thumb(self, asset):
        if asset is None:
            return
        path, _ = QFileDialog.getOpenFileName(
            self, tr("select_thumbnail_image"), "", tr("images_filter"))
        if not path:
            return
        lib = self.cfg.get("library_dir") or tempfile.gettempdir()
        out_dir = os.path.join(lib, "thumbs")
        os.makedirs(out_dir, exist_ok=True)
        dst = os.path.join(out_dir, asset.name + ".png")
        try:
            img = QImage(path)
            if img.isNull():
                raise ValueError("Cannot load image: %s" % path)
            size = 256
            scaled = img.scaled(size, size, Qt.KeepAspectRatioByExpanding,
                                Qt.SmoothTransformation)
            x = (scaled.width() - size) // 2
            y = (scaled.height() - size) // 2
            cropped = scaled.copy(x, y, size, size)
            cropped.save(dst)

            self.db.set_thumb(asset.object_path, dst)
            self.db.set_has_thumb(asset.object_path, True)
            asset.thumb_path = dst
            asset.tier = 3
            self.grid.refresh_thumb(asset.object_path, dst)
            if self._current_asset and self._current_asset.object_path == asset.object_path:
                self._show_inspector(self._current_asset)
            self.log.append(tr("manual_thumbnail_set", path=dst))
        except Exception as e:
            QMessageBox.critical(self, tr("manual_thumbnail_error"), str(e))

    # ---------- generate playing thumbnail (right-click) ----------
    def _asset_by_source(self, src):
        for a in self._all_assets:
            if a.source_path == src:
                return a
        return None

    def _generate_placeholder_thumb(self, asset):
        """Create a local placeholder thumbnail for an asset that has no
        embedded thumbnail. Uses the SAME visual style as the scanner's
        ``make_placeholder_thumb`` (colorful gradient + type glyph + soft dots)
        so there is exactly ONE placeholder appearance everywhere.
        Marks the asset as tier 4 (no real thumbnail)."""
        from app.scanner import _TYPE_COLORS, _TYPE_GLYPH, _rgb

        src = getattr(asset, "source_path", None)
        name = getattr(asset, "name", "FX")
        t = getattr(asset, "type", "Unknown")
        if not src:
            return None
        lib = self.cfg.get("library_dir") or os.path.join(CONFIG_DIR, "library")
        out_dir = os.path.join(lib, "thumbs")
        os.makedirs(out_dir, exist_ok=True)
        out_path = os.path.join(out_dir, os.path.splitext(os.path.basename(src))[0] + ".png")

        size = 256
        from PIL import Image, ImageDraw, ImageFont

        w = h = size
        a, b = _TYPE_COLORS.get(t, _TYPE_COLORS.get("Unknown", ("#475569", "#94a3b8")))
        ca, cb = _rgb(a), _rgb(b)

        img = Image.new("RGB", (w, h))
        px = img.load()
        # vertical gradient (same as scanner)
        for y in range(h):
            ratio = y / max(1, h - 1)
            r = int(ca[0] + (cb[0] - ca[0]) * ratio)
            g = int(ca[1] + (cb[1] - ca[1]) * ratio)
            bl = int(ca[2] + (cb[2] - ca[2]) * ratio)
            for x in range(w):
                px[x, y] = (r, g, bl)

        d = ImageDraw.Draw(img, "RGBA")
        # soft glow circles (same as scanner)
        d.ellipse([w - 72, -24, w + 40, 88], fill=(255, 255, 255, 40))
        d.ellipse([-32, h - 56, 88, h + 56], fill=(255, 255, 255, 30))
        # particle dots (deterministic, same seed logic as scanner)
        import random
        random.seed(abs(hash(name)) % (2 ** 31))
        for _ in range(14):
            x = random.randint(10, w - 10)
            y = random.randint(10, h - 10)
            r = random.randint(1, 3)
            d.ellipse([x - r, y - r, x + r, y + r], fill=(255, 255, 255, 90))

        # centered type glyph (same as scanner)
        glyph = _TYPE_GLYPH.get(t, _TYPE_GLYPH.get("Unknown", "?"))
        try:
            font = ImageFont.truetype("arial.ttf", 120)
        except Exception:
            try:
                font = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 120)
            except Exception:
                font = ImageFont.load_default()
        try:
            bb = d.textbbox((0, 0), glyph, font=font)
            tw, th = bb[2] - bb[0], bb[3] - bb[1]
            d.text(((w - tw) / 2 - bb[0], (h - th) / 2 - bb[1] - 14),
                   glyph, fill=(255, 255, 255, 235), font=font)
        except Exception:
            d.text((w / 2 - 36, h / 2 - 50), glyph,
                   fill=(255, 255, 255, 235), font=font)

        # asset name at bottom (same as scanner)
        try:
            nfont = ImageFont.truetype("arial.ttf", 18)
        except Exception:
            try:
                nfont = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 18)
            except Exception:
                nfont = ImageFont.load_default()
        disp = name if len(name) <= 18 else name[:17] + "\u2026"
        try:
            nb = d.textbbox((0, 0), disp, font=nfont)
            nw, nh = nb[2] - nb[0], nb[3] - nb[1]
            d.text(((w - nw) / 2 - nb[0], h - nh - 12),
                   disp, fill=(255, 255, 255, 220), font=nfont)
        except Exception:
            pass

        try:
            img.save(out_path, "PNG")
            self.db.set_thumb(src, out_path)
            self.db.set_tier(src, 4)       # tier 4 = placeholder-only
            self.db.set_has_thumb(src, False)
            for a in self._all_assets:
                if a.source_path == src:
                    a.thumb_path = out_path
                    a.tier = 4
                    a.has_thumb = False
                    break
            self.grid.refresh_thumb(src, out_path, tier=4)
            if self._current_asset and self._current_asset.source_path == src:
                self._show_inspector(self._current_asset)
            self.log.append(tr("gen_thumb_none", name=name))
            return out_path
        except Exception as e:
            self.log.append("[thumb] placeholder failed for %s: %s" % (name, e))
            return None

    def _apply_embedded_thumb(self, asset, out_path):
        """Persist an extracted embedded thumbnail (tier 1) to DB and grid."""
        src = getattr(asset, "source_path", None)
        if not src:
            return
        self.db.set_thumb(src, out_path)
        self.db.set_tier(src, 1)  # tier 1 = engine thumbnail
        self.db.set_has_thumb(src, True)
        for a in self._all_assets:
            if a.source_path == src:
                a.thumb_path = out_path
                a.tier = 1
                break
        self.grid.refresh_thumb(src, out_path, tier=1)
        if self._current_asset and self._current_asset.source_path == src:
            self._show_inspector(self._current_asset)

    def _gen_embedded_thumb(self, asset):
        """Right-click action: read the static thumbnail embedded inside the
        asset's .uasset file (pure Python, no Unreal Editor launched). Assets
        that have no embedded thumbnail get a "no thumbnail" placeholder."""
        if asset is None:
            return
        selected = self.grid.selected_assets()
        if selected and asset in selected:
            targets = selected          # right-clicked an already-selected card
        else:
            targets = [asset]           # right-clicked a single (unselected) card

        lib = self.cfg.get("library_dir") or os.path.join(CONFIG_DIR, "library")
        out_dir = os.path.join(lib, "thumbs")
        os.makedirs(out_dir, exist_ok=True)

        embedded = 0
        placeholder = 0
        for a in targets:
            src = getattr(a, "source_path", None)
            name = getattr(a, "name", "FX")
            if not src or not os.path.isfile(src):
                self._generate_placeholder_thumb(a)
                placeholder += 1
                continue
            out_path = os.path.join(
                out_dir, os.path.splitext(os.path.basename(src))[0] + ".png")
            ok = False
            try:
                if uasset_thumb.extract_thumbnail(src, out_path):
                    # Validate: some UE thumbnails are non-decodable; treat those
                    # as "no thumbnail" so the user never sees a broken image.
                    if not QImage(out_path).isNull():
                        ok = True
            except Exception as e:
                self.log.append("[thumb] extract failed for %s: %s" % (name, e))
            if ok:
                self._apply_embedded_thumb(a, out_path)
                self.log.append(tr("gen_thumb_embedded", name=name))
                embedded += 1
            else:
                try:
                    if os.path.isfile(out_path):
                        os.remove(out_path)
                except OSError:
                    pass
                self._generate_placeholder_thumb(a)
                placeholder += 1

        total = embedded + placeholder
        msg = tr("gen_thumb_local_done",
                 embedded=embedded, placeholder=placeholder, total=total)
        self.log.append(msg)
        self.statusBar().showMessage(msg, 6000)

    def _read_all_embedded_thumbs(self):
        """One-click thumbnail refresh for every asset in the library."""
        assets = list(self._all_assets)
        if not assets:
            self.statusBar().showMessage(tr("no_assets_to_read"), 3000)
            return
        self.statusBar().showMessage(tr("read_thumbs_start", n=len(assets)), 3000)
        self._read_embedded_thumbs(assets)

    # ---------- trash ----------
    def _move_to_trash(self, asset):
        if asset is None:
            return
        asset.deleted = True
        self.db.delete_asset(asset.source_path)
        self.log.append(f"已移到回收站: {asset.name}")
        if self._current_asset and self._current_asset.source_path == asset.source_path:
            self._current_asset = None
            self._show_empty_inspector()
        self._reload_library()

    def _trash_assets(self, assets):
        """Move one or more assets to the trash in a single reload."""
        if not assets:
            return
        paths = {a.source_path for a in assets}
        for a in assets:
            a.deleted = True
            self.db.delete_asset(a.source_path)
            self.log.append(tr("moved_to_trash", name=a.name))
        self.log.append(tr("batch_trash_done", n=len(assets)))
        if self._current_asset and self._current_asset.source_path in paths:
            self._current_asset = None
            self._show_empty_inspector()
        self.grid.clear_selection()
        self._reload_library()

    def _batch_add_tag(self, targets):
        """Append one or more comma-separated tags to every selected asset."""
        if not targets:
            return
        text, ok = QInputDialog.getText(
            self, tr("ctx_batch_tag"), tr("batch_tag_prompt"),
            QLineEdit.Normal, "")
        if not ok or not text.strip():
            return
        new_tags = [t.strip() for t in text.split(",") if t.strip()]
        if not new_tags:
            return
        for t in targets:
            cur = [p.strip() for p in (t.tags or "").split(",") if p.strip()]
            merged = cur + [nt for nt in new_tags if nt not in cur]
            self.db.set_tags(t.source_path, ",".join(merged))
            t.tags = ",".join(merged)
        self.log.append(tr("batch_tag_done", n=len(targets), tags=",".join(new_tags)))
        self._reload_library()

    def _restore_from_trash(self, asset):
        if asset is None:
            return
        asset.deleted = False
        self.db.restore_asset(asset.source_path)
        self.log.append(f"已从回收站恢复: {asset.name}")
        self._reload_library()

    def _purge_asset_files(self, asset):
        """⑧: on *permanent* delete, physically reclaim the app-owned files —
        the copy-imported .uasset in library/files (copy mode) and the
        generated thumbnail. Without this, copy-mode libraries leak orphan
        files forever (disk keeps growing). Strictly scoped to paths INSIDE
        the managed library dir; the user's ORIGINAL source_path is never
        touched."""
        lib = os.path.abspath(self.cfg.get("library_dir")
                              or os.path.join(CONFIG_DIR, "library"))
        removed = 0
        for path in (getattr(asset, "stored_path", None),
                     getattr(asset, "thumb_path", None)):
            if not path:
                continue
            ap = os.path.abspath(path)
            # safety fence: only ever delete files under <library>/
            if not (ap == lib or ap.startswith(lib + os.sep)):
                continue
            try:
                if os.path.isfile(ap):
                    os.remove(ap)
                    removed += 1
            except OSError:
                pass
        return removed

    def _empty_trash(self):
        trash = self.db.get_trash()
        n = len(trash)
        if n == 0:
            return
        reply = QMessageBox.question(self, tr("empty_trash_title"),
                                     tr("empty_trash_confirm", n=n),
                                     QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            freed = 0
            for a in trash:
                freed += self._purge_asset_files(a)
            self.db.empty_trash()
            self.log.append(f"回收站已清空 ({n} 个, 释放 {freed} 个文件)")
            self.grid.clear_selection()
            self._reload_library()

    def _restore_selected(self):
        for a in self.grid.selected_assets():
            self._restore_from_trash(a)
        self.grid.clear_selection()

    def _permanently_delete_selected(self):
        assets = self.grid.selected_assets()
        if not assets:
            return
        reply = QMessageBox.question(self, tr("delete_perm_title"),
                                     tr("delete_perm_confirm", n=len(assets)),
                                     QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            freed = 0
            for a in assets:
                freed += self._purge_asset_files(a)
                self.db.permanently_delete_asset(a.source_path)
            self.log.append("永久删除 %d 个 (释放 %d 个文件)" % (len(assets), freed))
            self.grid.clear_selection()
            self._reload_library()


def main():
    if "--selftest" in sys.argv:
        import sys as _sys
        rc = _self_test()
        _sys.exit(rc)
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setWindowIcon(app_icon())
    win = MainWindow()
    dbg("STARTUP version=%s py=%s" % (_APP_VER, sys.version.split()[0]))
    win.show()
    sys.exit(app.exec())
