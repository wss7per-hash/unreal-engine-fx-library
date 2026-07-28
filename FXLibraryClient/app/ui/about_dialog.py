# -*- coding: utf-8 -*-
# app/ui/about_dialog.py -- "About" dialog: version / build date / tech stack.
# The version string comes exclusively from app.version (single source).
# All colors come from the active theme token set (self.tok()) — the old
# hardcoded grey/slate hex values froze the dialog in a half-dark palette and
# the bare QLabels painted the global QWidget {bg} behind every detail row
# ("一行行黑色的黑框").

import os
import sys
import datetime

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QVBoxLayout, QHBoxLayout, QLabel,
                               QPushButton, QFrame)

from app.version import __version__, __build_date__
from app.i18n import tr
from app.icons import logo_pixmap
from app.ui.base_dialog import BaseDialog


def _build_date_text():
    """Baked-in build date, falling back to the executable/script mtime."""
    if __build_date__:
        return __build_date__
    try:
        if getattr(sys, "frozen", False):
            path = sys.executable
        else:
            path = os.path.abspath(__file__)
        ts = os.path.getmtime(path)
        return datetime.date.fromtimestamp(ts).isoformat()
    except OSError:
        return "-"


class AboutDialog(BaseDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        tok = self.tok()
        self.setWindowTitle(tr("about_title"))
        self.setModal(True)
        self.setFixedWidth(380)

        root = QVBoxLayout(self)
        root.setContentsMargins(28, 28, 28, 20)
        root.setSpacing(10)

        # Logo
        logo = QLabel()
        logo.setPixmap(logo_pixmap(size=72))
        logo.setAlignment(Qt.AlignCenter)
        root.addWidget(logo)

        # Product name + version
        name = QLabel("FX Library")
        f = name.font()
        f.setPointSize(15)
        f.setBold(True)
        name.setFont(f)
        name.setAlignment(Qt.AlignCenter)
        name.setStyleSheet("background: transparent; color: %s;" % tok["text"])
        root.addWidget(name)

        ver = QLabel("v%s" % __version__)
        ver.setAlignment(Qt.AlignCenter)
        ver.setStyleSheet("background: transparent; color: %s;" % tok["muted2"])
        root.addWidget(ver)

        desc = QLabel(tr("about_desc"))
        desc.setAlignment(Qt.AlignCenter)
        desc.setStyleSheet("background: transparent; color: %s;" % tok["muted"])
        root.addWidget(desc)

        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFixedHeight(1)
        line.setStyleSheet("background: %s; border: none;" % tok["border"])
        root.addWidget(line)

        # Detail rows
        for key, value in (
            (tr("about_version"), __version__),
            (tr("about_build_date"), _build_date_text()),
            (tr("about_stack"), "PySide6 · SQLite · PyInstaller"),
        ):
            row = QHBoxLayout()
            k = QLabel(key)
            k.setStyleSheet("background: transparent; color: %s;" % tok["muted2"])
            v = QLabel(value)
            v.setStyleSheet("background: transparent; color: %s; font-weight: 600;"
                            % tok["text"])
            v.setTextInteractionFlags(Qt.TextSelectableByMouse)
            row.addWidget(k)
            row.addStretch(1)
            row.addWidget(v)
            root.addLayout(row)

        root.addSpacing(6)

        btn = QPushButton(tr("ok"))
        btn.setObjectName("primary")
        btn.setDefault(True)
        btn.setMinimumWidth(96)
        btn.clicked.connect(self.accept)
        brow = QHBoxLayout()
        brow.addStretch(1)
        brow.addWidget(btn)
        root.addLayout(brow)
