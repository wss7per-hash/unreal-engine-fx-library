# app/ui/asset_grid.py -- card-style grid of FX assets with thumbnails.
# Rewritten selection system: always-on multi-select (Ctrl+click, Shift+click,
# rubber-band drag). Custom scrollbars. Card highlight + check on selection.

import os
from PySide6.QtWidgets import (QScrollArea, QWidget, QGridLayout, QLabel,
                               QPushButton, QHBoxLayout, QVBoxLayout, QApplication,
                               QSizePolicy, QRubberBand, QGraphicsDropShadowEffect)
from PySide6.QtCore import (Qt, QSize, QRect, QRectF, QPoint, Signal, QTimer,
                            QPropertyAnimation, QEasingCurve)
from PySide6.QtGui import (QPixmap, QIcon, QPainter, QColor, QFont,
                           QLinearGradient, QImage, QPainterPath, QFontMetrics,
                           QPen)

from app.i18n import tr
from app.icons import icon
from app.style import THEMES

# --- Decisive diagnostic logger: writes to the SAME file as main_window.dbg
# so a single %TEMP%/fxlibrary_debug.log captures the whole click->filter
# chain. This records the grid's REAL render state right after set_assets(),
# which is the one place every filter path converges. ---
import datetime as _dt
_GDBG_PATH = os.path.join(os.environ.get("TEMP", os.path.expanduser("~")),
                        "fxlibrary_debug.log")
def _gdbg(*a):
    try:
        with open(_GDBG_PATH, "a", encoding="utf-8") as _f:
            _f.write("[%s] %s\n" % (
                _dt.datetime.now().strftime("%H:%M:%S.%f")[:-3],
                " ".join(str(x) for x in a)))
            _f.flush()
    except Exception:
        pass

CARD_W = 190
THUMB_H = 128

# F12: type colors made clearly distinguishable (was Niagara/Cascade both purple).
TYPE_CHIP = {
    "Niagara": ("#0ea5e9", "rgba(14,165,233,.14)"),
    "Cascade": ("#a855f7", "rgba(168,85,247,.14)"),
    "Blueprint": ("#10b981", "rgba(16,185,129,.14)"),
    "BP": ("#10b981", "rgba(16,185,129,.14)"),
    "Texture": ("#f59e0b", "rgba(245,158,11,.14)"),
    "Material": ("#f43f5e", "rgba(244,63,94,.14)"),
}
DEFAULT_CHIP = ("#64748b", "rgba(100,116,139,.14)")

HEALTH_COLOR = {"ok": "#1aa179", "warn": "#f5a623", "bad": "#e25950"}

TYPE_GRADIENT = {
    "Niagara": ("#22d3ee", "#3b82f6"),
    "Cascade": ("#8b5cf6", "#d946ef"),
    "Blueprint": ("#34d399", "#14b8a6"),
    "BP": ("#34d399", "#14b8a6"),
    "Texture": ("#fbbf24", "#fb923c"),
    "Material": ("#fb7185", "#e11d48"),
}
DEFAULT_GRADIENT = ("#475569", "#64748b")

TIER_LABEL = {1: "tier_engine", 2: "tier_peak", 3: "tier_manual", 4: "tier_none"}

# Thumbnail size modes (grid card width, thumb height) + list-view thumb size.
VIEW_SIZES = {
    "small": (150, 100),
    "medium": (190, 128),
    "large": (250, 168),
}
LIST_THUMB = (120, 64)
# List mode: force a tight fixed height so cards don't balloon from Qt layout
# engine's natural size calculation (which includes all child widget minimums,
# margins, and QSS padding — often 140+px). 84 = thumb(64) + body(~20) tight.
LIST_CARD_HEIGHT = 84

# Icon/grid mode: force fixed heights per size tier to prevent overlapping.
# Without these, adjustSize() returns inconsistent values and cards overlap.
ICON_CARD_HEIGHTS = {
    "small": 154,   # thumb(100) + body(~54)
    "medium": 190,  # thumb(128) + body(~62)
    "large": 244,   # thumb(168) + body(~76)
}


def _crop_to_square(path, w, h):
    img = QImage(path)
    if img.isNull():
        return QPixmap()
    scaled = img.scaled(w, h, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
    x = (scaled.width() - w) // 2
    y = (scaled.height() - h) // 2
    return QPixmap.fromImage(scaled.copy(x, y, w, h))


_PLACEHOLDER_CACHE = {}


# Type glyph LETTERs for placeholder thumbnails (matches scanner._TYPE_GLYPH)
_TYPE_LETTER = {
    "Niagara": "N",
    "Cascade": "C",
    "Blueprint": "B",
    "BP": "B",
    "Texture": "T",
    "Material": "M",
}


def _placeholder(fx_type, w, h):
    """Draw a unified placeholder: gradient + big type letter + soft dots.
    Matches the visual style of scanner.make_placeholder_thumb() and
    main_window._generate_placeholder_thumb() so there is exactly ONE
    placeholder appearance across the entire app."""
    key = (fx_type, w, h)
    cached = _PLACEHOLDER_CACHE.get(key)
    if cached is not None and not cached.isNull():
        return cached

    pm = QPixmap(w, h)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)

    # Gradient background
    a, b = TYPE_GRADIENT.get(fx_type, DEFAULT_GRADIENT)
    grad = QLinearGradient(0, 0, w, h)
    grad.setColorAt(0.0, QColor(a))
    grad.setColorAt(1.0, QColor(b))
    p.setBrush(grad)
    p.setPen(Qt.NoPen)
    p.drawRect(0, 0, w, h)

    # Soft glow circles (same feel as Pillow version)
    p.setBrush(QColor(255, 255, 255, 38))
    p.drawEllipse(w - 46, 8, 34, 34)
    p.setBrush(QColor(255, 255, 255, 28))
    p.drawEllipse(8, h - 46, 34, 34)

    # Particle dots (deterministic by type name for consistency)
    p.setBrush(QColor(255, 255, 255, 85))
    import random
    rng = random.Random(hash(fx_type) % (2 ** 31))
    for _ in range(10):
        dx = rng.randint(8, w - 8)
        dy = rng.randint(8, h - 8)
        dr = rng.randint(1, 2)
        p.drawEllipse(dx - dr, dy - dr, dr * 2, dr * 2)

    # Big centered type letter (N/C/B/T/M)
    letter = _TYPE_LETTER.get(fx_type, "?")
    font = QFont("Arial", max(int(h * 0.48), 24), QFont.Bold)
    p.setFont(font)
    p.setOpacity(0.93)
    p.setPen(QColor(255, 255, 255, 235))
    fm = QFontMetrics(font)
    tw = fm.horizontalAdvance(letter)
    th = fm.height()
    p.drawText((w - tw) // 2, (h - th) // 2 + fm.ascent(), letter)

    p.end()
    _PLACEHOLDER_CACHE[key] = pm
    return pm


_CHECK_ICON_CACHE = None


def _check_icon():
    global _CHECK_ICON_CACHE
    if _CHECK_ICON_CACHE is not None:
        return _CHECK_ICON_CACHE
    from PySide6.QtSvg import QSvgRenderer
    svg = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
           'stroke="#ffffff" stroke-width="3" stroke-linecap="round" '
           'stroke-linejoin="round"><path d="M5 12l5 5L20 7"/></svg>')
    r = QSvgRenderer()
    if not r.load(bytearray(svg.encode())):
        _CHECK_ICON_CACHE = QIcon()
        return _CHECK_ICON_CACHE
    pm = QPixmap(16, 16)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    r.render(p, QRectF(0, 0, 16, 16))
    p.end()
    _CHECK_ICON_CACHE = QIcon(pm)
    return _CHECK_ICON_CACHE


# ---------------------------------------------------------------------------
# Rounded pixmap label — clips its pixmap to rounded corners so square
# thumbnails don't break out of the parent card's border-radius.
# ---------------------------------------------------------------------------
class _RoundedPixmapLabel(QLabel):
    """QLabel that paints its pixmap clipped to a rounded rect path."""
    def __init__(self, radius=12, parent=None):
        super().__init__(parent)
        self._radius = radius

    def setRadius(self, r):
        self._radius = r

    def paintEvent(self, event):
        pm = self.pixmap()
        if pm is None or pm.isNull():
            super().paintEvent(event)
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        # Clip to rounded rect matching the card's top corners
        path = QPainterPath()
        path.addRoundedRect(QRectF(self.rect()), self._radius, self._radius)
        p.setClipPath(path)
        # Scale pixmap to fill the label (keep aspect ratio via _crop_to_square)
        scaled = pm.scaled(self.size(), Qt.KeepAspectRatioByExpanding,
                           Qt.SmoothTransformation)
        # Center-crop to label bounds
        src_x = (scaled.width() - self.width()) // 2
        src_y = (scaled.height() - self.height()) // 2
        p.drawPixmap(0, 0, self.width(), self.height(),
                     scaled, src_x, src_y, self.width(), self.height())
        p.end()


class AssetCard(QWidget):
    """Single asset card in the grid.

    Signals:
        activated(asset) — single click (select + show inspector)
        toggled(asset, bool) — Ctrl+click toggles selection
        context(asset, global_pos) — right-click
    """
    activated = Signal(object)
    toggled = Signal(object, bool)
    context = Signal(object, QPoint)

    def __init__(self, asset, index=0, view_mode="medium"):
        super().__init__()
        self.asset = asset
        self.index = index
        self.view_mode = view_mode
        self.setObjectName("AssetCard")
        if view_mode == "list":
            self._card_w = 0
            self._thumb_w, self._thumb_h = LIST_THUMB
        else:
            self._card_w, self._thumb_h = VIEW_SIZES.get(view_mode, VIEW_SIZES["medium"])
            self._thumb_w = self._card_w
        self._fav = getattr(asset, "favorite", False) or False
        self._theme = "light"
        if self._card_w:
            self.setFixedWidth(self._card_w)
        else:
            self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.setCursor(Qt.PointingHandCursor)
        self._selected = False
        self._build()
        self._setup_hover_lift()
        # Force fixed height to prevent overlapping — bypass Qt's adjustSize()
        # which returns inconsistent values causing cards to overlap in grid mode.
        if self.view_mode == "list":
            self.setFixedHeight(LIST_CARD_HEIGHT)
        else:
            # Icon/grid mode: use size-tier-specific fixed height
            self.setFixedHeight(ICON_CARD_HEIGHTS.get(self.view_mode, 190))

    # ---- D-3 micro-interaction: animated hover "lift" ----------------------
    # Qt stylesheets silently ignore `box-shadow`, so the shadow *scale* in
    # style.py never actually renders. A real QGraphicsDropShadowEffect whose
    # blur/offset is animated on hover gives the card genuine depth + a 160ms
    # ease, turning a static grid into a tactile one.
    def _setup_hover_lift(self):
        tok = THEMES.get(self._theme, THEMES["light"])
        eff = QGraphicsDropShadowEffect(self)
        eff.setBlurRadius(10.0)
        eff.setXOffset(0.0)
        eff.setYOffset(2.0)
        eff.setColor(QColor(15, 23, 42, 40))
        self.setGraphicsEffect(eff)
        self._shadow = eff
        self._lift_anim = QPropertyAnimation(eff, b"blurRadius", self)
        self._lift_anim.setDuration(160)
        self._lift_anim.setEasingCurve(QEasingCurve.OutCubic)
        self._drop_anim = QPropertyAnimation(eff, b"yOffset", self)
        self._drop_anim.setDuration(160)
        self._drop_anim.setEasingCurve(QEasingCurve.OutCubic)

    def _animate_lift(self, hovered):
        if not hasattr(self, "_shadow"):
            return
        blur_to = 26.0 if hovered else 10.0
        off_to = 10.0 if hovered else 2.0
        for anim, end in ((self._lift_anim, blur_to), (self._drop_anim, off_to)):
            anim.stop()
            anim.setEndValue(end)
            anim.start()

    def _build(self):
        self.thumb = _RoundedPixmapLabel(radius=16)
        self.thumb.setFixedHeight(self._thumb_h)
        if self.view_mode == "list":
            self.thumb.setFixedWidth(self._thumb_w)
        self.thumb.setAlignment(Qt.AlignCenter)
        self._set_thumb_pixmap()

        # engine version badge (bottom-right) — only for assets detected
        # inside a UE project. Mirrors the tier/fav overlay pattern. The
        # semi-transparent dark pill stays legible over any thumbnail.
        self.engine_badge = QLabel(self.thumb)
        self.engine_badge.setObjectName("cardengine")
        self.engine_badge.setText(getattr(self.asset, "engine_version", "") or "")
        self.engine_badge.setStyleSheet(
            "background: rgba(15,23,42,0.72); color:#ffffff; "
            "border-radius:6px; padding:2px 6px; "
            "font-size:11px; font-weight:600;")
        self.engine_badge.adjustSize()
        self.engine_badge.move(
            max(2, self._thumb_w - self.engine_badge.width() - 8),
            max(2, self._thumb_h - self.engine_badge.height() - 8))
        self.engine_badge.setVisible(bool(getattr(self.asset, "engine_version", "")))

        if self.view_mode == "list":
            v = QHBoxLayout(self)
        else:
            v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        v.addWidget(self.thumb)

        # tier badge (top-left)
        self.tier = QLabel(self.thumb)
        tier_key = getattr(self.asset, "tier", 1) or 1
        self.tier.setText(tr(TIER_LABEL.get(tier_key, "tier_engine")))
        self.tier.setObjectName("cardtier")
        self.tier.adjustSize()
        self.tier.move(8, 8)
        self.tier.setVisible(self._tier_visible())

        # selection dot is drawn directly in paintEvent() — no overlay
        # button. The card itself is the click target; Ctrl+click toggles
        # selection without firing the activated signal.

        # fav (top-right)
        self.fav = QPushButton(self.thumb)
        self.fav.setObjectName("cardfav")
        self.fav.setFixedSize(28, 28)
        self.fav.clicked.connect(self._on_fav)
        self._style_fav()
        # fav shows on hover or when already favorited (reduces grid noise)
        self.fav.setHidden(not self._fav)

        # selection highlight border (painted in paintEvent)
        self._sel_color = QColor(THEMES.get(self._theme, THEMES["light"])["accent"])

        # ---- body ----
        body = QWidget()
        body.setStyleSheet("background:transparent;")
        bl = QVBoxLayout(body)
        bl.setContentsMargins(10, 6, 10, 8)
        bl.setSpacing(4)

        self.name = QLabel(self.asset.name)
        self.name.setObjectName("cardname")
        self.name.setFixedHeight(16)
        self.name.setWordWrap(False)
        self.name.setToolTip(self.asset.name)
        self._elide_name()

        meta = QHBoxLayout()
        meta.setContentsMargins(0, 0, 0, 0)
        meta.setSpacing(5)
        meta.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        tcolor, tbg = TYPE_CHIP.get(self.asset.type, DEFAULT_CHIP)
        self.chip = QLabel(self.asset.type)
        self.chip.setObjectName("cardtypechip")
        self.chip.setProperty("type", self.asset.type)
        self.chip.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        self.chip.setFixedHeight(18)
        self.chip.adjustSize()
        self.chip.setFixedWidth(self.chip.width())
        self.tag = QLabel()
        self.tag.setObjectName("cardtag")
        self.tag.setFixedHeight(16)
        self.tag.setWordWrap(False)
        self.tag.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._refresh_tag_text()
        meta.addWidget(self.chip)
        if getattr(self.asset, "blueprint", False):
            tok = THEMES.get(self._theme, THEMES["light"])
            self.bp_chip = QLabel(tr("bp_badge"))
            self.bp_chip.setToolTip(tr("bp_tip"))
            self.bp_chip.setObjectName("cardbpchip")
            self.bp_chip.setFixedHeight(18)
            self.bp_chip.adjustSize()
            self.bp_chip.setFixedWidth(self.bp_chip.width())
            meta.addWidget(self.bp_chip)
        meta.addWidget(self.tag, 1)

        bl.addWidget(self.name)
        bl.addLayout(meta)
        v.addWidget(body)

    def _tier_visible(self):
        tk = getattr(self.asset, "tier", 1) or 1
        return tk >= 2

    def _health(self):
        return getattr(self.asset, "health", "ok") or "ok"

    def _elide_name(self):
        fm = QFontMetrics(self.name.font())
        maxw = (self._card_w or 9999) - 22
        self.name.setText(fm.elidedText(self.asset.name, Qt.ElideRight, maxw))

    def _refresh_tag_text(self):
        raw = self.asset.tags.split(",")[0] if self.asset.tags else ""
        if not raw:
            self.tag.setText("")
            self.tag.setToolTip("")
            return
        fm = QFontMetrics(self.tag.font())
        maxw = (self._card_w or 9999) - 22 - self.chip.width() - 8 - 7
        bp = getattr(self, "bp_chip", None)
        if bp is not None:
            maxw -= bp.width() + 7
        self.tag.setText(fm.elidedText(raw.strip(), Qt.ElideRight, max(20, maxw)))
        self.tag.setToolTip(raw.strip())

    def _set_thumb_pixmap(self):
        pm = QPixmap()
        if self.asset.thumb_path and os.path.exists(self.asset.thumb_path):
            pm = _crop_to_square(self.asset.thumb_path, self._thumb_w, self._thumb_h)
        if pm.isNull():
            pm = _placeholder(self.asset.type, self._thumb_w, self._thumb_h)
        self.thumb.setPixmap(pm)

    def _style_fav(self):
        col = "#f5a623" if self._fav else "#ffffff"
        solid = self._fav
        self.fav.setIcon(icon("fav", col, 15, solid=solid))

    def _on_fav(self):
        self._fav = not self._fav
        self._style_fav()
        self.asset.favorite = self._fav
        from PySide6.QtCore import QTimer
        QTimer.singleShot(0, lambda: self._on_fav_changed())

    def _on_fav_changed(self):
        from PySide6.QtWidgets import QApplication
        parent_grid = self.parentWidget().parentWidget().parentWidget() if self.parentWidget() else None
        while parent_grid and not isinstance(parent_grid, AssetGrid):
            parent_grid = parent_grid.parentWidget()
        if parent_grid:
            parent_grid.fav_changed.emit(self.asset, self._fav)

    def set_selected(self, b):
        self._selected = b
        self.update()
        # Deepen shadow on selection for tactile "lift" feedback
        if hasattr(self, "_shadow"):
            if b:
                self._shadow.setBlurRadius(22.0)
                self._shadow.setYOffset(6.0)
                col = QColor(99, 91, 255, 70) if self._theme == "light" else QColor(0, 0, 0, 150)
                self._shadow.setColor(col)
            else:
                self._shadow.setBlurRadius(10.0)
                self._shadow.setYOffset(2.0)
                self._shadow.setColor(QColor(15, 23, 42, 40) if self._theme == "light"
                                      else QColor(0, 0, 0, 110))
        if b:
            self.tier.hide()
        else:
            self.tier.setVisible(self._tier_visible())

    def refresh_thumb(self, path, tier=None):
        self.asset.thumb_path = path
        if tier is not None:
            self.asset.tier = tier
        self._set_thumb_pixmap()
        if tier is not None:
            tk = getattr(self.asset, "tier", 1) or 1
            self.tier.setText(tr(TIER_LABEL.get(tk, "tier_engine")))
            self.tier.setVisible(self._tier_visible())

    def set_theme(self, theme):
        self._theme = theme
        tok = THEMES.get(theme, THEMES["light"])
        self._sel_color = QColor(tok["accent"])
        self.name.setStyleSheet("font-weight:600; font-size:13px; color:%s;" % tok["text"])
        self.tag.setStyleSheet("color:%s; font-size:12px" % tok["muted"])
        if hasattr(self, "_shadow"):
            # deeper, more opaque shadow reads better on dark surfaces
            self._shadow.setColor(QColor(0, 0, 0, 110) if theme == "dark"
                                  else QColor(15, 23, 42, 40))
        if self._selected:
            self.set_selected(True)

    def mousePressEvent(self, e):
        if e.button() == Qt.RightButton:
            self.context.emit(self.asset, self.mapToGlobal(e.pos()))
            return
        modifiers = QApplication.keyboardModifiers()
        if modifiers == Qt.ControlModifier:
            # Ctrl+click: toggle without losing other selections
            self.set_selected(not self._selected)
            self.toggled.emit(self.asset, self._selected)
        elif modifiers == Qt.ShiftModifier:
            # Shift+click: range select from parent grid's anchor
            parent_grid = self._find_grid()
            if parent_grid:
                parent_grid._shift_select_to(self.index)
        else:
            # Normal click: select this card, deselect others
            parent_grid = self._find_grid()
            if parent_grid:
                parent_grid._clear_selection(keep=self)
            self.set_selected(True)
            self.toggled.emit(self.asset, True)
            self.activated.emit(self.asset)

    def mouseDoubleClickEvent(self, e):
        if e.button() == Qt.LeftButton:
            parent_grid = self._find_grid()
            if parent_grid:
                parent_grid.reveal_requested.emit(self.asset)

    def _find_grid(self):
        p = self.parentWidget()
        while p:
            if isinstance(p, AssetGrid):
                return p
            if hasattr(p, 'parent'):
                p = p.parentWidget()
            else:
                break
        return None

    def enterEvent(self, e):
        # show fav on hover (hidden again on leave unless favorited)
        self.fav.show()
        self._animate_lift(True)
        super().enterEvent(e)

    def leaveEvent(self, e):
        if not self._fav:
            self.fav.hide()
        self._animate_lift(False)
        super().leaveEvent(e)

    def resizeEvent(self, e):
        w = self.thumb.width()
        h = self.thumb.height()
        self.tier.move(8, 8)
        self.tier.adjustSize()
        self.fav.move(w - 8 - 28, 8)
        self._elide_name()
        self._refresh_tag_text()
        super().resizeEvent(e)

    def paintEvent(self, e):
        super().paintEvent(e)
        # Selection indicator: a small accent dot in the top-left corner,
        # drawn directly in the card's own paintEvent so we don't have to
        # rely on a separate QPushButton overlay (which previously rendered
        # as a loud blue square and made the card look like it had two
        # stacked borders).
        if self._selected:
            p = QPainter(self)
            p.setRenderHint(QPainter.Antialiasing)
            d = 12                 # dot diameter
            m = 8                  # margin from corner
            # Soft dark backdrop so the accent stays legible on any thumb
            p.setBrush(QColor(15, 23, 42, 170))
            p.setPen(Qt.NoPen)
            p.drawEllipse(m, m, d, d)
            # Accent ring + check inside
            pen = QPen(QColor(self._sel_color))
            pen.setWidthF(1.5)
            p.setPen(pen)
            p.setBrush(Qt.NoBrush)
            p.drawEllipse(m + 0.75, m + 0.75, d - 1.5, d - 1.5)
            p.setPen(QPen(QColor("#ffffff")))
            p.setRenderHint(QPainter.Antialiasing)
            cx, cy = m + d / 2, m + d / 2
            check = QPainterPath()
            check.moveTo(cx - 3.0, cy + 0.2)
            check.lineTo(cx - 0.8, cy + 2.4)
            check.lineTo(cx + 3.2, cy - 2.4)
            p.drawPath(check)
            p.end()


# ---------------------------------------------------------------------------
# Grid content widget with rubber-band selection support
# ---------------------------------------------------------------------------

class _GridContent(QWidget):
    def __init__(self, grid):
        super().__init__()
        self.grid = grid
        self._origin = None

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton and not self._child_at(e.pos()):
            # Click on empty area — start rubber band or deselect all
            mods = QApplication.keyboardModifiers()
            if not (mods & (Qt.ControlModifier | Qt.ShiftModifier)):
                self.grid._clear_selection()
            self._origin = e.pos()
            self.grid._rubber.hide()
            self.grid._rubber.setGeometry(QRect(self._origin, QSize()))
            self.grid._rubber.show()
            return
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        if self._origin:
            rect = QRect(self._origin, e.pos()).normalized()
            self.grid._rubber.setGeometry(rect)
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):
        if self._origin:
            self.grid._rubber.hide()
            rect = QRect(self._origin, e.pos()).normalized()
            self._origin = None
            if rect.width() > 5 or rect.height() > 5:
                # Rubber band selection
                mods = QApplication.keyboardModifiers()
                if not (mods & Qt.ControlModifier):
                    self.grid._clear_selection()
                for card in self.grid._live.values():
                    card_pos = card.mapTo(self, QPoint(0, 0))
                    card_rect = QRect(card_pos, card.size())
                    if rect.intersects(card_rect):
                        if not card._selected:
                            card.set_selected(True)
                            card.toggled.emit(card.asset, True)
            else:
                # Just a click on empty — deselect all
                pass
        super().mouseReleaseEvent(e)

    def _child_at(self, pos):
        """Check if pos is over any card widget."""
        for card in self.grid._live.values():
            if card.geometry().contains(pos):
                return card
        return None


# ---------------------------------------------------------------------------
# AssetGrid — scrollable card grid
# ---------------------------------------------------------------------------

class AssetGrid(QScrollArea):
    asset_activated = Signal(object)
    asset_context = Signal(object, QPoint)
    selection_changed = Signal(int)
    reveal_requested = Signal(object)
    fav_changed = Signal(object, bool)
    empty_action = Signal()

    def __init__(self):
        super().__init__()
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        # Custom scrollbar styling applied via stylesheet in style.py

        self.content = _GridContent(self)
        self.setWidget(self.content)
        # Virtual scrolling: only cards inside the visible window are
        # instantiated (O(visible), never O(total)), so the grid stays
        # usable on libraries with tens of thousands of .uasset files.
        self._live = {}            # index -> AssetCard (visible only)
        self.assets = []           # full source-of-truth list (windowed)
        self._theme = "light"
        self._anchor_index = -1
        self._selected = set()     # object_path strings (survives windowing)
        self._rubber = QRubberBand(QRubberBand.Rectangle, self.content)
        self._rubber.hide()
        self._empty_label = None
        self._empty_widget = None
        self._empty_cta = None
        self._card_w = 0
        self._card_h = 0
        self._margin = 14
        self._gap = 14
        self._list_gap = 8  # tighter row spacing for list mode
        self.view_mode = "medium"
        self.verticalScrollBar().valueChanged.connect(
            lambda _=None: self._refill_window())

    # Back-compat: visible live cards (prefer total_count for counts)
    @property
    def cards(self):
        return list(self._live.values())

    def total_count(self):
        return len(self.assets)

    def _clear_live(self):
        # Synchronous removal: deleteLater() is ASYNCHRONOUS — it only marks
        # widgets for deletion when control returns to the event loop.  If
        # _refill_window() runs immediately after (as it does in set_assets),
        # the old cards are still in the widget tree and paint ON TOP of the
        # newly created cards, making the grid appear "stale" until the user
        # interacts with another widget (e.g. a toolbar combo) that lets the
        # event loop process pending deletions.
        # Fix: unparent synchronously so old cards vanish instantly, then
        # schedule C++ cleanup for later.
        for c in self._live.values():
            c.hide()
            c.setParent(None)
            c.deleteLater()
        self._live = {}

    def _measure_card(self):
        """Probe one card to learn its true height/width for geometry."""
        if self._card_h and (self.view_mode == "list" or self._card_w):
            return
        if not self.assets:
            return
        # Use forced fixed heights — avoid adjustSize() which returns
        # inconsistent values causing card overlap in icon/grid mode.
        if self.view_mode == "list":
            self._card_h = LIST_CARD_HEIGHT
            return
        if self.view_mode in ICON_CARD_HEIGHTS:
            self._card_h = ICON_CARD_HEIGHTS[self.view_mode]
        else:
            # Fallback: probe for unknown view modes
            probe = AssetCard(self.assets[0], index=0, view_mode=self.view_mode)
            probe.setParent(self.content)
            probe.adjustSize()
            self._card_h = probe.height()
            if self.view_mode != "list":
                self._card_w = probe.width()
            probe.deleteLater()
            return
        # Measure width from a probe (height is already known from above)
        probe = AssetCard(self.assets[0], index=0, view_mode=self.view_mode)
        probe.setParent(self.content)
        probe.adjustSize()
        if self.view_mode != "list":
            self._card_w = probe.width()
        probe.deleteLater()

    def set_theme(self, theme):
        self._theme = theme
        for c in self.cards:
            c.set_theme(theme)
        if self._empty_widget is not None and self._empty_widget.isVisible():
            self._show_empty()

    def set_assets(self, assets):
        self._clear_live()
        self._clear_empty()
        self.assets = list(assets)
        # Preserve selection for assets that survive the new filter/view.
        # A no-op re-filter (e.g. a trailing search-debounce timer) keeps the
        # user's selection intact; switching views naturally drops assets that
        # are no longer present via the intersection below.
        valid = {a.object_path for a in self.assets}
        kept = {p for p in self._selected if p in valid}
        if kept != self._selected:
            self._selected = kept
            self.selection_changed.emit(len(self._selected))
        if self._anchor_index >= len(self.assets):
            self._anchor_index = -1
        self._relayout()
        # Synchronous repaint.  update() alone is asynchronous and can be
        # swallowed when set_assets() runs right after a batch of sidebar
        # widget rebuilds (setParent/deleteLater/layout in _refresh_tag_browser),
        # which is exactly why the grid looked "stale" until the user
        # clicked a toolbar widget and the event loop finally painted it.
        # repaint() forces the paint *now* so the filtered grid shows
        # immediately after a tag/folder click.
        self.viewport().repaint()
        # Decisive state dump: if live==expected but user sees stale pixels,
        # it is a pure paint problem; if live is wrong/zero, the virtual-
        # scroll windowing used a stale viewport width / card height.
        _gdbg("SET_ASSETS src=%d live=%d vpW=%d vpH=%d cols=%d "
               "cardW=%d cardH=%d scroll=%d"
               % (len(self.assets), len(self._live),
                  self.viewport().width(), self.viewport().height(),
                  self._cols(), self._card_w, self._card_h,
                  self.verticalScrollBar().value()))

    def _cols(self):
        if self.view_mode == "list":
            return 1
        cw = VIEW_SIZES.get(self.view_mode, VIEW_SIZES["medium"])[0]
        w = self.viewport().width() - 28
        c = max(1, w // (cw + 14))
        return c

    def _relayout(self):
        """Size the canvas to hold every card, then window only the
        visible ones. This is the virtual-scrolling core: the number of
        live QWidget cards stays O(visible), never O(total)."""
        if not self.assets:
            self.content.setFixedSize(
                max(1, self.viewport().width()),
                max(1, self.viewport().height()))
            self._show_empty()
            return
        self._clear_empty()
        if self._card_h == 0:
            self._measure_card()
        cols = self._cols()
        n = len(self.assets)
        rows = (n + cols - 1) // cols
        m, g = self._margin, self._gap
        if self.view_mode == "list":
            cw = max(1, self.viewport().width() - 28)
            ch = LIST_CARD_HEIGHT
            W = self.viewport().width()
            H = m * 2 + rows * ch + (rows - 1) * self._list_gap
        else:
            cw = VIEW_SIZES.get(self.view_mode, VIEW_SIZES["medium"])[0]
            ch = self._card_h or (THUMB_H + 62)
            W = m * 2 + cols * cw + (cols - 1) * g
            H = m * 2 + rows * ch + (rows - 1) * g
        self._card_w, self._card_h = cw, ch
        self.content.setFixedSize(W, H)
        self._refill_window()

    def _refill_window(self):
        if not self.assets or self._card_h == 0:
            return
        cols = self._cols()
        n = len(self.assets)
        rows = (n + cols - 1) // cols
        vp = self.viewport()
        m, g, cw, ch = self._margin, self._gap, self._card_w, self._card_h
        yg = self._list_gap if self.view_mode == "list" else g
        vh = vp.height() or 600
        top = self.verticalScrollBar().value()
        bottom = top + vh
        first_row = max(0, (top - m) // (ch + yg) - 1)
        last_row = min(rows - 1, (bottom - m) // (ch + yg) + 1)
        first = first_row * cols
        last = min(n - 1, (last_row + 1) * cols - 1)
        # evict off-window cards
        for idx in [k for k in self._live if k < first or k > last]:
            self._live.pop(idx).deleteLater()
        # create on-window cards
        for i in range(first, last + 1):
            if i in self._live:
                continue
            a = self.assets[i]
            card = AssetCard(a, index=i, view_mode=self.view_mode)
            card.setParent(self.content)
            if self.view_mode == "list":
                card.setFixedWidth(max(1, self.viewport().width() - 28))
            card.set_theme(self._theme)
            card.activated.connect(self.asset_activated)
            card.toggled.connect(self._on_toggled)
            card.context.connect(self.asset_context)
            if a.object_path in self._selected:
                card.set_selected(True)
            r, c = divmod(i, cols)
            yg = self._list_gap if self.view_mode == "list" else g
            card.move(m + c * (cw + g), m + r * (ch + yg))
            card.show()
            self._live[i] = card
        self._position_empty()

    def resizeEvent(self, e):
        self._relayout()
        self._position_empty()
        super().resizeEvent(e)

    def _empty_illustration(self, theme):
        """D-2: a lightweight, brand-tinted empty-state illustration painted
        with QPainter (no external SVG asset needed). A dashed 'canvas' frame
        with a stacked-asset glyph + accent sparkles reads warmer than bare
        text and stays crisp at any DPI."""
        tok = THEMES.get(theme, THEMES["light"])
        accent = QColor(tok["accent"])
        muted = QColor(tok.get("muted", "#94a3b8"))
        W, H = 140, 116
        dpr = self.devicePixelRatioF() if hasattr(self, "devicePixelRatioF") else 1.0
        pm = QPixmap(int(W * dpr), int(H * dpr))
        pm.setDevicePixelRatio(dpr)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        # dashed rounded canvas frame
        frame = QColor(muted)
        frame.setAlpha(150)
        pen = p.pen()
        pen.setColor(frame)
        pen.setWidthF(2.0)
        pen.setStyle(Qt.DashLine)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(QRectF(14, 22, 112, 80), 12, 12)
        # stacked asset tiles (back + front) in accent
        back = QColor(accent)
        back.setAlpha(60)
        front = QColor(accent)
        front.setAlpha(180)
        p.setPen(Qt.NoPen)
        p.setBrush(back)
        p.drawRoundedRect(QRectF(44, 46, 52, 40), 8, 8)
        p.setBrush(front)
        p.drawRoundedRect(QRectF(56, 38, 52, 40), 8, 8)
        # sparkle accents
        spark = QColor(accent)
        for cx, cy, s in ((34, 34, 5.0), (108, 96, 4.0), (120, 30, 3.0)):
            spark.setAlpha(230)
            p.setBrush(spark)
            path = QPainterPath()
            path.moveTo(cx, cy - s)
            path.lineTo(cx + s * 0.32, cy - s * 0.32)
            path.lineTo(cx + s, cy)
            path.lineTo(cx + s * 0.32, cy + s * 0.32)
            path.lineTo(cx, cy + s)
            path.lineTo(cx - s * 0.32, cy + s * 0.32)
            path.lineTo(cx - s, cy)
            path.lineTo(cx - s * 0.32, cy - s * 0.32)
            path.closeSubpath()
            p.drawPath(path)
        p.end()
        return pm

    def _show_empty(self):
        if self._empty_widget is None:
            self._empty_widget = QWidget(self.content)
            self._empty_widget.setObjectName("emptyhint")
            el = QVBoxLayout(self._empty_widget)
            el.setContentsMargins(40, 40, 40, 40)
            el.setSpacing(14)
            el.setAlignment(Qt.AlignCenter)
            self._empty_icon = QLabel()
            self._empty_icon.setObjectName("emptyillustration")
            self._empty_icon.setAlignment(Qt.AlignCenter)
            el.addWidget(self._empty_icon, alignment=Qt.AlignCenter)
            self._empty_label = QLabel()
            self._empty_label.setAlignment(Qt.AlignCenter)
            self._empty_label.setWordWrap(True)
            el.addWidget(self._empty_label)
            self._empty_cta = QPushButton(tr("scan_now"))
            self._empty_cta.setObjectName("primary")
            self._empty_cta.clicked.connect(lambda: self.empty_action.emit())
            el.addWidget(self._empty_cta, alignment=Qt.AlignCenter)
        self._empty_icon.setPixmap(self._empty_illustration(self._theme))
        self._empty_label.setText(tr("nores") + "\n\n" + tr("scan_dir_tip"))
        self._empty_label.setObjectName("cardemptylabel")
        self._empty_widget.show()
        self._position_empty()

    def _clear_empty(self):
        if self._empty_widget is not None:
            self._empty_widget.hide()

    def _position_empty(self):
        if self._empty_widget is not None and self._empty_widget.isVisible():
            w = min(440, self.content.width())
            h = self._empty_widget.sizeHint().height()
            x = (self.content.width() - w) // 2
            y = max(40, (self.content.height() - h) // 2)
            self._empty_widget.setGeometry(x, y, w, h)

    def _clear_selection(self, keep=None):
        """Deselect all cards except *keep* (if given). Selection is
        tracked at the grid level (self._selected) so it survives
        card recycling during virtual scrolling."""
        keep_path = keep.asset.object_path if keep is not None else None
        for c in self._live.values():
            if keep is not None and c.asset.object_path == keep_path:
                continue
            if c._selected:
                c.set_selected(False)
                c.toggled.emit(c.asset, False)
        if keep is not None:
            self._selected = {keep_path}
        else:
            self._selected.clear()
        self.selection_changed.emit(len(self._selected))

    def _shift_select_to(self, target_index):
        """Select a range from anchor to target (by asset index, so it
        works even when the in-between cards are not windowed)."""
        if self._anchor_index < 0:
            self._anchor_index = target_index
        lo = min(self._anchor_index, target_index)
        hi = max(self._anchor_index, target_index)
        for i, a in enumerate(self.assets):
            if lo <= i <= hi:
                self._selected.add(a.object_path)
            else:
                self._selected.discard(a.object_path)
        for c in self._live.values():
            sel = c.asset.object_path in self._selected
            if sel != c._selected:
                c.set_selected(sel)
                c.toggled.emit(c.asset, sel)
        self.selection_changed.emit(len(self._selected))

    def _on_toggled(self, asset, selected):
        if selected:
            self._selected.add(asset.object_path)
            self._anchor_index = self._card_index(asset)
        else:
            self._selected.discard(asset.object_path)
        self.selection_changed.emit(len(self._selected))

    def _card_index(self, asset):
        for i, a in enumerate(self.assets):
            if a.object_path == asset.object_path:
                return i
        return -1

    def _update_selected_set(self):
        # selection source-of-truth is self._selected; nothing to rebuild
        self.selection_changed.emit(len(self._selected))

    def selected_assets(self):
        return [a for a in self.assets if a.object_path in self._selected]

    def clear_selection(self):
        self._clear_selection()
        self._anchor_index = -1

    def select_only(self, asset):
        """Deselect everything, then select just *asset* (Eagle-like
        behavior when right-clicking an unselected card)."""
        self._clear_selection()
        ap = asset.object_path
        self._selected = {ap}
        for c in self._live.values():
            if c.asset.object_path == ap:
                if not c._selected:
                    c.set_selected(True)
                    c.toggled.emit(c.asset, True)
                self._anchor_index = c.index
        self.selection_changed.emit(1)

    def select_all(self):
        """Select every (filtered) asset — not just the visible window."""
        if not self.assets:
            return
        for a in self.assets:
            self._selected.add(a.object_path)
        for c in self._live.values():
            if not c._selected:
                c.set_selected(True)
                c.toggled.emit(c.asset, True)
            else:
                self._anchor_index = c.index
        self.selection_changed.emit(len(self._selected))

    def invert_selection(self):
        """Toggle every (filtered) asset."""
        if not self.assets:
            return
        for a in self.assets:
            if a.object_path in self._selected:
                self._selected.discard(a.object_path)
            else:
                self._selected.add(a.object_path)
        for c in self._live.values():
            sel = c.asset.object_path in self._selected
            if sel != c._selected:
                c.set_selected(sel)
                c.toggled.emit(c.asset, sel)
        self.selection_changed.emit(len(self._selected))

    def refresh_thumb(self, object_path, path, tier=None):
        # The card mutates the SHARED asset object (it is the same
        # instance held in self.assets), so the change persists when
        # the card is later recycled; repaint only if windowed now.
        for c in self._live.values():
            if c.asset.object_path == object_path:
                c.refresh_thumb(path, tier=tier)
