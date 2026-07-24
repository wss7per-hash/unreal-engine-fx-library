# app/ui/tag_manager_dialog.py -- list / rename / delete tags library-wide.

from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                               QPushButton, QListWidget, QListWidgetItem,
                               QInputDialog, QMessageBox, QWidget, QSizePolicy)
from PySide6.QtCore import Qt

from app.i18n import tr
from app.style import THEMES


class TagManagerDialog(QDialog):
    def __init__(self, db, theme, parent=None):
        super().__init__(parent)
        self.db = db
        self.theme = theme
        self.setWindowTitle(tr("tag_manager_title"))
        self.setMinimumWidth(440)
        tok = THEMES.get(theme, THEMES["light"])

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)

        hint = QLabel(tr("manage_tags_hint"))
        hint.setWordWrap(True)
        hint.setStyleSheet("color:%s; font-size:12px;" % tok["muted"])
        layout.addWidget(hint)

        self.list_widget = QListWidget()
        self.list_widget.setStyleSheet(
            "QListWidget { background: %s; border: 1px solid %s; border-radius: 10px; padding: 4px; }"
            "QListWidget::item { padding: 2px; }" % (tok["bg2"], tok["border"]))
        layout.addWidget(self.list_widget, 1)

        close_btn = QPushButton(tr("ok"))
        close_btn.setObjectName("primary")
        close_btn.setFixedHeight(32)
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn, 0, Qt.AlignRight)

        self._refresh()

    def _refresh(self):
        self.list_widget.clear()
        tok = THEMES.get(self.theme, THEMES["light"])
        tags = self.db.all_tags_with_counts()
        if not tags:
            item = QListWidgetItem("（暂无标签）")
            item.setFlags(item.flags() & ~Qt.ItemIsEnabled)
            item.setForeground(tok["muted2"])
            self.list_widget.addItem(item)
            return
        for tag, count in tags:
            widget = QWidget()
            row = QHBoxLayout(widget)
            row.setContentsMargins(8, 4, 8, 4)
            row.setSpacing(8)

            name = QLabel(tag)
            name.setStyleSheet("font-weight:600; color:%s; font-size:13px;" % tok["text"])
            count_lbl = QLabel("%d %s" % (count, tr("tag_count_suffix")))
            count_lbl.setStyleSheet("color:%s; font-size:11px;" % tok["muted2"])

            rename_btn = QPushButton(tr("rename_tag"))
            rename_btn.setObjectName("secondary")
            rename_btn.setFixedHeight(28)
            rename_btn.setCursor(Qt.PointingHandCursor)
            rename_btn.clicked.connect(lambda _c, t=tag: self._rename(t))

            del_btn = QPushButton(tr("delete_tag"))
            del_btn.setObjectName("danger")
            del_btn.setFixedHeight(28)
            del_btn.setCursor(Qt.PointingHandCursor)
            del_btn.clicked.connect(lambda _c, t=tag, c=count: self._delete(t, c))

            row.addWidget(name)
            row.addWidget(count_lbl)
            row.addStretch(1)
            row.addWidget(rename_btn)
            row.addWidget(del_btn)

            item = QListWidgetItem()
            item.setSizeHint(widget.sizeHint())
            self.list_widget.addItem(item)
            self.list_widget.setItemWidget(item, widget)

    def _rename(self, tag):
        name, ok = QInputDialog.getText(self, tr("rename_tag_title"),
                                        tr("rename_tag_ph"), text=tag)
        if ok and name.strip() and name.strip() != tag:
            self.db.rename_tag(tag, name.strip())
            self._refresh()
            if self.parent():
                self.parent()._refresh_tag_browser()
                self.parent()._apply_filters()

    def _delete(self, tag, count):
        rep = QMessageBox.question(
            self, tr("tag_manager_title"),
            tr("delete_tag_confirm", tag=tag, n=count),
            QMessageBox.Yes | QMessageBox.No)
        if rep == QMessageBox.Yes:
            self.db.delete_tag(tag)
            self._refresh()
            if self.parent():
                self.parent()._refresh_tag_browser()
                self.parent()._apply_filters()
