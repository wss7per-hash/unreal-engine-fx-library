# app/ui/settings_dialog.py -- configure language, theme and FX-only import.

from PySide6.QtWidgets import (QFormLayout,
                               QVBoxLayout, QHBoxLayout,
                               QDialogButtonBox, QComboBox, QCheckBox,
                               QLabel)
from PySide6.QtCore import Qt

from app import config as cfg
from app.i18n import tr
from app.version import __version__
from app.ui.base_dialog import BaseDialog


class SettingsDialog(BaseDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("settings_title"))
        self.cfg = cfg.load()
        self.setMinimumWidth(440)

        self.lang_combo = QComboBox()
        self.lang_combo.addItem(tr("choose_language"), "auto")
        self.lang_combo.addItem("中文", "zh")
        self.lang_combo.addItem("English", "en")
        current = self.cfg.get("language", "auto")
        idx = self.lang_combo.findData(current)
        if idx >= 0:
            self.lang_combo.setCurrentIndex(idx)

        self.theme_combo = QComboBox()
        self.theme_combo.addItem(tr("theme_auto"), "auto")
        self.theme_combo.addItem(tr("theme_light"), "light")
        self.theme_combo.addItem(tr("theme_dark"), "dark")
        current_t = self.cfg.get("theme", "auto")
        idx_t = self.theme_combo.findData(current_t)
        if idx_t >= 0:
            self.theme_combo.setCurrentIndex(idx_t)

        self.fx_only_chk = QCheckBox(tr("import_fx_only"))
        self.fx_only_chk.setChecked(bool(self.cfg.get("import_fx_only", True)))

        self.skip_import_chk = QCheckBox(tr("skip_import_dialog"))
        self.skip_import_chk.setChecked(bool(self.cfg.get("skip_import_dialog", False)))

        form = QFormLayout()
        form.setSpacing(14)
        form.setLabelAlignment(Qt.AlignRight)
        form.addRow(tr("import_fx_only"), self.fx_only_chk)
        form.addRow("", self.skip_import_chk)
        form.addRow(tr("theme"), self.theme_combo)
        form.addRow(tr("language"), self.lang_combo)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        # Give the box buttons the app's design-system identities — without an
        # objectName they get the generic solid-purple QPushButton rule and
        # clash with everything else in the dialog.
        ok_btn = buttons.button(QDialogButtonBox.Ok)
        if ok_btn is not None:
            ok_btn.setObjectName("primary")
            ok_btn.setMinimumWidth(88)
        cancel_btn = buttons.button(QDialogButtonBox.Cancel)
        if cancel_btn is not None:
            cancel_btn.setObjectName("secondary")
            cancel_btn.setMinimumWidth(88)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.addLayout(form)
        layout.addStretch(1)
        ver_lbl = QLabel("FX Library v%s" % __version__)
        ver_lbl.setStyleSheet("background: transparent; color: %s;"
                              % self.tok()["muted2"])
        ver_lbl.setAlignment(Qt.AlignLeft)
        bottom = QHBoxLayout()
        bottom.addWidget(ver_lbl)
        bottom.addStretch(1)
        bottom.addWidget(buttons)
        layout.addLayout(bottom)

    def accept(self):
        self.cfg["import_fx_only"] = self.fx_only_chk.isChecked()
        self.cfg["skip_import_dialog"] = self.skip_import_chk.isChecked()
        self.cfg["language"] = self.lang_combo.currentData() or "auto"
        self.cfg["theme"] = self.theme_combo.currentData() or "auto"
        cfg.save(self.cfg)
        super().accept()
