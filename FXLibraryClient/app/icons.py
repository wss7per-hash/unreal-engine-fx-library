# app/icons.py -- in-code SVG icon factory for the FX Library client.
# All icons are vector strings rendered to QIcon at runtime, so no external
# image assets are required at runtime. A logo .ico is generated separately
# (see tools/make_icons.py) for the standalone executable.

from PySide6.QtGui import QIcon, QPixmap, QPainter, QImage
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtCore import Qt, QRectF, QSize

# Accent color used for toolbar / action icons (works on both light & dark).
ICON_COLOR = "#7c6cff"

# ---- line icons (viewBox 0 0 24 24, stroke=currentColor) ----
_LINE = {
    "open": '<path d="M3 7h5l2 2h11v10H3z"/>',
    "copy": '<rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>',
    "refresh": '<path d="M20 11a8 8 0 1 0-1.5 5.3"/><path d="M20 4v5h-5"/>',
    "select": '<rect x="3" y="4" width="7" height="7" rx="1.5"/><rect x="14" y="4" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><path d="M17 14v7M14 17h7"/>',
    "thumbnail": '<rect x="3" y="4" width="18" height="16" rx="2"/><circle cx="9" cy="10" r="2"/><path d="M3 17l5-4 4 3 3-2 6 5"/>',
    "no_thumb": '<rect x="3" y="4" width="18" height="16" rx="2"/><circle cx="9" cy="10" r="2"/><path d="M3 17l5-4 4 3 3-2 6 5"/><path d="M2 2l20 20"/>',
    "export": '<path d="M12 3v11"/><path d="M8 10l4 4 4-4"/><path d="M4 19h16"/>',
    "import": '<path d="M12 15V4"/><path d="M8 8l4-4 4 4"/><path d="M4 19h16"/>',
    "health": '<path d="M3 12h4l2 5 4-12 2 7h6"/>',
    "settings": '<circle cx="12" cy="12" r="3"/><path d="M19 12a7 7 0 0 0-.1-1.2l2-1.6-2-3.4-2.4 1a7 7 0 0 0-2-1.2L16 2H8l-.5 2.6a7 7 0 0 0-2 1.2l-2.4-1-2 3.4 2 1.6A7 7 0 0 0 3 12a7 7 0 0 0 .1 1.2l-2 1.6 2 3.4 2.4-1a7 7 0 0 0 2 1.2L8 22h8l.5-2.6a7 7 0 0 0 2-1.2l2.4 1 2-3.4-2-1.6A7 7 0 0 0 19 12z"/>',
    "fav": '<path d="M12 17.3 6.2 21l1.5-6.5L2 9.2l6.6-.6L12 2.5l3.4 6.1 6.6.6-5.7 5.3L17.8 21z"/>',
    "search": '<circle cx="11" cy="11" r="7"/><path d="M21 21l-4-4"/>',
    "sun": '<circle cx="12" cy="12" r="4"/><path d="M12 2v3M12 19v3M2 12h3M19 12h3M5 5l2 2M17 17l2 2M19 5l-2 2M7 17l-2 2"/>',
    "moon": '<path d="M21 12.8A8.5 8.5 0 1 1 11.2 3a6.5 6.5 0 0 0 9.8 9.8z"/>',
    "close": '<path d="M6 6l12 12M18 6 6 18"/>',
    "clear": '<path d="M6 6l12 12M18 6 6 18"/>',
    "preview": '<path d="M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/>',
    "grid": '<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/>',
    "home": '<path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/>',
    "box": '<path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/><polyline points="3.27 6.96 12 12.01 20.73 6.96"/><line x1="12" y1="22.08" x2="12" y2="12"/>',
    "chevron-down": '<path d="M6 9l6 6 6-6"/>',
    "chevron-right": '<path d="M9 18l6-6-6-6"/>',
    "download": '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/>',
    "tag": '<path d="M20.59 13.41l-7.17 7.17a2 2 0 0 1-2.83 0L2 12V2h10l8.59 8.59a2 2 0 0 1 0 2.82z"/><circle cx="7" cy="7" r="1.5"/>',
    "folder": '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
    "plus": '<path d="M12 5v14M5 12h14"/>',
    "scan": '<path d="M3 7V5a2 2 0 0 1 2-2h2M17 3h2a2 2 0 0 1 2 2v2M21 17v2a2 2 0 0 1-2 2h-2M7 21H5a2 2 0 0 1-2-2v-2"/><path d="M3 12h18"/>',
    "trash": '<path d="M3 6h18M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6M10 11v6M14 11v6"/>',
    "library": '<path d="M3 4h4v16H3zM9 4h4v16H9zM15.5 4l3.5 1v15l-3.5-1z"/>',
    "uncategorized": '<rect x="3" y="3" width="18" height="18" rx="2"/><path d="M9 9h6M9 13h4M9 17h2" stroke-dasharray="2 2"/>',
    "no_tag": '<path d="M20.59 13.41l-7.17 7.17a2 2 0 0 1-2.83 0L2 12V2h10"/><path d="M2 2l20 20"/>',
    "recent": '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    "smart_folder": '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><path d="M9 11l1.5 1.5L13 10"/>',
    "community": '<circle cx="9" cy="7" r="3"/><circle cx="17" cy="9" r="2.5"/><path d="M3 20c0-3 2.5-5 6-5s6 2 6 5"/><path d="M14 20c0-2 1.5-3.5 3.5-3.5s3.5 1.5 3.5 3.5"/>',
    "tag_manage": '<path d="M20.59 13.41l-7.17 7.17a2 2 0 0 1-2.83 0L2 12V2h10"/><circle cx="7" cy="7" r="1.5"/><path d="M16 6h4M16 10h4" stroke-dasharray="1 2"/>',
    "terminal": '<rect x="2" y="4" width="20" height="16" rx="2"/><path d="M6 8l4 4-4 4"/><path d="M12 16h6"/>',
    "info": '<circle cx="12" cy="12" r="9"/><path d="M12 8h.01"/><path d="M12 11v6"/>',
}

# Type-specific glyphs used on card/hero placeholders (fill=none, stroke=#fff).
_TYPE_GLYPHS = {
    "Niagara": '<circle cx="12" cy="12" r="3"/><path d="M12 2v3M12 19v3M2 12h3M19 12h3M5 5l2 2M17 17l2 2M19 5l-2 2M7 17l-2 2"/>',
    "Cascade": '<path d="M12 2c4 5 4 8 0 11-4-3-4-6 0-11zM12 13c4 5 4 8 0 11-4-3-4-6 0-11z"/>',
}

# Solid glyphs (fill=currentColor) used for the fav star on/off.
_SOLID = {
    "fav": '<path d="M12 17.3 6.2 21l1.5-6.5L2 9.2l6.6-.6L12 2.5l3.4 6.1 6.6.6-5.7 5.3L17.8 21z"/>',
}


def _svg(name, solid=False):
    inner = _SOLID.get(name) if solid else _LINE.get(name)
    if not inner:
        return ""
    if solid:
        return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" '
                'fill="currentColor" stroke="none">' + inner + '</svg>')
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" '
            'fill="none" stroke="currentColor" stroke-width="2" '
            'stroke-linecap="round" stroke-linejoin="round">' + inner + '</svg>')


def icon(name, color=ICON_COLOR, size=22, solid=False):
    """Render a named icon to a QIcon at the given size in `color`."""
    svg = _svg(name, solid=solid)
    if not svg:
        return QIcon()
    svg = svg.replace("currentColor", color)
    renderer = QSvgRenderer()
    if not renderer.load(bytearray(svg.encode("utf-8"))):
        return QIcon()
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    renderer.render(p, QRectF(0, 0, size, size))
    p.end()
    return QIcon(pm)


def logo_pixmap(size=256, color_a="#635bff", color_b="#00a3ff"):
    """Render the FX Library logo (magic energy orb) to a QPixmap."""
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 256 256">'
        '<defs>'
        '<linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">'
        '<stop offset="0" stop-color="{a}"/><stop offset="1" stop-color="{b}"/>'
        '</linearGradient>'
        '<radialGradient id="orb" cx="50%" cy="50%" r="50%">'
        '<stop offset="0" stop-color="#ffffff" stop-opacity="0.95"/>'
        '<stop offset="0.45" stop-color="{a}" stop-opacity="0.85"/>'
        '<stop offset="1" stop-color="{b}" stop-opacity="0.65"/>'
        '</radialGradient>'
        '<filter id="glow" x="-50%" y="-50%" width="200%" height="200%">'
        '<feGaussianBlur stdDeviation="5" result="blur"/>'
        '<feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge>'
        '</filter>'
        '</defs>'
        '<rect width="256" height="256" rx="56" fill="url(#bg)"/>'
        '<g filter="url(#glow)">'
        '<circle cx="128" cy="128" r="58" fill="url(#orb)"/>'
        '<path d="M128 78 L139 119 L182 128 L140 137 L149 178 L128 146 L107 178 L116 137 L74 128 L117 119 Z" '
        'fill="#ffffff" opacity="0.92"/>'
        '<circle cx="128" cy="128" r="20" fill="#ffffff" opacity="0.85"/>'
        '</g>'
        '<circle cx="128" cy="128" r="76" fill="none" stroke="#ffffff" stroke-width="3" stroke-opacity="0.35"/>'
        '<circle cx="128" cy="128" r="92" fill="none" stroke="#ffffff" stroke-width="2" stroke-opacity="0.2" stroke-dasharray="14 10"/>'
        '</svg>'
    ).format(a=color_a, b=color_b)
    renderer = QSvgRenderer()
    if not renderer.load(bytearray(svg.encode("utf-8"))):
        return QPixmap()
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    renderer.render(p, QRectF(0, 0, size, size))
    p.end()
    return pm


# ---- application icon (window + exe) ----
_APP_ICON = None


def app_icon():
    global _APP_ICON
    if _APP_ICON is None:
        _APP_ICON = QIcon(logo_pixmap(256))
    return _APP_ICON


def type_glyph_pixmap(fx_type, size=64, color="#ffffff"):
    """Render a per-type glyph (e.g. Niagara, Cascade) to a QPixmap."""
    inner = _TYPE_GLYPHS.get(fx_type, _TYPE_GLYPHS.get("Cascade"))
    svg = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" '
           'fill="none" stroke="' + color + '" stroke-width="1.6" '
           'stroke-linecap="round" stroke-linejoin="round">' + inner + '</svg>')
    renderer = QSvgRenderer()
    if not renderer.load(bytearray(svg.encode("utf-8"))):
        return QPixmap()
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    renderer.render(p, QRectF(0, 0, size, size))
    p.end()
    return pm
