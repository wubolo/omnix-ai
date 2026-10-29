"""Современная «стеклянная» тема для PyQt6 + плавные переходы.

    from glass_theme import GLASS_QSS, SmoothStackedWidget, SlidingIndicator
    app.setStyleSheet(GLASS_QSS)
Для размытия фона Windows 11 (Acrylic): pip install PyQt6-Frameless-Window или
вызов DwmSetWindowAttribute(DWMWA_SYSTEMBACKDROP_TYPE=38, 3) — см. enable_backdrop().
"""
import ctypes
import sys

from PyQt6.QtCore import QEasingCurve, QParallelAnimationGroup, QPropertyAnimation, QPoint
from PyQt6.QtWidgets import QGraphicsOpacityEffect, QStackedWidget, QWidget

GLASS_QSS = """
QWidget { color:#F2F4F8; font-family:'SF Pro Text','SFProText','Segoe UI Variable','Segoe UI'; font-size:13px; }
QMainWindow, #root { background:#0E1016; }
#glassCard { background:qlineargradient(x1:0,y1:0,x2:1,y2:1,
    stop:0 rgba(255,255,255,0.09), stop:1 rgba(255,255,255,0.03));
    border:1px solid rgba(255,255,255,0.14); border-radius:18px; }
#cardTitle { font-size:15px; font-weight:600; }
#dim { color:rgba(255,255,255,0.55); }
QPushButton { background:rgba(255,255,255,0.07); border:1px solid rgba(255,255,255,0.12);
    border-radius:12px; padding:8px 16px; }
QPushButton:hover { background:rgba(255,255,255,0.13); }
QPushButton:checked { background:rgba(99,102,241,0.55); border:1px solid rgba(139,142,255,0.9); color:white; }
QLineEdit { background:rgba(255,255,255,0.06); border:1px solid rgba(255,255,255,0.12);
    border-radius:12px; padding:10px 14px; selection-background-color:#6366F1; }
QLineEdit:focus { background:rgba(255,255,255,0.10); border:1px solid rgba(99,102,241,0.8); }
QScrollBar:vertical { background:transparent; width:8px; }
QScrollBar::handle:vertical { background:rgba(255,255,255,0.2); border-radius:4px; min-height:30px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height:0; }
"""


class SmoothStackedWidget(QStackedWidget):
    """Переключение страниц с плавным появлением."""
    duration = 260

    def setCurrentIndex(self, index):
        nxt, cur = self.widget(index), self.currentWidget()
        if index == self.currentIndex() or cur is None or nxt is None:
            return super().setCurrentIndex(index)
        super().setCurrentIndex(index)
        eff = QGraphicsOpacityEffect(nxt)
        nxt.setGraphicsEffect(eff)
        a = QPropertyAnimation(eff, b"opacity", self)
        a.setDuration(self.duration)
        a.setStartValue(0.0); a.setEndValue(1.0)
        a.setEasingCurve(QEasingCurve.Type.OutCubic)
        a.finished.connect(lambda: nxt.setGraphicsEffect(None))
        self._anim = a
        a.start()


class SlidingIndicator(QWidget):
    """Подсветка активной вкладки, плавно переезжающая к кнопке."""
    def __init__(self, parent):
        super().__init__(parent)
        from PyQt6.QtCore import Qt
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setStyleSheet("background:rgba(167,139,250,0.18);border:1px solid rgba(196,181,253,0.30);border-radius:12px;")
        self._pos = QPropertyAnimation(self, b"pos", self)
        self._pos.setDuration(240)
        self._pos.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.lower()

    def move_to(self, button):
        self.resize(button.size())
        self._pos.stop()
        self._pos.setStartValue(self.pos())
        self._pos.setEndValue(QPoint(button.x(), button.y()))
        self._pos.start()


def enable_backdrop(widget):
    """Win11: Mica/Acrylic за окном. На других ОС тихо ничего не делает."""
    if sys.platform != "win32":
        return
    try:
        hwnd = int(widget.winId())
        val = ctypes.c_int(3)  # 3 = Acrylic, 2 = Mica
        ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 38, ctypes.byref(val), 4)
        dark = ctypes.c_int(1)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(dark), 4)
    except Exception:
        pass
