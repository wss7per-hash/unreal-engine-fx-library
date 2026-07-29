# app/ui/base_dialog.py -- shared base class for every in-app dialog.
#
# WHY THIS EXISTS
# ---------------
# On Windows + PySide6, modal dialogs opened via exec() sometimes fail to
# inherit the QApplication-wide stylesheet: child controls silently fall
# back to the native platform style. The user saw a stock white Win32
# combo box inside the Settings dialog while the main window was fully
# themed. Re-applying the application stylesheet directly on the dialog
# forces the cascade locally, and is harmless when inheritance already
# works (same rules, same specificity).
#
# All dialogs should inherit BaseDialog instead of QDialog and use
# self.tok() for any color that must follow the active theme — never
# hardcode hex values (that froze the About dialog in a half-dark palette).

from PySide6.QtWidgets import QDialog, QApplication

from app.style import THEMES


class BaseDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        app = QApplication.instance()
        if app is not None and app.styleSheet():
            self.setStyleSheet(app.styleSheet())

    def tok(self):
        """Active theme token set — the app is dark-only."""
        return THEMES["dark"]
