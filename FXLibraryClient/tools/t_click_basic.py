# tools/t_click_basic.py -- minimum repro: does sendEvent on a button inside a
# QScrollArea reach it, in offscreen mode?
import os, sys
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import (QApplication, QWidget, QPushButton, QScrollArea,
                                QHBoxLayout, QLabel)
from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
from PySide6.QtGui import QMouseEvent
app = QApplication.instance() or QApplication(sys.argv)
print("=== Case 1: plain window with button ===")
win = QPushButton("btn")
win.resize(200, 60); win.show()
app.processEvents()
fired = []
win.clicked.connect(lambda: fired.append(1))
gp = win.mapToGlobal(QPoint(100, 30))
print("btn global pos:", gp, "size:", win.size())
hit = QApplication.widgetAt(gp)
print("widgetAt:", type(hit).__name__ if hit else None, "isbtn:", hit is win)
# Try a real mouse press+release via sendEvent at the button's local centre
local = QPointF(win.width() // 2, win.height() // 2)
press = QMouseEvent(QEvent.MouseButtonPress, local, QPointF(gp),
                     Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
release = QMouseEvent(QEvent.MouseButtonRelease, local, QPointF(gp),
                       Qt.NoButton, Qt.LeftButton, Qt.NoModifier)
QApplication.sendEvent(win, press); app.processEvents()
QApplication.sendEvent(win, release); app.processEvents()
print("clicked fired:", len(fired) > 0)

print("\n=== Case 2: button INSIDE a QScrollArea ===")
sa = QScrollArea(); sa.resize(200, 100); sa.show()
sa_pos = sa.mapToGlobal(QPoint(0, 0))
print("scrollarea global:", sa_pos, "size:", sa.size())
inner = QWidget(); inner.setMinimumSize(200, 80)
sa.setWidget(inner); sa.setWidgetResizable(True)
vb = QHBoxLayout(inner)
btn = QPushButton("inside"); btn.setMinimumSize(180, 30)
fired2 = []
btn.clicked.connect(lambda: fired2.append(1))
vb.addWidget(btn)
sa.show(); app.processEvents()
btn_glob = btn.mapToGlobal(QPoint(90, 15))
print("btn global:", btn_glob)
hit2 = QApplication.widgetAt(btn_glob)
print("widgetAt:", type(hit2).__name__ if hit2 else None)
local2 = QPointF(90, 15)
press2 = QMouseEvent(QEvent.MouseButtonPress, local2, QPointF(btn_glob),
                      Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
release2 = QMouseEvent(QEvent.MouseButtonRelease, local2, QPointF(btn_glob),
                        Qt.NoButton, Qt.LeftButton, Qt.NoModifier)
QApplication.sendEvent(btn, press2); app.processEvents()
QApplication.sendEvent(btn, release2); app.processEvents()
print("clicked fired (sendEvent to btn):", len(fired2) > 0)
# Also try sending to the scroll viewport
fired2b = []
btn.clicked.disconnect()
btn.clicked.connect(lambda: fired2b.append(1))
vp = sa.viewport()
vp_local = QPointF(vp.mapFromGlobal(btn_glob))
press3 = QMouseEvent(QEvent.MouseButtonPress, vp_local, QPointF(btn_glob),
                      Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
release3 = QMouseEvent(QEvent.MouseButtonRelease, vp_local, QPointF(btn_glob),
                        Qt.NoButton, Qt.LeftButton, Qt.NoModifier)
QApplication.sendEvent(vp, press3); app.processEvents()
QApplication.sendEvent(vp, release3); app.processEvents()
print("clicked fired (sendEvent to viewport):", len(fired2b) > 0)

print("\n=== Case 3: ensure full mouse chain via QTest.mouseClick (sanity) ===")
fired3 = []
btn.clicked.disconnect()
btn.clicked.connect(lambda: fired3.append(1))
from PySide6.QtTest import QTest
QTest.mouseClick(btn, Qt.LeftButton); app.processEvents()
print("clicked fired (QTest.mouseClick):", len(fired3) > 0)
