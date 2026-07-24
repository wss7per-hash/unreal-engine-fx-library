import os, sys
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QPushButton,
                             QScrollArea, QSizePolicy)
app = QApplication.instance() or QApplication(sys.argv)
app.setStyle("Fusion")

# Minimal: plain VBox + fixed-height buttons, no scroll
w = QWidget(); w.resize(300,600)
lay = QVBoxLayout(w); lay.setSpacing(4); lay.setContentsMargins(0,0,0,0)
for i in range(5):
    b = QPushButton("B%d"%i)
    b.setFixedHeight(26)
    lay.addWidget(b)
w.show(); app.processEvents()
print("=== MINIMAL plain VBox, setFixedHeight(26) ===")
for i,b in enumerate(w.findChildren(QPushButton)):
    print("  B%d y=%d h=%d" % (i, b.geometry().y(), b.geometry().height()))

# Now inside a scroll area with widgetResizable(True), like the app
scroll = QScrollArea(); scroll.resize(300,200); scroll.setWidgetResizable(True)
inner = QWidget(); inner.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)
lay2 = QVBoxLayout(inner); lay2.setSpacing(4); lay2.setContentsMargins(0,0,0,0)
for i in range(5):
    b = QPushButton("S%d"%i)
    b.setFixedHeight(26)
    lay2.addWidget(b)
scroll.setWidget(inner)
scroll.show(); app.processEvents()
print("=== SCROLL widgetResizable(True), inner Minimum policy ===")
for i,b in enumerate(inner.findChildren(QPushButton)):
    print("  S%d y=%d h=%d" % (i, b.geometry().y(), b.geometry().height()))
print("  inner height:", inner.height(), "viewport height:", scroll.viewport().height())
