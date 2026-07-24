# app/style.py -- light/dark QSS for the FX Library client.
# Mirrors the HTML prototype's Stripe-like light theme + professional dark theme.

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt


THEMES = {
    "light": {
        "bg": "#f6f8fb", "bg2": "#ffffff", "panel": "#ffffff", "panel2": "#f1f4f9",
        "card": "#ffffff", "card_hover": "#ffffff", "card_sel": "#eef0ff",
        "border": "#e6e9ef", "border2": "#d3d9e3",
        "text": "#0a2540", "muted": "#5a6b82", "muted2": "#64748b",
        "accent": "#635bff", "accent2": "#00a3ff",
        "accent_hover": "#736aff", "accent_pressed": "#4338ca",
        "accent_tint": "rgba(99,91,255,0.10)",
        "input_bg": "#ffffff", "scroll": "#cdd5e0", "scroll_hover": "#b6c0cf",
        "log_bg": "#0b1220", "log_text": "#e6edf3", "log_border": "#1b2740",
        "dock_bg": "#ffffff", "dock_title": "#f3f4f6",
        "shadow": "rgba(10,37,64,0.10)",
        "shadow_sm": "rgba(10,37,64,0.06)",
        "shadow_md": "rgba(10,37,64,0.12)",
        "shadow_lg": "rgba(10,37,64,0.18)",
        "overlay": "rgba(10,37,64,0.55)",
        "ok": "#1aa179", "warn": "#f5a623", "bad": "#e25950",
        "amber": "#f5a623", "purple": "#7a5af8",
        "r_sm": "6px", "r_md": "12px", "r_lg": "16px", "r_pill": "999px",
    },
    "dark": {
        "bg": "#0e1116", "bg2": "#161b22", "panel": "#161b22", "panel2": "#1c222b",
        "card": "#1a2029", "card_hover": "#20272f", "card_sel": "rgba(124,108,255,0.12)",
        "border": "#272e38", "border2": "#333c48",
        "text": "#e6edf3", "muted": "#9aa7b5", "muted2": "#8a95a5",
        "accent": "#6d5df5", "accent2": "#3aa0ff",
        "accent_hover": "#8d80ff", "accent_pressed": "#6a5cf0",
        "accent_tint": "rgba(124,108,255,0.12)",
        "input_bg": "#11161d", "scroll": "#2c3440", "scroll_hover": "#3c4756",
        "log_bg": "#070b12", "log_text": "#cdd6e2", "log_border": "#1b2740",
        "dock_bg": "#161b22", "dock_title": "#1c222b",
        "shadow": "rgba(0,0,0,0.45)",
        "shadow_sm": "rgba(0,0,0,0.28)",
        "shadow_md": "rgba(0,0,0,0.45)",
        "shadow_lg": "rgba(0,0,0,0.62)",
        "overlay": "rgba(5,8,15,0.6)",
        "ok": "#1aa179", "warn": "#f5a623", "bad": "#e25950",
        "amber": "#f5a623", "purple": "#9a85ff",
        "r_sm": "6px", "r_md": "12px", "r_lg": "16px", "r_pill": "999px",
    },
}


_TEMPLATE = """
QWidget {{
    font-family: "Segoe UI", "Microsoft YaHei UI", sans-serif;
    font-size: 13px;
    color: {text};
}}
/* keyboard focus visibility (accessibility) */
QPushButton:focus, QPushButton#icon:focus, QPushButton#lang:focus,
QPushButton#seg:focus, QPushButton#tag:focus, QPushButton#act:focus,
QPushButton#secondary:focus, QPushButton#inspexp:focus,
QPushButton#danger:focus, QPushButton#batchbtnprimary:focus,
QPushButton#batchbtndanger:focus {{
    outline: 2px solid {accent};
    outline-offset: 2px;
}}
/* Star rating buttons — never show focus ring (they're tap targets, not form fields) */
QPushButton#star:focus {{ outline: none; }}
QPushButton#cardfav:focus {{ outline: none; }}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus,
QTextEdit:focus, QPlainTextEdit:focus {{
    outline: 2px solid {accent};
    outline-offset: 1px;
}}
QAbstractScrollArea:focus, AssetCard:focus, QFrame:focus, QMainWindow:focus {{
    outline: none;
}}
/* checked widgets already show a colored border — don't also draw a focus ring
   (prevents the "double box" the user saw on the active view segment). */
QPushButton:checked:focus, QPushButton#seg:focus:checked,
QPushButton#nav:focus:checked, QPushButton#tag:focus:checked,
QPushButton#icon:focus:checked, QPushButton#iconghost:focus:checked {{
    outline: none;
}}
QMainWindow {{ background: {bg}; }}
QMainWindow::separator {{ background: {border}; width: 1px; height: 1px; }}

/* ---------- tooltips ---------- */
QToolTip {{
    background-color: {bg2};
    color: {text};
    border: 1px solid {border};
    border-radius: {{r_sm}};
    padding: 6px 10px;
    /* No `opacity` — stacking with the top-level window's alpha makes the box
       look BLACK in light mode (user saw: hovering any setToolTip'd button
       showed a dark rectangle, not the themed {bg2}). */
}}
QToolTip:disabled {{ color: {muted2}; background-color: {panel2}; }}

/* ---------- docks ---------- */
QDockWidget {{
    border: 1px solid {border};
    border-radius: {{r_lg}};
    background: {dock_bg};
    margin: 8px;
}}
QDockWidget::title {{
    background: {dock_title};
    padding: 9px 12px;
    border-top-left-radius: 10px;
    border-top-right-radius: 10px;
    font-weight: 600;
    color: {muted};
}}
QDockWidget::close-button, QDockWidget::float-button {{
    border: none; background: transparent; padding: 4px; border-radius: 4px;
}}
QDockWidget::close-button:hover, QDockWidget::float-button:hover {{ background: {border}; }}

/* ---------- buttons ---------- */
QPushButton {{
    background: {accent};
    color: #ffffff;
    border: none;
    border-radius: {{r_md}};
    padding: 8px 14px;
    font-weight: 600;
    min-height: 28px;
}}
QPushButton:hover {{ background: {accent_hover}; }}
QPushButton:pressed {{ background: {accent_pressed}; }}
QPushButton:disabled {{ background: {border2}; color: {muted2}; }}

QPushButton#secondary {{
    background: {bg2};
    color: {text};
    border: 1px solid {border2};
    border-radius: {{r_md}};
    padding: 5px 12px;
}}
QPushButton#secondary:hover {{ background: {panel2}; border: 1px solid {muted2}; }}
QPushButton#secondary:pressed {{ background: {border}; }}

QPushButton#danger {{
    background: {bg2};
    color: #e5484d;
    border: 1px solid {border2};
    border-radius: {{r_md}};
    padding: 5px 10px;
    font-weight: 600;
    font-size: 12px;
}}
QPushButton#danger:hover {{ background: rgba(229,72,77,0.12); border-color: #e5484d; }}
QPushButton#danger:pressed {{ background: rgba(229,72,77,0.22); }}

QPushButton#sfbtn {{
    background: {bg2};
    color: {text};
    border: 1px solid {border};
    border-radius: {{r_md}};
    padding: 6px 10px;
    font-size: 12px;
    font-weight: 500;
    text-align: left;
}}
QPushButton#sfbtn:hover {{ background: {panel2}; border-color: {accent}; color: {accent}; }}
QPushButton#sfbtn:checked {{ background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 rgba(99,91,255,0.14), stop:1 rgba(0,163,255,0.06));
    border-color: {accent}; color: {accent}; font-weight: 600; }}

QPushButton#icon {{
    background: {bg2};
    color: {muted};
    border: 1px solid {border};
    border-radius: {{r_md}};
    padding: 5px;
    min-width: 30px; min-height: 30px;
}}
QPushButton#icon:hover {{ background: {panel2}; color: {accent}; border: 1px solid {border2}; }}
QPushButton#icon:checked {{ background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 {accent}, stop:1 {accent2}); color: #fff; border: 1px solid {accent}; }}
QPushButton#icon:checked:hover {{ background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 {accent_hover}, stop:1 #00b8ff); }}

/* Ghost icon button: no border/background until hover. Used for the small "+"
   buttons inside sidebar section headers so they don't read as a "box in a box". */
QPushButton#iconghost {{
    background: transparent;
    color: {muted};
    border: none;
    border-radius: {{r_sm}};
    padding: 3px;
    min-width: 24px; min-height: 24px;
}}
QPushButton#iconghost:hover {{ background: {panel2}; color: {accent}; }}
QPushButton#iconghost:pressed {{ background: {border}; }}

QPushButton#lang {{
    background: {bg2};
    color: {text};
    border: 1px solid {border};
    border-radius: {{r_md}};
    padding: 5px 9px;
    font-size: 11px;
    font-weight: 700;
    min-width: 42px;
}}
QPushButton#lang:hover {{ background: {panel2}; border: 1px solid {border2}; }}

QPushButton#nav {{
    background: transparent;
    color: {muted};
    border: 1px solid transparent;
    border-radius: {{r_md}};
    padding: 5px 10px;
    font-size: 12.5px;
    font-weight: 500;
    text-align: left;
    min-height: 26px;
}}
QPushButton#nav:hover {{
    background: {panel2};
    color: {text};
    border-color: {border};
}}
QPushButton#nav:checked {{
    /* Soft indigo→cyan gradient selected state with left accent rail. */
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 rgba(99,91,255,0.14), stop:1 rgba(0,163,255,0.06));
    border-left: 3px solid {accent};
    border-top: 1px solid {border};
    border-right: 1px solid {border};
    border-bottom: 1px solid {border};
    color: {accent};
    font-weight: 600;
}}

QPushButton#tag {{
    background: {bg2};
    color: {muted};
    border: 1px solid {border};
    border-radius: {{r_md}};
    padding: 3px 6px;
    font-size: 11px;
    font-weight: 500;
}}
QPushButton#tag:hover {{ border-color: {accent}; color: {accent}; background: {panel2}; }}
QPushButton#tag:checked {{
    border-color: {accent};
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 rgba(99,91,255,0.12), stop:1 rgba(99,91,255,0.06));
    color: {accent};
    font-weight: 600;
}}

QPushButton#tagchipbar {{
    background: {bg2};
    color: {muted};
    border: 1px solid {border};
    border-radius: {{r_md}};
    padding: 3px 9px;
    font-size: 11.5px;
    font-weight: 500;
    text-align: left;
    min-height: 24px;
}}
QPushButton#tagchipbar:hover {{ border-color: {accent}; color: {accent}; background: {panel2}; }}
QPushButton#tagchipbar:checked {{
    border-color: {accent};
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 rgba(99,91,255,0.16), stop:1 rgba(99,91,255,0.08));
    color: {accent};
    font-weight: 600;
}}

QLabel#taghint {{
    color: {muted2};
    font-size: 11px;
    padding: 2px 4px;
}}

QFrame#tagsep {{
    background: {border};
    border: none;
    max-height: 1px;
}}

QScrollArea#tagscroll {{
    background: transparent;
    border: none;
}}

QPushButton#act {{
    background: {bg2};
    color: {text};
    border: 1px solid {border};
    border-radius: {{r_md}};
    padding: 5px 10px;
    font-weight: 600;
    font-size: 12px;
}}
QPushButton#act:hover {{ background: {panel2}; border: 1px solid {border2}; }}
QPushButton#act:pressed {{ background: {border}; }}
/* Primary CTA: Stripe-inspired indigo→cyan dual-tone gradient (the
   "soft glow" soul of the redesign). White text stays ≥4.5:1 contrast. */
QPushButton#primary {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 {accent}, stop:1 {accent2});
    color: #ffffff;
    border: none;
    border-radius: {{r_md}};
    padding: 8px 16px;
    font-weight: 700;
}}
QPushButton#primary:hover {{ background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 {accent_hover}, stop:1 #00b8ff);
    color: #ffffff; outline: 2px solid {accent}; outline-offset: 1px; }}
QPushButton#primary:pressed {{ background: {accent_pressed}; color: #ffffff; }}

/* Toolbar primary action — same gradient as #primary but compact padding to
   match adjacent #act buttons in the toolbar row (user: "扫描目录比同一排的按钮宽"). */
QPushButton#toolbarprimary {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 {accent}, stop:1 {accent2});
    color: #ffffff;
    border: none;
    border-radius: {{r_md}};
    padding: 5px 10px;
    font-weight: 600;
}}
QPushButton#toolbarprimary:hover {{ background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 {accent_hover}, stop:1 #00b8ff);
    color: #ffffff; }}
QPushButton#toolbarprimary:pressed {{ background: {accent_pressed}; color: #ffffff; }}

/* ---------- line edits ---------- */
QLineEdit {{
    background: {input_bg};
    border: 1px solid {border2};
    border-radius: {{r_md}};
    padding: 8px 10px;
    min-height: 20px;
    color: {text};
}}
QLineEdit:focus {{ border: 1px solid {accent}; }}
QLineEdit:disabled {{ background: {panel2}; color: {muted2}; }}
QTextEdit, QPlainTextEdit {{
    background: {input_bg};
    border: 1px solid {border};
    border-radius: {{r_md}};
    padding: 8px;
    color: {text};
}}

/* ---------- labels ---------- */
QLabel {{ color: {muted}; }}
QLabel#title {{ font-size: 16px; font-weight: 700; color: {text}; }}
QLabel#subtitle {{ font-size: 12px; color: {muted2}; }}
QLabel#section {{ font-size: 16px; font-weight: 700; color: {text}; }}
QLabel#count {{ font-size: 12px; color: {muted}; }}
QLabel#navcount {{
    font-size: 11px; color: {muted2}; background: {panel2};
    border-radius: {{r_sm}}; padding: 1px 7px;
}}
QLabel#brand {{ font-size: 16px; font-weight: 700; color: {text}; }}
QLabel#tagline {{ font-size: 11px; color: {muted}; }}
QLabel#projname {{ font-size: 12px; color: {text}; font-weight: 600; }}
QLabel#projver {{ font-size: 12px; color: {muted2}; }}
QLabel#navtitle {{
    font-size: 11px; text-transform: uppercase; letter-spacing: 0.8px;
    color: {muted2}; font-weight: 700;
}}
QLabel#selhint {{
    color: {accent}; border-radius:8px;
    padding:4px 11px; font-size:12px; font-weight:600;
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 rgba(99,91,255,0.12), stop:1 rgba(0,163,255,0.08));
}}
QLabel#healthpill {{
    border-radius: {{r_sm}}; padding: 3px 10px; font-size: 11px; font-weight: 700;
}}

/* ---------- scroll areas / grid ---------- */
/* NOTE: do NOT force a background on every QWidget child of a scroll area —
   that was painting the inspector/folder tree white in dark mode and greying
   out card internals. Set the viewport explicitly instead. */
QScrollArea {{ background: transparent; border: none; }}
QScrollArea::viewport {{ background: {bg2}; }}

/* ---------- scrollbars ---------- */
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 0; border-radius: 5px; }}
QScrollBar::handle:vertical {{ background: {scroll}; min-height: 30px; border-radius: 5px; }}
QScrollBar::handle:vertical:hover {{ background: {scroll_hover}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; border-radius: 5px; }}
QScrollBar::handle:horizontal {{ background: {scroll}; min-width: 30px; border-radius: 5px; }}
QScrollBar::handle:horizontal:hover {{ background: {scroll_hover}; }}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}

/* ---------- status bar ---------- */
QStatusBar {{ background: {bg2}; border-top: 1px solid {border}; color: {muted}; padding: 4px 12px; min-height: 22px; }}
QStatusBar::item {{ border: none; }}

/* ---------- dialogs ---------- */
QDialog {{ background: {bg2}; }}
QDialog QFormLayout QLabel {{ color: {text}; font-weight: 500; }}
QMessageBox {{ background: {bg2}; }}
QMessageBox QPushButton {{ min-width: 80px; }}
QInputDialog {{ background: {bg2}; }}

/* ---------- combo box ---------- */
QComboBox {{
    background: {input_bg};
    border: 1px solid {border2};
    border-radius: {{r_md}};
    padding: 6px 10px;
    min-width: 110px;
    min-height: 30px;
    color: {text};
}}
QComboBox:hover {{ border: 1px solid {accent}; }}
QComboBox:focus {{ border: 1px solid {accent}; }}
QComboBox:hover::down-arrow {{ border-top-color: {accent}; }}
QComboBox::drop-down {{
    border: none;
    border-top-right-radius: {{r_md}};
    border-bottom-right-radius: {{r_md}};
    width: 24px;
}}
QComboBox::down-arrow {{
    image: none;
    border-left: 5px solid transparent;
    border-right: 5px solid transparent;
    border-top: 6px solid {muted2};
    margin-right: 8px;
}}
QComboBox QAbstractItemView {{
    background: {bg2}; color: {text}; border: 1px solid {border};
    selection-background-color: {accent};
}}

/* ---------- log (terminal-style, dark on both themes) ---------- */
QPlainTextEdit#log, QTextEdit#log {{
    background: {log_bg};
    color: {log_text};
    border: 1px solid {log_border};
    border-radius: {{r_md}};
    padding: 10px;
    font-family: "Consolas", "SF Mono", "Microsoft YaHei Mono", monospace;
    font-size: 12px;
}}
QPlainTextEdit#log QScrollBar::handle:vertical, QTextEdit#log QScrollBar::handle:vertical {{ background: #2c3440; }}
QPlainTextEdit#log QScrollBar::handle:vertical:hover, QTextEdit#log QScrollBar::handle:vertical:hover {{ background: #3c4756; }}

/* ---------- menu ---------- */
QMenu {{ background: {bg2}; border: 1px solid {border}; border-radius: {{r_md}}; padding: 6px; color: {text}; }}
QMenu::item {{ padding: 7px 18px 7px 12px; border-radius: {{r_sm}}; }}
QMenu::item:selected {{ background: {accent}; color: #fff; }}

/* ---------- asset cards ---------- */
/* Elevation scale (ambient + key baked into one shadow per level,
   since Qt QSS box-shadow takes a single layer): sm at rest,
   md on hover, lg on selection. Gives real "lift" depth. */
AssetCard {{
    background: {card};
    border: 1px solid {border};
    border-radius: {{r_lg}};
    box-shadow: 0 1px 2px {shadow_sm};
}}
AssetCard:hover {{ border: 1px solid {border2}; box-shadow: 0 8px 20px {shadow_md}; }}
AssetCard[selected="true"] {{
    border: 2px solid {accent};
    background: {card_sel};
    box-shadow: 0 12px 28px {shadow_lg};
}}

/* ---------- batch bar / lightbox / inspector frames ---------- */
QFrame#batchbar {{
    background: {bg2};
    border: 1px solid {border2};
    border-radius: {{r_pill}};
}}
QFrame#lightbox {{
    background: {overlay};
}}
QFrame#insphero {{
    border-radius: {{r_lg}};
    border: 1px solid {border};
}}
QFrame#sidebar {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 rgba(99,91,255,0.03), stop:1 {bg2});
    border-right: 1px solid {border};
}}
QFrame#navsection {{
    background: transparent;
}}
/* Collapsible sidebar section header — hover affordance so the bare titles
   (Tags / Smart Folders / Management) read as interactive rows, not text. */
QWidget#navheader {{
    border-radius: {{r_sm}};
    padding: 2px 4px;
}}
QWidget#navheader:hover {{ background: {panel2}; }}
QLabel#navarrow {{
    color: {muted2};
    font-size: 11px;
}}
/* Library selector row (top of sidebar) — tokenized so it follows theme switch
   (was inline QSS that stayed light in dark mode). Read as a section title
   (muted color + bold), matching the QWidget#navheader section labels below. */
QPushButton#libbtn {{
    background: transparent;
    color: {muted};
    border: none;
    border-radius: {{r_md}};
    padding: 6px 8px 6px 10px;
    font-weight: 700;
    font-size: 13px;
    text-align: left;
}}
QPushButton#libbtn:hover {{ background: {panel2}; color: {text}; }}
/* Folder tree — tokenized. Inline QSS was baked at build time and did NOT
   update on theme switch, leaving a white block in dark mode. */
QTreeWidget#foldertree {{
    background: {panel2};
    color: {text};
    border: 1px solid {border};
    border-radius: {{r_md}};
    outline: none;
    padding: 4px;
}}
QTreeWidget#foldertree::item {{
    border-radius: {{r_sm}};
    padding: 4px 2px;
    margin: 1px 0px;
    min-height: 22px;
}}
QTreeWidget#foldertree::item:hover {{ background: {bg}; color: {text}; }}
QTreeWidget#foldertree::item:selected {{ background: {accent_tint}; color: {accent}; }}
QTreeWidget#foldertree::branch:open {{ image: none; }}
QTreeWidget#foldertree::branch:closed {{ image: none; }}

/* Details (table) view — Windows-Explorer-like, tokenized. */
QTableWidget#detailstable {{
    background: {panel2};
    color: {text};
    border: 1px solid {border};
    border-radius: {{r_sm}};
    gridline-color: transparent;
    outline: none;
    font-size: 13px;
    alternate-background-color: {bg};
}}
QTableWidget#detailstable::item {{ padding: 5px 8px; border-bottom: 1px solid {border}; }}
QTableWidget#detailstable::item:hover {{ background: {bg}; color: {text}; }}
QTableWidget#detailstable::item:selected {{
    background: {accent_tint};
    color: {accent};
}}
/* Sort indicator on header */
QHeaderView::section {{
    background: {panel};
    color: {muted2};
    border: none;
    border-bottom: 1px solid {border};
    border-right: 1px solid {border};
    padding: 7px 10px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: .5px;
    font-size: 11px;
}}
QHeaderView::section:hover {{ background: {bg}; color: {text}; }}
QTableWidget#detailstable::corner {{ background: {panel}; border: none; }}
/* Sidebar splitter handle — tokenized (was inline). */
QSplitter#sidebarsplitter::handle {{
    background: {border};
    border-radius: 2px;
    margin: 4px 0;
}}
QSplitter#sidebarsplitter::handle:hover {{ background: {muted2}; }}
/* Main content splitter handle — tokenized (was inline via _splitter_style). */
QSplitter#mainsplitter::handle {{
    background: {border};
}}
/* Empty-section hints (Tags / Smart Folders). */
QLabel#navhint {{
    color: {muted2};
    font-size: 12px;
}}
/* Horizontal divider separating the Trash footer in the sidebar. */
QFrame#seph {{
    background: {border};
    min-height: 1px;
    max-height: 1px;
}}

/* ---------- asset cards (tokenized; was inline setStyleSheet locked to
   the build-time theme — that's why some card chrome stayed light after
   switching to dark). All colors come from the active token set, so they
   refresh with the QApplication QSS on theme switch. ---------- */
QLabel#cardtier {{
    background: rgba(10,20,30,.55); color: #ffffff;
    border-radius: {{r_sm}}; padding: 3px 8px;
    font-size: 11px; font-weight: 700;
}}
QPushButton#cardfav {{
    background: rgba(10,20,30,.45);
    border: none;
    border-radius: {{r_md}};
}}
QPushButton#cardcheck {{
    border-radius: {{r_md}};
    background: rgba(255,255,255,.9);
    border: 2px solid rgba(255,255,255,.9);
}}
QPushButton#cardcheck[selected="true"] {{
    background: {accent};
    border: 1px solid {accent};
}}
QLabel#cardtypechip {{
    border-radius: {{r_sm}}; padding: 2px 7px;
    font-size: 11px; font-weight: 600;
}}
QLabel#cardtypechip[type="Niagara"]   {{ background: rgba(14,165,233,.14);  color: #0ea5e9; }}
QLabel#cardtypechip[type="Cascade"]   {{ background: rgba(168,85,247,.14); color: #a855f7; }}
QLabel#cardtypechip[type="Blueprint"] {{ background: rgba(16,185,129,.14);  color: #10b981; }}
QLabel#cardtypechip[type="BP"]        {{ background: rgba(16,185,129,.14);  color: #10b981; }}
QLabel#cardtypechip[type="Texture"]   {{ background: rgba(245,158,11,.14); color: #f59e0b; }}
QLabel#cardtypechip[type="Material"]  {{ background: rgba(244,63,94,.14);  color: #f43f5e; }}
QLabel#cardbpchip {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 rgba(99,91,255,0.14), stop:1 rgba(0,163,255,0.08));
    color: {accent};
    border-radius: {{r_sm}}; padding: 2px 6px;
    font-size: 10px; font-weight: 700;
}}
QLabel#cardemptylabel {{
    color: {muted}; font-size: 14px;
    text-align: center; line-height: 1.6;
}}
QLabel#cardname {{
    color: {text}; font-weight: 600; font-size: 13px;
}}
QLabel#cardtag {{
    color: {muted}; font-size: 12px;
}}

/* ---------- batch bar (tokenized; was inline). Refreshes with the global
   QSS so a dark/light switch recolors the badge + buttons too. ---------- */
QLabel#batchcount {{
    font-weight: 700; color: {accent}; font-size: 13px;
    border-radius: {{r_sm}}; padding: 3px 9px;
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 rgba(99,91,255,0.12), stop:1 rgba(0,163,255,0.08));
}}
/* Inspector "Export to UE" + blueprint chip are tokenized (they were inline
   gradients/bg that went stale after a theme switch). Uses the same
   indigo→cyan dual-tone as #primary for brand consistency. */
QPushButton#inspexp {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 {accent}, stop:1 {accent2});
    color: #ffffff; border: none; border-radius: {{r_md}};
    padding: 7px; font-weight: 600; font-size: 12px;
}}
QPushButton#inspexp:hover {{ background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 {accent_hover}, stop:1 #00b8ff); color: #ffffff; }}
QPushButton#inspexp:pressed {{ background: {accent_pressed}; color: #ffffff; }}
QLabel#inspbpchip {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 rgba(99,91,255,0.14), stop:1 rgba(0,163,255,0.08));
    color: {accent};
    border-radius: 6px; padding: 2px 7px;
    font-size: 10px; font-weight: 700;
}}
/* Rating stars — token-driven so they follow the theme switch (previously had
   no rule at all and rendered as default purple buttons). */
QPushButton#star {{
    background: transparent; border: none; border-radius: {{r_sm}};
    color: {muted2}; font-size: 18px; padding: 0;
    min-width: 28px; min-height: 28px; max-width: 28px; max-height: 28px;
    qproperty-text-align: center;
}}
QPushButton#star:hover {{ color: {warn}; background: {bg}; }}
QPushButton#star:pressed {{ background: {border}; }}
QPushButton#star[on="true"] {{ color: {amber}; }}

QPushButton#batchbtnprimary {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 {accent}, stop:1 {accent2});
    color: #ffffff; border: none; border-radius: {{r_md}};
    padding: 0 14px; font-weight: 600; font-size: 12px;
}}
QPushButton#batchbtnprimary:hover {{ background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 {accent_hover}, stop:1 #00b8ff); color: #ffffff; }}
QPushButton#batchbtnprimary:pressed {{ background: {accent_pressed}; color: #ffffff; }}
QPushButton#batchbtndanger {{
    background: {bg2};     color: {bad}; border: 1px solid {border2};
    border-radius: {{r_md}}; padding: 0 14px; font-weight: 600; font-size: 12px;
}}
QPushButton#batchbtndanger:hover {{ background: rgba(232,93,93,.10); border-color: {bad}; }}
QPushButton#batchbtndanger:pressed {{ background: rgba(232,93,93,.18); }}
QPushButton#batchbtn {{
    background: {bg2}; color: {text}; border: 1px solid {border2};
    border-radius: {{r_md}}; padding: 0 14px; font-weight: 600; font-size: 12px;
}}
QPushButton#batchbtn:hover {{ background: {panel2}; border-color: {accent}; }}
QPushButton#batchbtn:pressed {{ background: {card_sel}; }}

QFrame#header {{
    background: {bg};
    border-bottom: 1px solid {border};
}}
QFrame#header #brand {{ color: {text}; font-weight: 700; font-size: 14px; }}

QFrame#toolbar {{
    background: {bg2};
    border-bottom: 1px solid {border};
}}
QFrame#segctl {{
    background: {panel2};
    border: 1px solid {border};
    border-radius: {{r_md}};
    padding: 2px;
}}
QPushButton#seg {{
    background: transparent;
    color: {text};
    border: none;
    border-radius: {{r_md}};
    padding: 0 12px;
    font-size: 12px;
    font-weight: 600;
}}
QPushButton#seg:hover {{ background: {bg}; color: {text}; }}
QPushButton#seg:checked {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 rgba(99,91,255,0.12), stop:1 rgba(99,91,255,0.06));
    color: {accent};
    border: 1px solid {accent};
}}
QPushButton#seg:checked:hover {{ background: {accent_tint}; }}
QPushButton#seg:pressed {{ background: {border}; }}
QFrame#projpill {{
    background: {panel2};
    border: 1px solid {border};
    border-radius: {{r_pill}};
}}
QFrame#sep {{
    background: {border};
    max-width: 1px;
    min-width: 1px;
}}
/* Sidebar brand/stat hero card — soft translucent indigo→cyan glow
   (the "Stripe 柔光概念" signature element). Uses semi-transparent stops
   so the underlying panel texture bleeds through, giving a luminous
   depth that solid gradients can't achieve. */
QFrame#sidehero {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 rgba(99,91,255,0.35), stop:1 rgba(0,163,255,0.20));
    border-radius: {{r_lg}};
    border: 1px solid rgba(99,91,255,0.25);
}}
QLabel#heromono {{
    color: #ffffff;
    background: rgba(255,255,255,0.18);
    border-radius: {{r_sm}};
    font-size: 14px;
    font-weight: 800;
    padding: 2px 8px;
}}
QLabel#herolib {{
    color: rgba(255,255,255,0.92);
    font-size: 12px;
    font-weight: 600;
}}
QLabel#herostat {{
    color: #ffffff;
    font-size: 28px;
    font-weight: 800;
}}
QLabel#herosuB {{
    color: rgba(255,255,255,0.82);
    font-size: 12px;
}}
QLabel#herometa {{
    color: rgba(255,255,255,0.72);
    font-size: 11px;
}}
"""


def resolve_theme(theme="auto"):
    if theme in ("light", "dark"):
        return theme
    try:
        app = QApplication.instance()
        if app is not None and app.styleHints().colorScheme() == Qt.ColorScheme.Dark:
            return "dark"
    except Exception:
        pass
    return "light"


def get_stylesheet(theme="light"):
    p = THEMES.get(theme, THEMES["light"])
    return _TEMPLATE.format(**p)
