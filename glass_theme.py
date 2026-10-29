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
QWidget { color:#202227; font-family:'Segoe UI Variable','Segoe UI'; font-size:13px; }
QMainWindow, #root { background:#F5F6F8; }
#glassCard { background:#FFFFFF; border:1px solid #E2E5E9; border-radius:12px; }
#cardTitle { font-size:15px; font-weight:600; }
#dim { color:#565B64; }
QPushButton { background:#F1F2F4; border:1px solid #E2E5E9; color:#202227;
    border-radius:9px; padding:8px 16px; }
QPushButton:hover { background:#E9EDF5; }
QPushButton:checked { background:#335FFF; border:1px solid #335FFF; color:white; }
QLineEdit { background:#F0F1F3; border:1px solid #E2E5E9; color:#202227;
    border-radius:9px; padding:10px 14px; selection-background-color:#335FFF; }
QLineEdit:focus { background:#FFFFFF; border:1px solid #335FFF; }
QScrollBar:vertical { background:transparent; width:8px; }
QScrollBar::handle:vertical { background:#CFD3D9; border-radius:4px; min-height:30px; }
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
        self.setStyleSheet("background:rgba(255,255,255,0.14);border:1px solid rgba(255,255,255,0.22);border-radius:12px;")
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
