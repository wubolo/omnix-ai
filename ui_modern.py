"""
ui_modern.py — the OMNIX AI glass interface.

The app uses a liquid-glass surface, top title/mic controls, and bottom section
navigation. All existing assistant features remain connected to the same shell.

HOW IT FITS
    ModernWindow subclasses the existing MainWindow, so everything that already
    works keeps working: signals, the confirmation banner, the API-key setup,
    the audio-device / memory / plugin / customise overlays, wake word, PTT.
    The old central widget is kept hidden for backend compatibility; it has no
    menu route, button or hotkey in the user-facing interface.

All drawing is original (own logo, own icons). Nothing is imported from any
other application.
"""
from __future__ import annotations

import json
import math
import os
import platform
import sys
import threading
import time
import traceback
from collections import deque
from pathlib import Path

from PyQt6.QtCore import (Qt, QTimer, QRectF, QPointF, QPropertyAnimation,
                          QEasingCurve, QUrl, pyqtProperty, pyqtSignal)
from PyQt6.QtGui import (QPainter, QColor, QPen, QFont,
                         QPainterPath, QDesktopServices, QFontDatabase)
from PyQt6.QtWidgets import (QWidget, QFrame, QLabel, QPushButton, QVBoxLayout,
                             QHBoxLayout, QScrollArea, QStackedWidget, QSlider,
                             QLineEdit, QAbstractButton, QTextBrowser, QGridLayout,
                             QFileDialog, QMessageBox, QSizePolicy)

import ui as _legacy
from ui import MainWindow
from memory.config_manager import (AVAILABLE_VOICES, get_ui_setting, get_voice,
                                   save_plugin_enabled, save_ui_setting, save_voice)

APP_TITLE = "OMNIX AI"
APP_BUILD = "6.5"


# ── palette ────────────────────────────────────────────────────────────────────
class P:
    BG_A      = "#f5f6f8"
    BG_B      = "#ffffff"
    SIDEBAR   = "#ffffff"
    NAV_ON    = "#edf0f5"
    CARD      = "#ffffff"
    CARD_LINE = "#e2e5e9"
    TEXT      = "#202227"
    DIM       = "#565b64"
    FAINT     = "#858b95"
    ACCENT    = "#335fff"
    ACCENT_HI = "#335fff"
    RED       = "#fb7185"
    GREEN     = "#6ee7c0"


# ── make every old overlay match ───────────────────────────────────────────────
# The classic panels (devices, memory, customise, remote access, plugin settings,
# the confirmation banner …) read their colours from ui.C and their fonts from
# QFont(...) when they are BUILT. Patching both here, before any of them exists,
# gives them the new palette and a clean sans-serif font without rewriting each.
_MODERN_C = {
    "BG": "#f5f6f8", "PANEL": "#ffffff", "PANEL2": "#f4f5f7",
    "BORDER": "#e2e5e9", "BORDER_B": "#d2d6dc", "BORDER_A": "#dce0e6",
    "PRI": "#335fff", "PRI_DIM": "#2449d8", "PRI_GHO": "#edf0f5",
    "ACC": "#6ee7c0", "ACC2": "#8cf0d0", "GREEN": "#6ee7c0", "GREEN_D": "#31ba94",
    "RED": "#fb7185", "MUTED_C": "#fb7185",
    "TEXT": "#f7f4fb", "TEXT_DIM": "#827b8c", "TEXT_MED": "#b1aaba",
    "WHITE": "#ffffff", "DARK": "#0b0e14", "BAR_BG": "#1b212c",
}
_MONO = ("courier new", "consolas", "courier", "monospace", "lucida console")
_FONT_DIR = Path(__file__).resolve().parent / "assets" / "fonts"
_SF_FONT_ID = QFontDatabase.addApplicationFont(str(_FONT_DIR / "SFProText-Medium.ttf")) if (_FONT_DIR / "SFProText-Medium.ttf").is_file() else -1
_SF_BOLD_FONT_ID = QFontDatabase.addApplicationFont(str(_FONT_DIR / "SFProText-Bold.ttf")) if (_FONT_DIR / "SFProText-Bold.ttf").is_file() else -1
_INTER_FONT_ID = QFontDatabase.addApplicationFont(str(_FONT_DIR / "Inter.ttf")) if (_FONT_DIR / "Inter.ttf").is_file() else -1
_SF_FAMILIES = QFontDatabase.applicationFontFamilies(_SF_FONT_ID) if _SF_FONT_ID >= 0 else []
_UI_FONT = (_SF_FAMILIES[0] if _SF_FAMILIES else
            ("Inter" if _INTER_FONT_ID >= 0 else "Segoe UI"))


class _ModernFont(QFont):
    """Old panels ask for Courier New; give them Segoe UI, one point larger."""

    def __init__(self, *a):
        if a and isinstance(a[0], str) and a[0].lower() in _MONO:
            a = list(a)
            a[0] = _UI_FONT
            if len(a) > 1 and isinstance(a[1], int) and 0 < a[1] <= 10:
                a[1] += 1
            a = tuple(a)
        super().__init__(*a)


def _apply_modern_look() -> None:
    try:
        for k, v in _MODERN_C.items():
            setattr(_legacy.C, k, v)
        hue_keys = getattr(_legacy, "_HUE_LINKED", ())
        if hasattr(_legacy, "_PALETTE_DEFAULTS"):
            for k in hue_keys:
                if k in _MODERN_C:
                    _legacy._PALETTE_DEFAULTS[k] = _MODERN_C[k]
        _legacy.DEFAULT_UI_COLOR = _MODERN_C["PRI"]
        _legacy.QFont = _ModernFont
    except Exception:
        traceback.print_exc()


_apply_modern_look()


def _mix(a: str, b: str, t: float) -> QColor:
    ca, cb = QColor(a), QColor(b)
    t = max(0.0, min(1.0, t))
    return QColor(int(ca.red() + (cb.red() - ca.red()) * t),
                  int(ca.green() + (cb.green() - ca.green()) * t),
                  int(ca.blue() + (cb.blue() - ca.blue()) * t))


def ring_colors(accent: str) -> list[str]:
    """The five circle colours, from the darkest outer ring to the brightest core."""
    return [_mix("#121826", accent, t).name() for t in (0.20, 0.38, 0.62, 0.86, 1.0)]


def set_accent(color: str) -> None:
    """Change the theme colour. Takes effect for everything built afterwards
    (the window rebuilds itself) and for the classic panels."""
    import re
    if not re.fullmatch(r"#[0-9a-fA-F]{6}", color or ""):
        return
    P.ACCENT = color.lower()
    P.ACCENT_HI = _mix(color, "#ffffff", 0.28).name()
    try:
        _legacy.C.PRI = P.ACCENT
        _legacy.C.PRI_DIM = _mix(color, "#0e1118", 0.45).name()
        _legacy.C.PRI_GHO = _mix(color, "#0e1118", 0.85).name()
    except Exception:
        pass


def _font(px: int, bold: bool = False) -> QFont:
    f = QFont(_UI_FONT)
    f.setPixelSize(px)
    f.setWeight(QFont.Weight.DemiBold if bold else QFont.Weight.Normal)
    return f


set_accent(str(get_ui_setting("ui_accent", "#3b82f6") or "#3b82f6"))


# ── icons (drawn, so there are no image files and they take the text colour) ──
def paint_icon(p: QPainter, kind: str, x: float, y: float, size: float,
               color: QColor, width: float = 1.7, bg: str = P.SIDEBAR) -> None:
    p.save()
    p.translate(x, y)
    s = size / 18.0
    p.scale(s, s)
    pen = QPen(color, width)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)

    if kind == "home":
        roof = QPainterPath()
        roof.moveTo(2.5, 8.5); roof.lineTo(9, 3); roof.lineTo(15.5, 8.5)
        p.drawPath(roof)
        body = QPainterPath()
        body.moveTo(4.5, 7.5); body.lineTo(4.5, 15); body.lineTo(13.5, 15); body.lineTo(13.5, 7.5)
        p.drawPath(body)
    elif kind == "list":
        for yy in (4.5, 9, 13.5):
            p.drawLine(QPointF(7.5, yy), QPointF(15.5, yy))
            p.drawLine(QPointF(2.5, yy), QPointF(4.5, yy))
    elif kind == "history":
        p.drawArc(QRectF(3, 3, 12, 12), 35 * 16, 300 * 16)
        p.drawLine(QPointF(2.5, 3), QPointF(2.5, 7))
        p.drawLine(QPointF(2.5, 7), QPointF(6.5, 7))
        p.drawLine(QPointF(9, 6), QPointF(9, 9))
        p.drawLine(QPointF(9, 9), QPointF(12, 11))
    elif kind == "grid":
        for gx, gy in ((2.5, 2.5), (10, 2.5), (2.5, 10), (10, 10)):
            p.drawRoundedRect(QRectF(gx, gy, 5.5, 5.5), 1.3, 1.3)
    elif kind == "ai":
        p.drawRoundedRect(QRectF(2.5, 6.5, 13, 8.5), 2.6, 2.6)
        p.setBrush(color)
        p.drawEllipse(QPointF(6.6, 10.7), 1.0, 1.0)
        p.drawEllipse(QPointF(11.4, 10.7), 1.0, 1.0)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawLine(QPointF(9, 6.5), QPointF(9, 4))
        p.drawEllipse(QPointF(9, 3.2), 0.9, 0.9)
    elif kind == "sliders":
        p.drawLine(QPointF(2.5, 5), QPointF(15.5, 5))
        p.drawLine(QPointF(2.5, 13), QPointF(15.5, 13))
        p.setBrush(QColor(bg))
        p.drawEllipse(QPointF(6.5, 5), 2.1, 2.1)
        p.drawEllipse(QPointF(11.5, 13), 2.1, 2.1)
    elif kind == "collapse":
        p.drawRoundedRect(QRectF(2.5, 2.5, 13, 13), 2.4, 2.4)
        p.drawLine(QPointF(7, 6), QPointF(7, 12))
        chev = QPainterPath()
        chev.moveTo(11.6, 6.6); chev.lineTo(9.4, 9); chev.lineTo(11.6, 11.4)
        p.drawPath(chev)
    elif kind == "info":
        p.drawEllipse(QPointF(9, 9), 6.6, 6.6)
        p.drawLine(QPointF(9, 8.2), QPointF(9, 12.6))
        p.drawPoint(QPointF(9, 5.7))
    elif kind == "help":
        p.drawArc(QRectF(4, 2.5, 10, 10), 25 * 16, 250 * 16)
        p.drawLine(QPointF(9, 12.5), QPointF(9, 14.2))
        p.drawPoint(QPointF(9, 16.2))
    elif kind == "account":
        p.drawEllipse(QPointF(9, 6), 3.2, 3.2)
        p.drawArc(QRectF(3, 9, 12, 9), 0, 180 * 16)
    elif kind in ("mic", "mic_off"):
        p.drawRoundedRect(QRectF(6.4, 1.8, 5.2, 8.8), 2.6, 2.6)
        p.drawArc(QRectF(3.8, 5.6, 10.4, 8.2), 180 * 16, 180 * 16)
        p.drawLine(QPointF(9, 13.8), QPointF(9, 16.2))
        p.drawLine(QPointF(6.4, 16.2), QPointF(11.6, 16.2))
        if kind == "mic_off":
            slash = QPen(QColor(P.RED), width + 0.2)
            slash.setCapStyle(Qt.PenCapStyle.RoundCap)
            p.setPen(slash)
            p.drawLine(QPointF(3, 2.6), QPointF(15, 15.4))
    p.restore()


# ── small widgets ──────────────────────────────────────────────────────────────
class Logo(QWidget):
    """Own mark: a blue disc with a speech bubble and 'AI' — not borrowed from anywhere."""

    activated = pyqtSignal()

    def __init__(self, size: int = 46):
        super().__init__()
        self.setFixedSize(size, size)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("Главная панель")

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.activated.emit()
        super().mousePressEvent(event)

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(P.ACCENT))
        p.drawEllipse(QRectF(1, 1, w - 2, h - 2))
        bubble = QPainterPath()
        bubble.addRoundedRect(QRectF(w * 0.24, h * 0.27, w * 0.52, h * 0.38), 7, 7)
        tail = QPainterPath()
        tail.moveTo(w * 0.36, h * 0.64)
        tail.lineTo(w * 0.34, h * 0.78)
        tail.lineTo(w * 0.50, h * 0.65)
        tail.closeSubpath()
        p.setBrush(QColor("white"))
        p.drawPath(bubble.united(tail))
        p.setPen(QColor(P.ACCENT))
        p.setFont(_font(int(h * 0.22), True))
        p.drawText(QRectF(w * 0.24, h * 0.27, w * 0.52, h * 0.38),
                   Qt.AlignmentFlag.AlignCenter, "AI")


class Toggle(QAbstractButton):
    def __init__(self):
        super().__init__()
        self.setCheckable(True)
        self.setFixedSize(50, 26)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._k = 0.0
        self._anim = QPropertyAnimation(self, b"knob", self)
        self._anim.setDuration(140)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.toggled.connect(self._animate)

    def _get_knob(self) -> float:
        return self._k

    def _set_knob(self, v: float) -> None:
        self._k = float(v)
        self.update()

    knob = pyqtProperty(float, fget=_get_knob, fset=_set_knob)

    def _animate(self, on: bool) -> None:
        self._anim.stop()
        self._anim.setStartValue(self._k)
        self._anim.setEndValue(1.0 if on else 0.0)
        self._anim.start()

    def set_state(self, on: bool) -> None:
        """Move the switch without firing `toggled`."""
        self.blockSignals(True)
        self.setChecked(bool(on))
        self.blockSignals(False)
        self._k = 1.0 if on else 0.0
        self.update()

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        t = self._k
        p.setPen(QPen(_mix("#d3d7dd", P.ACCENT, t), 1))
        p.setBrush(_mix("#e9edf1", P.ACCENT, t))
        p.drawRoundedRect(QRectF(0.5, 0.5, w - 1, h - 1), h / 2 - 0.5, h / 2 - 0.5)
        d = 18
        x = 4 + t * (w - 8 - d)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#ffffff"))
        p.drawEllipse(QRectF(x, (h - d) / 2, d, d))


class NavButton(QPushButton):
    def __init__(self, icon: str, text: str):
        super().__init__()
        self._icon, self._text = icon, text
        self.setCheckable(True)
        self.setAutoExclusive(False)
        self.setFixedHeight(42)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.horizontal = False
        self.vertical = False

    def set_vertical(self, on: bool = True) -> None:
        self.vertical = bool(on)
        self.setFixedSize(72, 62 if on else 42)

    def set_horizontal(self, on: bool = True) -> None:
        self.horizontal = bool(on)
        self.setFixedHeight(56 if on else 42)

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        on, hover = self.isChecked(), self.underMouse()
        if on or hover:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(P.NAV_ON if on else "#f5f6f8"))
            p.drawRoundedRect(QRectF(2, 1, self.width() - 4, self.height() - 2), 10, 10)
        if on and not self.horizontal:
            p.setBrush(QColor(P.ACCENT))
            p.drawRoundedRect(QRectF(0, self.height() / 2 - 9, 3, 18), 1.5, 1.5)
        col = QColor(P.ACCENT if on else P.DIM)
        if self.vertical:
            paint_icon(p, self._icon, (self.width() - 20) / 2, 6, 20, col)
            p.setPen(col)
            p.setFont(_font(9, on))
            p.drawText(QRectF(1, 33, self.width() - 2, 22), Qt.AlignmentFlag.AlignCenter, self._text)
            return
        if self.horizontal:
            paint_icon(p, self._icon, (self.width() - 18) / 2, 5, 18, col)
            if on:
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor(P.ACCENT))
                p.drawRoundedRect(QRectF(self.width() * 0.32, self.height() - 3,
                                         self.width() * 0.36, 2), 1, 1)
            p.setPen(col)
            p.setFont(_font(11, on))
            p.drawText(QRectF(2, 27, self.width() - 4, 24),
                       Qt.AlignmentFlag.AlignCenter, self._text)
            return
        paint_icon(p, self._icon, 16, (self.height() - 18) / 2, 18, col)
        p.setPen(col)
        p.setFont(_font(14, on))
        p.drawText(QRectF(46, 0, self.width() - 50, self.height()),
                   Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, self._text)


class IconButton(QPushButton):
    def __init__(self, icon: str, size: int = 42):
        super().__init__()
        self._icon = icon
        self.setFixedSize(size, size)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def set_icon(self, icon: str) -> None:
        self._icon = icon
        self.update()

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        hover = self.underMouse()
        p.setPen(QPen(QColor(P.CARD_LINE), 1))
        p.setBrush(QColor("#e9edf5" if hover else "#f4f5f7"))
        p.drawRoundedRect(QRectF(0.5, 0.5, self.width() - 1, self.height() - 1), 12, 12)
        paint_icon(p, self._icon, (self.width() - 20) / 2, (self.height() - 20) / 2, 20,
                   QColor(P.TEXT if self._icon == "mic" else P.DIM), 1.8, "#f4f5f7")


def _card(title: str | None = None) -> tuple[QFrame, QVBoxLayout]:
    f = QFrame()
    f.setObjectName("card")
    lay = QVBoxLayout(f)
    lay.setContentsMargins(22, 20, 22, 20)
    lay.setSpacing(10)
    if title:
        t = QLabel(title)
        t.setFont(_font(18, True))
        t.setStyleSheet(f"color:{P.TEXT};")
        lay.addWidget(t)
    return f, lay


def _button(text: str, primary: bool = False) -> QPushButton:
    b = QPushButton(text)
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    b.setFixedHeight(36)
    b.setFont(_font(13, True))
    if primary:
        b.setStyleSheet(f"QPushButton{{background:{P.ACCENT};color:white;border:1px solid {P.ACCENT};"
                        f"border-radius:9px;padding:0 18px;}}"
                        f"QPushButton:hover{{background:#2449d8;}}")
    else:
        b.setStyleSheet(f"QPushButton{{background:#f1f2f4;color:{P.TEXT};"
                        f"border:1px solid #e2e5e9;border-radius:9px;padding:0 16px;}}"
                        f"QPushButton:hover{{background:#e9edf5;border-color:#cfd5dd;}}")
    return b


class HistoryList(QScrollArea):
    """Command history: what you said and what the assistant answered."""
    MAX = 80

    def __init__(self):
        super().__init__()
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        inner = QWidget()
        inner.setStyleSheet("background:transparent;")
        self._lay = QVBoxLayout(inner)
        self._lay.setContentsMargins(0, 0, 6, 0)
        self._lay.setSpacing(8)
        self._lay.addStretch(1)
        self.setWidget(inner)
        self._placeholder: QLabel | None = None
        self._count = 0

    @staticmethod
    def _style(kind: str) -> tuple[str, int]:
        return {
            "user": (f"color:{P.TEXT};border-left:3px solid {P.ACCENT};", 15),
            "ai":   (f"color:#b4bccb;border-left:3px solid #3a414f;", 15),
            "sys":  (f"color:{P.FAINT};border-left:3px solid #242a36;", 12),
            "err":  (f"color:{P.RED};border-left:3px solid {P.RED};", 13),
        }.get(kind, (f"color:{P.DIM};border-left:3px solid #3a414f;", 14))

    def _make(self, text: str, kind: str) -> QLabel:
        css, px = self._style(kind)
        lab = QLabel(text)
        lab.setWordWrap(True)
        lab.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        lab.setFont(_font(px, kind == "user"))
        lab.setStyleSheet(css + "padding:2px 0 2px 10px;background:transparent;")
        return lab

    def add_welcome(self, welcome: str, empty: str) -> None:
        self._lay.insertWidget(self._lay.count() - 1, self._make(welcome, "user"))
        self._placeholder = self._make(empty, "other")
        self._lay.insertWidget(self._lay.count() - 1, self._placeholder)

    def add(self, text: str, kind: str) -> None:
        if self._placeholder is not None and kind in ("user", "ai"):
            self._placeholder.deleteLater()
            self._placeholder = None
        self._lay.insertWidget(self._lay.count() - 1, self._make(text, kind))
        self._count += 1
        while self._lay.count() - 1 > self.MAX:
            item = self._lay.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()
        QTimer.singleShot(0, lambda: self.verticalScrollBar().setValue(
            self.verticalScrollBar().maximum()))


class ModernSetupOverlay(QWidget):
    """First-run card: paste the Gemini API key. Same `done(key, os)` signal as the
    classic SetupOverlay, so the rest of the app does not care which one it got."""
    done = pyqtSignal(str, str)
    W, H = 500, 480

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(self.W, self.H)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(
            f"ModernSetupOverlay{{background:{P.CARD};border:1px solid {P.CARD_LINE};border-radius:22px;}}"
            f"QLabel{{background:transparent;color:{P.TEXT};}}"
            f"QLineEdit{{background:#151a23;color:{P.TEXT};border:1px solid {P.CARD_LINE};"
            f"border-radius:10px;padding:9px 12px;font-size:14px;}}"
            f"QLineEdit:focus{{border:1px solid {P.ACCENT};}}")
        self._os = {"darwin": "mac", "windows": "windows"}.get(platform.system().lower(), "linux")

        lay = QVBoxLayout(self)
        lay.setContentsMargins(34, 28, 34, 26)
        lay.setSpacing(8)
        logo = Logo(56)
        lay.addWidget(logo, 0, Qt.AlignmentFlag.AlignHCenter)
        lay.addSpacing(6)
        title = QLabel("Добро пожаловать")
        title.setFont(_font(24, True))
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(title)
        sub = QLabel("Чтобы включить искусственный интеллект,\nвставь ключ Google Gemini API.")
        sub.setFont(_font(14))
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sub.setStyleSheet(f"color:{P.DIM};")
        lay.addWidget(sub)
        link = QLabel(f'<a href="https://aistudio.google.com/app/apikey" style="color:{P.ACCENT_HI};'
                      f'text-decoration:none;">Получить бесплатный ключ →</a>')
        link.setTextFormat(Qt.TextFormat.RichText)
        link.setOpenExternalLinks(True)
        link.setFont(_font(13, True))
        link.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(link)
        lay.addSpacing(10)

        cap = QLabel("Ключ API")
        cap.setFont(_font(13, True))
        cap.setStyleSheet(f"color:{P.DIM};")
        lay.addWidget(cap)
        row = QHBoxLayout()
        self._key = QLineEdit()
        self._key.setEchoMode(QLineEdit.EchoMode.Password)
        self._key.setPlaceholderText("AIza…")
        self._key.returnPressed.connect(self._submit)
        self._eye = _button("Показать")
        self._eye.clicked.connect(self._toggle_echo)
        row.addWidget(self._key, 1)
        row.addWidget(self._eye)
        lay.addLayout(row)
        self._err = QLabel("")
        self._err.setFont(_font(12))
        self._err.setStyleSheet(f"color:{P.RED};")
        lay.addWidget(self._err)

        cap2 = QLabel("Операционная система (определена автоматически)")
        cap2.setFont(_font(13, True))
        cap2.setStyleSheet(f"color:{P.DIM};")
        lay.addWidget(cap2)
        osrow = QHBoxLayout()
        self._os_btns: dict[str, QPushButton] = {}
        for k, label in (("windows", "Windows"), ("mac", "macOS"), ("linux", "Linux")):
            b = QPushButton(label)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setFixedHeight(36)
            b.setFont(_font(13, True))
            b.clicked.connect(lambda _=False, key=k: self._select_os(key))
            osrow.addWidget(b)
            self._os_btns[k] = b
        lay.addLayout(osrow)
        self._select_os(self._os)
        lay.addStretch(1)
        go = _button("Продолжить", primary=True)
        go.setFixedHeight(42)
        go.clicked.connect(self._submit)
        lay.addWidget(go)

    def _toggle_echo(self) -> None:
        hidden = self._key.echoMode() == QLineEdit.EchoMode.Password
        self._key.setEchoMode(QLineEdit.EchoMode.Normal if hidden else QLineEdit.EchoMode.Password)
        self._eye.setText("Скрыть" if hidden else "Показать")

    def _select_os(self, key: str) -> None:
        self._os = key
        for k, b in self._os_btns.items():
            on = k == key
            b.setStyleSheet(
                f"QPushButton{{background:{P.ACCENT if on else '#232a37'};color:{'white' if on else P.TEXT};"
                f"border:1px solid {P.ACCENT if on else P.CARD_LINE};border-radius:10px;}}"
                f"QPushButton:hover{{background:{P.ACCENT_HI if on else '#2b3342'};}}")

    def _submit(self) -> None:
        key = self._key.text().strip()
        if not key:
            self._err.setText("Вставь ключ в поле выше.")
            return
        if any(ch.isspace() for ch in key) or len(key) < 20:
            self._err.setText("Ключ выглядит неполным: проверь, что скопирован целиком, без пробелов.")
            return
        self._err.setText("")
        self.done.emit(key, self._os)


# ── the shell ──────────────────────────────────────────────────────────────────
class ModernShell(QWidget):
    _wake_sig = pyqtSignal(bool)

    PAGES = [("home", "Главная", "home"), ("ai", "Чат", "ai"),
             ("history", "История", "history"),
             ("commands", "Команды", "list"), ("addons", "Плагины", "grid"),
             ("help", "Справка", "help"), ("account", "Аккаунт", "info"),
             ("settings", "Настройки", "sliders")]
    NAV_STACK_INDEXES = [0, 3, 7, 1, 2, 4, 5, 6]
    PAGE_TITLES = {0: "Главная", 1: "Команды", 2: "Плагины", 3: "Чат",
                   4: "Справка", 5: "Аккаунт", 6: "Настройки", 7: "История"}

    def __init__(self, win: "ModernWindow"):
        super().__init__()
        self._win = win
        self._state = "LISTENING"
        self._level = 0.0
        self._sched: deque = deque()
        self._t0 = time.monotonic()
        self._page = 0
        self._catalog = None
        self._recent: deque = deque(maxlen=30)     # what the user said, for the History widget
        self._desk_index = 0                        # 0 = the main Home, 1.. = custom desks
        self._edit = False
        self._dialog = None
        self._pet = None
        self._orb_win = None
        self._prefix_cards: list = []              # extra prefix switches kept in sync
        self._sync_n = 0
        from core.widget_data import AwayLock
        self._away = AwayLock()

        self.setStyleSheet(f"""
            QWidget {{ color: {P.TEXT}; }}
            QLabel {{ background: transparent; color: {P.TEXT}; }}
            QFrame#card, QFrame#newsCard {{ background: #ffffff; border: 1px solid #e2e5e9; border-radius: 12px; }}
            QFrame#sidebar {{ background: #ffffff; border: none; border-right: 1px solid #e2e5e9; }}
            QFrame#heroCard {{ background: #ffffff; border: 1px solid #e2e5e9; border-radius: 12px; }}
            QScrollArea {{ background: transparent; border: none; }}
            QScrollBar:vertical {{ background: transparent; width: 8px; margin: 2px; }}
            QScrollBar::handle:vertical {{ background: #cfd3d9; border-radius: 4px; min-height: 28px; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
            QLineEdit {{ background: #f0f1f3; color: {P.TEXT}; border: 1px solid #e5e7ea;
                        border-radius: 9px; padding: 9px 14px; font-size: 14px; }}
            QLineEdit:focus {{ border: 1px solid {P.ACCENT}; background: #ffffff; }}
            QTextBrowser {{ background: #ffffff; border: none; color: {P.TEXT}; font-size: 14px; }}
            QSlider::groove:horizontal {{ height: 4px; background: #dce0e6; border-radius: 2px; }}
            QSlider::sub-page:horizontal {{ background: {P.ACCENT}; border-radius: 2px; }}
            QSlider::handle:horizontal {{ background: white; border: 1px solid #cdd2da; width: 16px; height: 16px;
                                         margin: -6px 0; border-radius: 8px; }}
        """)

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        main = QVBoxLayout()
        main.setContentsMargins(22, 12, 22, 18)
        main.setSpacing(12)
        main.addLayout(self._build_header())
        from ai_companion_patch.glass_theme import SmoothStackedWidget
        self._stack = SmoothStackedWidget()
        self._stack.setStyleSheet("background: transparent;")
        self._pages = [self._page_home(), self._page_commands(), self._page_addons(),
                       self._page_ai(), self._page_help(), self._page_account(),
                       self._page_settings(), self._page_history()]
        for pg in self._pages:
            self._stack.addWidget(pg)
        main.addWidget(self._stack, 1)
        root.addWidget(self._build_sidebar())
        root.addLayout(main, 1)

        # live data from the existing machinery
        win._log_sig.connect(self.on_log)
        win._state_sig.connect(self.on_state)
        win._content_sig.connect(self.on_content)
        self._wake_sig.connect(self._set_wake_switch)

        self._tick = QTimer(self)
        self._tick.timeout.connect(self._on_tick)
        self._tick.start(33)
        self._sync = QTimer(self)
        self._sync.timeout.connect(self._sync_state)
        self._sync.start(500)
        self._poll_wake()
        if hasattr(win, "_desk_sig"):
            win._desk_sig.connect(self.select_desk_by_name)

        self._select(0)
        if get_ui_setting("pet_enabled", False):
            self.set_pet(True)
        if get_ui_setting("orb_overlay", False):
            self.set_orb_overlay(True)

    # ── construction helpers ──────────────────────────────────────────────────
    def _title(self) -> str:
        name = (getattr(self._win, "_assistant_name", "") or "").strip()
        return name if name and name != "OMNIX AI" else APP_TITLE

    def refresh_title(self) -> None:
        self._name_lbl.setText(self._title())
        self._win.setWindowTitle(self._title())
        self._welcome_text = f"Добро пожаловать в {self._title()}!"
        if hasattr(self, "_welcome_label"):
            self._welcome_label.setText(self._welcome_text)

    def _build_sidebar(self) -> QFrame:
        sb = QFrame()
        sb.setObjectName("sidebar")
        sb.setFixedWidth(88)
        lay = QVBoxLayout(sb)
        lay.setContentsMargins(8, 16, 8, 14)
        lay.setSpacing(8)
        brand = QLabel("AI")
        brand.setAlignment(Qt.AlignmentFlag.AlignCenter)
        brand.setFont(_font(20, True))
        brand.setStyleSheet(f"color:{P.ACCENT};")
        lay.addWidget(brand)
        lay.addSpacing(10)
        self._nav: list[NavButton] = []
        from ai_companion_patch.glass_theme import SlidingIndicator
        nav_host = QWidget(sb)
        nav_host.setStyleSheet("background:transparent;")
        nav_lay = QVBoxLayout(nav_host)
        nav_lay.setContentsMargins(0, 0, 0, 0)
        nav_lay.setSpacing(8)
        self._nav_host = nav_host
        for i, (_k, label, icon) in enumerate(self.PAGES):
            b = NavButton(icon, label)
            b.set_vertical()
            b.clicked.connect(lambda _=False, n=i: self._select(self.NAV_STACK_INDEXES[n]))
            nav_lay.addWidget(b)
            self._nav.append(b)
        lay.addWidget(nav_host)
        self._nav_indicator = SlidingIndicator(nav_host)
        lay.addStretch(1)
        return sb

    def _build_header(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(12)
        self._page_lbl = QLabel("Главная")
        self._page_lbl.setFont(_font(22, True))
        row.addWidget(self._page_lbl)
        row.addStretch(1)
        self._search_field = QLineEdit()
        self._search_field.setPlaceholderText("Поиск новостей и функций")
        self._search_field.setFixedWidth(300)
        self._search_field.textChanged.connect(self._filter_news)
        row.addWidget(self._search_field)
        row.addStretch(1)
        self._status_pill = QLabel("●  Слушаю")
        self._status_pill.setFont(_font(12, True))
        self._status_pill.setStyleSheet("color:#16845d; background:#e9f7f0; border:1px solid #cdebdc; border-radius:10px; padding:7px 10px;")
        row.addWidget(self._status_pill)
        self._mic = IconButton("mic")
        self._mic.setToolTip("Микрофон: включить / выключить")
        self._mic.clicked.connect(self._toggle_mic)
        row.addWidget(self._mic)
        minimize = IconButton("collapse", 38)
        minimize.setToolTip("Свернуть")
        minimize.clicked.connect(self._win.showMinimized)
        row.addWidget(minimize)
        avatar = Logo(38)
        avatar.setToolTip("OMNIX AI")
        avatar.activated.connect(lambda: self._select(0))
        row.addWidget(avatar)
        self._name_lbl = QLabel(self._title())
        self._name_lbl.setFont(_font(13, True))
        row.addWidget(self._name_lbl)
        self._welcome_text = f"Добро пожаловать в {self._title()}!"
        return row

    # ── pages ─────────────────────────────────────────────────────────────────
    def _page_home(self) -> QWidget:
        wrap = QWidget()
        v = QVBoxLayout(wrap)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(12)
        self._tabs = QHBoxLayout()
        self._tabs.setSpacing(8)
        v.addLayout(self._tabs)
        from ai_companion_patch.glass_theme import SmoothStackedWidget
        self._desk_stack = SmoothStackedWidget()
        self._desk_stack.setStyleSheet("background: transparent;")
        self._desk_stack.addWidget(self._home_main())
        v.addWidget(self._desk_stack, 1)
        self._rebuild_tabs()
        return wrap

    def _home_main(self) -> QWidget:
        pg = QWidget()
        outer = QVBoxLayout(pg)
        outer.setContentsMargins(0, 0, 4, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        inner = QWidget()
        lay = QVBoxLayout(inner)
        lay.setContentsMargins(0, 0, 8, 10)
        lay.setSpacing(16)

        hero = QFrame()
        hero.setObjectName("heroCard")
        hero_lay = QVBoxLayout(hero)
        hero_lay.setContentsMargins(22, 18, 22, 18)
        hero_lay.setSpacing(5)
        welcome = QLabel(f"Добро пожаловать в {self._title()}!")
        self._welcome_label = welcome
        welcome.setFont(_font(21, True))
        subtitle = QLabel("Новости, обновления и полезные возможности твоего OMNIX AI")
        subtitle.setFont(_font(13))
        subtitle.setStyleSheet(f"color:{P.DIM};")
        hero_lay.addWidget(welcome)
        hero_lay.addWidget(subtitle)
        lay.addWidget(hero)

        news_title = QLabel("Новости OMNIX AI")
        news_title.setFont(_font(19, True))
        lay.addWidget(news_title)
        news_grid = QGridLayout()
        news_grid.setContentsMargins(0, 0, 0, 0)
        news_grid.setHorizontalSpacing(12)
        news_grid.setVerticalSpacing(12)
        self._news_cards = []
        items = [
            ("ОБНОВЛЕНИЕ", "Новый домашний экран", "Новости и функции OMNIX AI собраны в одной ленте. Интерфейс стал светлым и плоским."),
            ("FISH AUDIO", "Голос одним нажатием", "Выбери JARVIS, MiSide или Рика, затем активируй встроенный ключ Fish Audio в настройках."),
            ("MCP", "Подключай инструменты", "Добавляй MCP-серверы на странице настроек и используй их инструменты прямо в диалоге."),
            ("ПАМЯТЬ", "История и факты", "Разговоры сохраняются локально. Ассистент может находить полезные сведения из прошлых сессий."),
            ("КОНТЕКСТ", "Спроси о том, что на экране", "Нажми Ctrl+Alt+S, чтобы отправить активное окно ассистенту и получить помощь."),
            ("БЫСТРЫЕ ДЕЙСТВИЯ", "Работа с буфером", "Ctrl+Alt+T переводит текст, Ctrl+Alt+E объясняет его, а Ctrl+Alt+P помогает отредактировать письмо."),
        ]
        for i, (tag, title, body) in enumerate(items):
            card = QFrame()
            card.setObjectName("newsCard")
            card.setMinimumHeight(218)
            card_lay = QVBoxLayout(card)
            card_lay.setContentsMargins(16, 14, 16, 14)
            card_lay.setSpacing(7)
            art = QFrame()
            art.setObjectName("newsArt")
            art.setFixedHeight(70)
            art.setStyleSheet("background:#eef2ff;border-radius:8px;")
            art_lay = QHBoxLayout(art)
            art_lay.setContentsMargins(14, 8, 14, 8)
            art_label = QLabel(tag)
            art_label.setFont(_font(13, True))
            art_label.setStyleSheet(f"color:{P.ACCENT};")
            art_lay.addWidget(art_label)
            art_lay.addStretch(1)
            card_lay.addWidget(art)
            badge = QLabel(tag)
            badge.setFont(_font(9, True))
            badge.setStyleSheet(f"color:{P.ACCENT};")
            badge.hide()
            headline = QLabel(title)
            headline.setFont(_font(14, True))
            headline.setWordWrap(True)
            summary = QLabel(body)
            summary.setFont(_font(11))
            summary.setStyleSheet(f"color:{P.DIM};")
            summary.setWordWrap(True)
            card_lay.addWidget(badge)
            card_lay.addWidget(headline)
            card_lay.addWidget(summary, 1)
            card.setProperty("searchText", f"{tag} {title} {body}".lower())
            self._news_cards.append(card)
            news_grid.addWidget(card, i // 3, i % 3)
        lay.addLayout(news_grid)

        control, cl = _card("Быстрый доступ")
        cl.setSpacing(7)
        self._sw_prefix = self._switch_row(cl, "Режим префикса", self._on_prefix)
        self._sw_prefix.set_state(bool(get_ui_setting("prefix_mode", False)))
        self._sw_dict = self._switch_row(cl, "Диктовка", self._on_dictation)
        self._sw_silent = self._switch_row(cl, "Тихий режим", self._on_silent)
        self._sw_anim = self._switch_row(cl, "Анимация аватара", self._on_anim)
        self._sw_top = self._switch_row(cl, "Окно поверх", self._on_top)
        self._sw_silent.set_state(bool(get_ui_setting("silent_mode", False)))
        self._sw_anim.set_state(bool(get_ui_setting("avatar_animation", True)))
        self._sw_top.set_state(bool(get_ui_setting("always_on_top", False)))
        vrow = QHBoxLayout()
        vl = QLabel("Громкость")
        vl.setFont(_font(13))
        vl.setStyleSheet(f"color:{P.DIM};")
        self._vol = QSlider(Qt.Orientation.Horizontal)
        self._vol.setRange(0, 100)
        try:
            self._vol.setValue(int(get_ui_setting("output_volume", 100)))
        except (TypeError, ValueError):
            self._vol.setValue(100)
        self._vol_lbl = QLabel(f"{self._vol.value()}%")
        self._vol_lbl.setFixedWidth(46)
        self._vol_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._vol.valueChanged.connect(self._on_volume)
        vrow.addWidget(vl)
        vrow.addWidget(self._vol, 1)
        vrow.addWidget(self._vol_lbl)
        cl.addLayout(vrow)
        lay.addWidget(control)

        activity, al = _card("Последняя активность")
        self._history = HistoryList()
        self._history.setMinimumHeight(130)
        self._history.add_welcome(self._welcome_text, "Команды ещё не выполнялись")
        al.addWidget(self._history, 1)
        lay.addWidget(activity)
        lay.addStretch(1)

        scroll.setWidget(inner)
        outer.addWidget(scroll)
        return pg

    def _filter_news(self, query: str) -> None:
        query = (query or "").strip().lower()
        for card in getattr(self, "_news_cards", []):
            card.setVisible(not query or query in str(card.property("searchText") or ""))

    def _switch_row(self, lay: QVBoxLayout, text: str, handler) -> Toggle:
        row = QHBoxLayout()
        lab = QLabel(text)
        lab.setFont(_font(14))
        lab.setStyleSheet(f"color:{P.DIM};")
        sw = Toggle()
        sw.toggled.connect(handler)
        row.addWidget(lab)
        row.addStretch(1)
        row.addWidget(sw)
        lay.addLayout(row)
        return sw

    def _scroll_page(self) -> tuple[QWidget, QVBoxLayout]:
        pg = QWidget()
        outer = QVBoxLayout(pg)
        outer.setContentsMargins(0, 0, 0, 0)
        sc = QScrollArea()
        sc.setWidgetResizable(True)
        sc.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        inner = QWidget()
        inner.setStyleSheet("background: transparent;")
        lay = QVBoxLayout(inner)
        lay.setContentsMargins(0, 0, 8, 0)
        lay.setSpacing(16)
        sc.setWidget(inner)
        outer.addWidget(sc)
        return pg, lay

    def _text(self, text: str, dim: bool = True, px: int = 14) -> QLabel:
        lab = QLabel(text)
        lab.setWordWrap(True)
        lab.setFont(_font(px))
        lab.setStyleSheet(f"color:{P.DIM if dim else P.TEXT};")
        return lab

    def _page_commands(self) -> QWidget:
        pg, lay = self._scroll_page()
        from ui_panels import CommandsCard, PacksCard
        lay.addWidget(CommandsCard(self))
        lay.addWidget(PacksCard(self))
        c1, l1 = _card("Голосовые команды")
        for phrase, what in [
            ("«Открой Steam», «Запусти Дота два»", "запускает программу или игру, найденную на этом компьютере"),
            ("«Закрой Дискорд»", "закрывает программу"),
            ("Любой вопрос или просьба", "уходит искусственному интеллекту, он отвечает и выполняет действия"),
            ("«Да» / «Отмена»", "подтверждение опасного действия голосом, когда на экране полноэкранная игра"),
            ("Режим префикса", "ассистент реагирует только после слова-активации"),
        ]:
            l1.addWidget(self._text(phrase, dim=False, px=14))
            l1.addWidget(self._text(what, px=13))
        lay.addWidget(c1)

        c2, l2 = _card("Свои названия для программ и игр")
        l2.addWidget(self._text("Привяжи своё слово к игре или программе: скажешь его, и она откроется.", px=13))
        self._alias_phrase = QLineEdit()
        self._alias_phrase.setPlaceholderText("Что ты говоришь, например: моя катка")
        self._alias_target = QLineEdit()
        self._alias_target.setPlaceholderText("Название игры/программы или путь к .exe")
        browse = _button("Обзор…")
        browse.clicked.connect(self._browse_target)
        add = _button("Добавить", primary=True)
        add.clicked.connect(self._add_alias)
        l2.addWidget(self._alias_phrase)
        trow = QHBoxLayout()
        trow.addWidget(self._alias_target, 1)
        trow.addWidget(browse)
        l2.addLayout(trow)
        l2.addWidget(add, 0, Qt.AlignmentFlag.AlignLeft)
        self._alias_box = QVBoxLayout()
        self._alias_box.setSpacing(6)
        l2.addLayout(self._alias_box)
        lay.addWidget(c2)

        c3, l3 = _card("Найдено на этом компьютере")
        self._catalog_lbl = self._text("", px=13)
        l3.addWidget(self._catalog_lbl)
        upd = _button("Обновить список")
        upd.clicked.connect(self._refresh_catalog)
        l3.addWidget(upd, 0, Qt.AlignmentFlag.AlignLeft)
        lay.addWidget(c3)
        lay.addStretch(1)
        self._reload_aliases()
        return pg

    def _page_addons(self) -> QWidget:
        pg, lay = self._scroll_page()
        intro = self._text("Дополнения расширяют возможности ассистента. Включай и выключай их здесь.", px=13)
        lay.addWidget(intro)
        self._addons_box = QVBoxLayout()
        self._addons_box.setSpacing(12)
        lay.addLayout(self._addons_box)

        built, bl = _card("Встроенные возможности")
        for name, how in (("Питомец", "Настройки → Питомец"),
                          ("Чтение вслух", "скажи «прочитай вслух»: ассистент прочитает скопированный текст"),
                          ("Блокировка, когда отхожу", "Настройки → Блокировка"),
                          ("Задачи, заметки, календарь", "«добавь задачу …», «запиши заметку …», «добавь событие 25.10 15:30 …»"),
                          ("Столы и виджеты", "вкладка + на Главной; голосом: «открой стол Игры»")):
            bl.addWidget(self._text(name, dim=False, px=14))
            bl.addWidget(self._text(how, px=12))
        lay.addWidget(built)

        tools, tl = _card("Управление")
        row = QHBoxLayout()
        sett = _button("Настройки дополнений", primary=True)
        sett.clicked.connect(lambda: self._call("_open_plugin_settings"))
        folder = _button("Открыть папку дополнений")
        folder.clicked.connect(self._open_plugins_folder)
        row.addWidget(sett)
        row.addWidget(folder)
        row.addStretch(1)
        tl.addLayout(row)
        tl.addWidget(self._text("Новое дополнение — это один файл .py: положи его в папку и перезапусти программу.", px=12))
        lay.addWidget(tools)
        lay.addStretch(1)
        return pg

    def _open_plugins_folder(self) -> None:
        folder = Path(__file__).resolve().parent / "plugins"
        try:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))
        except Exception as exc:
            self._history.add(f"ERR: {exc}", "err")

    def _plugin_toggle(self, name: str, on: bool) -> None:
        try:
            save_plugin_enabled(name, bool(on))
            self._history.add(f"Дополнение «{name}»: {'включено' if on else 'выключено'}", "sys")
        except Exception as exc:
            self._history.add(f"ERR: {exc}", "err")

    def _page_ai(self) -> QWidget:
        pg = QWidget()
        lay = QVBoxLayout(pg)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(14)
        quick, ql = _card("Быстрые действия")
        ql.setContentsMargins(14, 10, 14, 10)
        quick_row = QHBoxLayout()
        for label, prompt in (("⌕  Поиск в интернете", "Найди в интернете актуальную информацию по моему последнему вопросу"),
                              ("▣  Посмотри на экран", "Посмотри на мой экран и кратко объясни, что на нём"),
                              ("▶  Открой YouTube", "Открой YouTube")):
            action = QPushButton(label)
            action.setCursor(Qt.CursorShape.PointingHandCursor)
            action.setStyleSheet(f"QPushButton{{color:{P.TEXT};background:rgba(255,255,255,0.07);border:1px solid rgba(255,255,255,0.14);border-radius:12px;padding:10px 14px;text-align:left;}} QPushButton:hover{{background:rgba(167,139,250,0.22);border-color:{P.ACCENT};}}")
            action.clicked.connect(lambda _=False, text=prompt: self._submit_command(text))
            quick_row.addWidget(action, 1)
        ql.addLayout(quick_row)
        lay.addWidget(quick)

        chat, cl = _card("Разговор")
        self._chat = QTextBrowser()
        self._chat.setOpenLinks(False)
        cl.addWidget(self._chat, 1)
        lay.addWidget(chat, 1)

        self._result_card, rl = _card()
        self._result_title = QLabel("")
        self._result_title.setFont(_font(15, True))
        self._result_text = QTextBrowser()
        self._result_text.setMaximumHeight(170)
        rl.addWidget(self._result_title)
        rl.addWidget(self._result_text)
        self._result_card.hide()
        lay.addWidget(self._result_card)

        row = QHBoxLayout()
        self._input = QLineEdit()
        self._input.setPlaceholderText("Напиши команду или вопрос…")
        self._input.returnPressed.connect(self._send)
        send = _button("Отправить", primary=True)
        send.clicked.connect(self._send)
        row.addWidget(self._input, 1)
        row.addWidget(send)
        lay.addLayout(row)
        self._chat_html: list[str] = []
        return pg

    def _page_help(self) -> QWidget:
        pg, lay = self._scroll_page()
        intro, il = _card("Как пользоваться OMNIX AI")
        il.addWidget(self._text(
            "Говори с ассистентом через микрофон или напиши вопрос в разделе «Чат». "
            "Для команд Windows открой «Команды» или произнеси просьбу обычными словами.", px=14))
        lay.addWidget(intro)
        examples, el = _card("Примеры")
        for title, detail in (
            ("Программы", "«Открой Telegram», «Закрой Discord»"),
            ("Поиск и вопросы", "Задай вопрос голосом или в чате; для веб-поиска попроси найти информацию в интернете."),
            ("Экран", "Попроси посмотреть на экран и объяснить, что на нём."),
            ("Голос и микрофон", "В разделе «Настройки» выбери распознавание, голос и шумоподавление."),
        ):
            el.addWidget(self._text(title, dim=False, px=14))
            el.addWidget(self._text(detail, px=13))
        lay.addWidget(examples)
        actions, al = _card("Быстрый переход")
        row = QHBoxLayout()
        for label, index in (("Открыть чат", 3), ("Команды", 1), ("Настройки", 6)):
            b = _button(label, primary=label == "Открыть чат")
            b.clicked.connect(lambda _=False, n=index: self._select(n))
            row.addWidget(b)
        row.addStretch(1)
        al.addLayout(row)
        lay.addWidget(actions)
        lay.addStretch(1)
        return pg

    def _page_account(self) -> QWidget:
        pg, lay = self._scroll_page()
        profile, pl = _card("Профиль ассистента")
        pl.addWidget(self._text(self._title(), dim=False, px=17))
        pl.addWidget(self._text("Имя и цвет интерфейса настраиваются в окне персонализации.", px=13))
        edit_profile = _button("Настроить профиль", primary=True)
        edit_profile.clicked.connect(lambda: self._call("_open_customize"))
        pl.addWidget(edit_profile, 0, Qt.AlignmentFlag.AlignLeft)
        lay.addWidget(profile)

        access, acl = _card("Подключение ИИ")
        try:
            cfg = _legacy._read_full_config() or {}
            key_ready = bool(cfg.get("gemini_api_key"))
        except Exception:
            key_ready = False
        acl.addWidget(self._text(
            "Gemini API: ключ сохранён." if key_ready else "Gemini API: добавь ключ, чтобы подключить ответы ИИ.",
            dim=False, px=14))
        key_btn = _button("Изменить API-ключ" if key_ready else "Добавить API-ключ", primary=True)
        key_btn.clicked.connect(lambda: self._win._show_setup())
        acl.addWidget(key_btn, 0, Qt.AlignmentFlag.AlignLeft)
        lay.addWidget(access)

        data, dl = _card("Память и сведения")
        memory_btn = _button("Память ассистента")
        memory_btn.clicked.connect(lambda: self._call("_open_memory_panel"))
        about_btn = _button("О программе")
        about_btn.clicked.connect(self._about)
        row = QHBoxLayout()
        row.addWidget(memory_btn)
        row.addWidget(about_btn)
        row.addStretch(1)
        dl.addLayout(row)
        lay.addWidget(data)
        lay.addStretch(1)
        return pg

    def _page_settings(self) -> QWidget:
        pg, lay = self._scroll_page()
        from ui_panels import InterfaceCard, PrefixCard, SpeechRecognitionCard, VoiceCard
        lay.addWidget(VoiceCard(self))
        from ai_companion_patch.voice_presets import FishVoicePresets
        lay.addWidget(FishVoicePresets(self))
        lay.addWidget(SpeechRecognitionCard(self))
        lay.addWidget(InterfaceCard(self))
        lay.addWidget(PrefixCard(self))
        from ai_companion_patch.mcp_card import McpCard
        lay.addWidget(McpCard(self))

        cn, cnl = _card("Обработка микрофона")
        cnl.addWidget(self._text(
            "DeepFilterNet подавляет фоновый шум в реальном времени. Модель включена по умолчанию.", px=13))
        nr = QHBoxLayout()
        nr.addWidget(self._text("Шумоподавление DeepFilterNet", px=14), 1)
        self._noise_sw = Toggle()
        self._noise_sw.set_state(bool(get_ui_setting("deepfilternet_enabled", True)))
        self._noise_sw.toggled.connect(self._on_noise_suppression)
        nr.addWidget(self._noise_sw)
        cnl.addLayout(nr)
        lay.addWidget(cn)

        c2, l2 = _card("Параметры")
        for text, method in [("Имя ассистента и цвет", "_open_customize"),
                             ("Выбрать микрофон и наушники", "_open_audio_devices"),
                             ("Память ассистента", "_open_memory_panel"),
                             ("Удалённый доступ с телефона", "_open_remote")]:
            b = _button(text)
            b.clicked.connect(lambda _=False, m=method: self._call(m))
            l2.addWidget(b, 0, Qt.AlignmentFlag.AlignLeft)
        lay.addWidget(c2)

        cp, lp = _card("Питомец")
        prow = QHBoxLayout()
        prow.addWidget(self._text("Маленький друг на рабочем столе: гуляет, сидит, танцует под голос и музыку.", px=13), 1)
        self._pet_sw = Toggle()
        self._pet_sw.set_state(bool(get_ui_setting("pet_enabled", False)))
        self._pet_sw.toggled.connect(self.set_pet)
        prow.addWidget(self._pet_sw)
        lp.addLayout(prow)
        krow = QHBoxLayout()
        try:
            from ui_pet import KINDS
        except Exception:
            KINDS = {}
        for k, nm in KINDS.items():
            kb = _button(nm)
            kb.clicked.connect(lambda _=False, key=k: self.set_pet_kind(key))
            krow.addWidget(kb)
        krow.addStretch(1)
        lp.addLayout(krow)
        lay.addWidget(cp)

        cl2, ll2 = _card("Блокировка, когда отхожу")
        lrow = QHBoxLayout()
        lrow.addWidget(self._text("Если ты не трогаешь клавиатуру и мышь, компьютер заблокируется сам.", px=13), 1)
        self._lock_sw = Toggle()
        self._lock_sw.set_state(bool(get_ui_setting("away_lock", False)))
        self._lock_sw.toggled.connect(lambda on: save_ui_setting("away_lock", bool(on)))
        lrow.addWidget(self._lock_sw)
        ll2.addLayout(lrow)
        mrow = QHBoxLayout()
        self._lock_lbl = QLabel("")
        self._lock_lbl.setFixedWidth(110)
        self._lock_min = QSlider(Qt.Orientation.Horizontal)
        self._lock_min.setRange(1, 60)
        try:
            self._lock_min.setValue(int(get_ui_setting("away_lock_minutes", 10)))
        except (TypeError, ValueError):
            self._lock_min.setValue(10)
        self._lock_lbl.setText(f"через {self._lock_min.value()} мин")
        self._lock_min.valueChanged.connect(self._on_lock_minutes)
        mrow.addWidget(self._lock_lbl)
        mrow.addWidget(self._lock_min, 1)
        ll2.addLayout(mrow)
        lay.addWidget(cl2)

        lay.addStretch(1)
        return pg

    def _page_history(self) -> QWidget:
        pg, lay = self._scroll_page()
        card, cl = _card("История диалогов")
        self._history_search = QLineEdit()
        self._history_search.setPlaceholderText("Поиск по переписке…")
        self._history_search.textChanged.connect(self._reload_history)
        cl.addWidget(self._history_search)
        self._history_timeline = QTextBrowser()
        self._history_timeline.setMinimumHeight(360)
        cl.addWidget(self._history_timeline)
        reload_btn = _button("Обновить историю")
        reload_btn.clicked.connect(self._reload_history)
        cl.addWidget(reload_btn, 0, Qt.AlignmentFlag.AlignLeft)
        lay.addWidget(card)
        lay.addStretch(1)
        self._reload_history()
        return pg

    def _reload_history(self, *_args) -> None:
        if not hasattr(self, "_history_timeline"):
            return
        from ai_companion_patch.memory_store import search_history, timeline
        query = self._history_search.text().strip()
        rows = []
        if query:
            rows = search_history(query, limit=200)
            grouped = {}
            from time import localtime, strftime
            for ts, role, body in rows:
                grouped.setdefault(strftime("%d.%m.%Y", localtime(ts)), []).append(
                    (strftime("%H:%M", localtime(ts)), role, body))
            days = list(grouped.items())
        else:
            days = timeline(days=30, limit=1000)
        chunks = []
        for day, entries in days:
            chunks.append(f"<h3 style='color:{P.ACCENT}'>{day}</h3>")
            for when, role, body in entries:
                label = "Ты" if role in ("user", "You", "you") else self._title()
                from html import escape
                chunks.append(f"<p><span style='color:{P.DIM}'>{when}</span> &nbsp;"
                              f"<b>{escape(label)}</b><br>{escape(str(body)).replace(chr(10), '<br>')}</p>")
        self._history_timeline.setHtml("".join(chunks) if chunks else "История пока пуста.")

    # ── behaviour ─────────────────────────────────────────────────────────────
    def _select(self, idx: int) -> None:
        self._page = idx
        self._stack.setCurrentIndex(idx)
        for i, b in enumerate(self._nav):
            b.setChecked(self.NAV_STACK_INDEXES[i] == idx)
        self._page_lbl.setText(self.PAGE_TITLES.get(idx, "Главная"))
        if idx == 2:
            self._reload_addons()
        if idx == 1:
            self._reload_aliases()
        if idx == 7:
            self._reload_history()
        nav_i = next((i for i, stack_i in enumerate(self.NAV_STACK_INDEXES) if stack_i == idx), None)
        if nav_i is not None and hasattr(self, "_nav_indicator"):
            QTimer.singleShot(0, lambda b=self._nav[nav_i]: self._nav_indicator.move_to(b))
        self.update()

    def _call(self, method: str) -> None:
        try:
            getattr(self._win, method)()
        except Exception as exc:
            self._history.add(f"SYS: {exc}", "err")

    def _toggle_mic(self) -> None:
        self._call("_toggle_mute")
        self._sync_state()

    def _on_prefix(self, on: bool) -> None:
        """Prefix mode: only phrases that start with the assistant's name are handled."""
        save_ui_setting("prefix_mode", bool(on))
        self._sw_prefix.set_state(bool(on))
        for sw in self._prefix_cards:
            sw.set_state(bool(on))

    def _on_dictation(self, on: bool) -> None:
        """Voice typing: what you say is typed into the window you are working in."""
        from core import dictation
        dictation.STATE.set_active(bool(on))

    def _on_silent(self, on: bool) -> None:
        save_ui_setting("silent_mode", bool(on))

    def _on_anim(self, on: bool) -> None:
        save_ui_setting("avatar_animation", bool(on))
        self.update()

    def _on_top(self, on: bool) -> None:
        save_ui_setting("always_on_top", bool(on))
        self._win.apply_on_top(bool(on))

    def _on_volume(self, v: int) -> None:
        self._vol_lbl.setText(f"{v}%")
        save_ui_setting("output_volume", int(v))

    def _on_noise_suppression(self, enabled: bool) -> None:
        save_ui_setting("deepfilternet_enabled", bool(enabled))
        cb = getattr(self._win, "on_noise_suppression_change", None)
        if cb:
            try:
                cb(bool(enabled))
            except Exception as exc:
                self._history.add(f"SYS: Перезапусти аудиосессию, чтобы применить фильтр: {exc}", "sys")

    def _poll_wake(self) -> None:
        self._sw_prefix.set_state(bool(get_ui_setting("prefix_mode", False)))

    def _on_lock_minutes(self, v: int) -> None:
        self._lock_lbl.setText(f"через {v} мин")
        save_ui_setting("away_lock_minutes", int(v))

    def _set_wake_switch(self, on: bool) -> None:
        self._sw_prefix.set_state(on)

    def _sync_state(self) -> None:
        self._mic.set_icon("mic_off" if getattr(self._win, "_muted", False) else "mic")
        self._sync_n += 1
        try:
            from core import dictation
            self._sw_dict.set_state(dictation.STATE.active)      # also follows «начни диктовку»
        except Exception:
            pass
        if self._sync_n % 10 == 0:               # every ~5 s
            try:
                if self._away.check(bool(get_ui_setting("away_lock", False)),
                                    float(get_ui_setting("away_lock_minutes", 10))):
                    self._history.add("ПК заблокирован: тебя не было за компьютером.", "sys")
            except Exception:
                pass

    def _send(self) -> None:
        self._submit_command(self._input.text().strip())

    def _submit_command(self, txt: str) -> None:
        txt = (txt or "").strip()
        if not txt:
            return
        self._input.clear()
        self._win._log_sig.emit(f"You: {txt}")
        cb = getattr(self._win, "on_text_command", None)
        if cb:
            threading.Thread(target=cb, args=(txt,), daemon=True).start()

    def _about(self) -> None:
        QMessageBox.information(
            self._win, f"О программе — {self._title()}",
            f"{self._title()}  ·  сборка {APP_BUILD}\n\n"
            "Голос: модели Silero. Распознавание речи: Whisper. "
            "Ответы: Google Gemini (нужен собственный ключ).")

    # ── desks ─────────────────────────────────────────────────────────────────
    def recent_commands(self) -> list[str]:
        return list(self._recent)

    def _tab_style(self, on: bool) -> str:
        return (f"QPushButton{{background:{P.ACCENT if on else '#1b212c'};color:{'white' if on else P.DIM};"
                f"border:1px solid {P.ACCENT if on else P.CARD_LINE};border-radius:12px;padding:0 16px;}}"
                f"QPushButton:hover{{background:{P.ACCENT_HI if on else '#232a37'};color:white;}}")

    def _rebuild_tabs(self) -> None:
        import ui_widgets as W
        from core import desks
        while self._tabs.count():
            it = self._tabs.takeAt(0)
            if it and it.widget():
                it.widget().deleteLater()
        while self._desk_stack.count() > 1:                 # keep the main Home (index 0)
            w = self._desk_stack.widget(1)
            self._desk_stack.removeWidget(w)
            w.deleteLater()
        self._tab_btns: list[QPushButton] = []
        names = ["Главная"] + [d["name"] for d in desks.list_desks()]
        for i, name in enumerate(names):
            b = QPushButton(name)
            b.setFixedHeight(36)
            b.setFont(_font(13, True))
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda _=False, n=i: self._select_desk(n))
            self._tabs.addWidget(b)
            self._tab_btns.append(b)
        for d in desks.list_desks():
            self._desk_stack.addWidget(W.DeskView(self, d["id"]))
        plus = QPushButton("+")
        plus.setFixedSize(36, 36)
        plus.setToolTip("Новый стол")
        plus.setFont(_font(18, True))
        plus.setCursor(Qt.CursorShape.PointingHandCursor)
        plus.setStyleSheet(self._tab_style(False))
        plus.clicked.connect(self._new_desk)
        self._tabs.addWidget(plus)
        self._tabs.addStretch(1)
        self._add_w_btn = _button("＋ Виджет", primary=True)
        self._add_w_btn.clicked.connect(self._add_widget)
        self._del_desk_btn = _button("Удалить стол")
        self._del_desk_btn.clicked.connect(self._delete_desk)
        self._edit_btn = QPushButton("✎")
        self._edit_btn.setFixedSize(36, 36)
        self._edit_btn.setToolTip("Изменить стол")
        self._edit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._edit_btn.clicked.connect(self._toggle_edit)
        for w in (self._add_w_btn, self._del_desk_btn, self._edit_btn):
            self._tabs.addWidget(w)
        self._select_desk(min(self._desk_index, len(names) - 1))

    def _current_deskview(self):
        return self._desk_stack.widget(self._desk_index) if self._desk_index > 0 else None

    def _select_desk(self, i: int) -> None:
        self._desk_index = max(0, i)
        self._desk_stack.setCurrentIndex(self._desk_index)
        for n, b in enumerate(self._tab_btns):
            b.setStyleSheet(self._tab_style(n == self._desk_index))
        custom = self._desk_index > 0
        self._edit_btn.setVisible(custom)
        self._add_w_btn.setVisible(custom and self._edit)
        self._del_desk_btn.setVisible(custom and self._edit)
        self._edit_btn.setStyleSheet(self._tab_style(self._edit and custom))
        dv = self._current_deskview()
        if dv is not None:
            dv.set_edit(self._edit)
        self.update()

    def select_desk_by_name(self, name: str) -> None:
        """Voice: «открой стол Игры»."""
        from core import desks
        found = desks.find_desk(name)
        if found is None:
            return
        ids = [d["id"] for d in desks.list_desks()]
        self._select(0)
        self._select_desk(ids.index(found["id"]) + 1)

    def _toggle_edit(self) -> None:
        self._edit = not self._edit
        self._select_desk(self._desk_index)

    def _current_desk_id(self):
        from core import desks
        i = self._desk_index - 1
        ds = desks.list_desks()
        return ds[i]["id"] if 0 <= i < len(ds) else None

    def _new_desk(self) -> None:
        import ui_widgets as W
        dlg = W.NewDeskDialog(self)
        dlg.created.connect(self._create_desk)
        self.show_dialog(dlg)

    def _create_desk(self, name: str, preset: str) -> None:
        from core import desks
        desk = desks.create_desk(name, preset)
        self.close_dialog()
        self._desk_index = len(desks.list_desks())
        self._rebuild_tabs()
        self._history.add(f"Создан стол «{desk['name']}»", "sys")

    def _delete_desk(self) -> None:
        from core import desks
        did = self._current_desk_id()
        if did is None:
            return
        desks.delete_desk(did)
        self._edit = False
        self._desk_index = 0
        self._rebuild_tabs()

    def _add_widget(self) -> None:
        import ui_widgets as W
        dlg = W.AddWidgetDialog(self)
        dlg.chosen.connect(self._widget_chosen)
        self.show_dialog(dlg)

    def _widget_chosen(self, wtype: str) -> None:
        from core import desks
        did = self._current_desk_id()
        if did is not None:
            desks.add_widget(did, wtype)
            dv = self._current_deskview()
            if dv is not None:
                dv.rebuild()
                dv.set_edit(self._edit)
        self.close_dialog()

    def show_dialog(self, dlg) -> None:
        self.close_dialog()
        self._dialog = dlg
        dlg.closed.connect(self.close_dialog)
        self._center_dialog()
        dlg.show()
        dlg.raise_()

    def close_dialog(self) -> None:
        dlg, self._dialog = self._dialog, None
        if dlg is not None:
            try:
                dlg.hide()
                dlg.deleteLater()
            except RuntimeError:
                pass

    def _center_dialog(self) -> None:
        d = self._dialog
        if d is not None:
            d.move(max(0, (self.width() - d.width()) // 2), max(0, (self.height() - d.height()) // 2))

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._center_dialog()

    # ── pet ───────────────────────────────────────────────────────────────────
    def set_pet(self, on: bool) -> None:
        save_ui_setting("pet_enabled", bool(on))
        if on:
            if self._pet is None:
                from ui_pet import PetWindow
                self._pet = PetWindow(str(get_ui_setting("pet_kind", "blob")))
            self._pet.start()
        elif self._pet is not None:
            self._pet.stop()
        if hasattr(self, "_pet_sw"):
            self._pet_sw.set_state(bool(on))

    def set_pet_kind(self, kind: str) -> None:
        save_ui_setting("pet_kind", kind)
        if self._pet is not None:
            self._pet.set_kind(kind)

    def set_orb_overlay(self, on: bool) -> None:
        """The live avatar: the breathing circles in a corner of the desktop."""
        save_ui_setting("orb_overlay", bool(on))
        if on:
            if self._orb_win is None:
                from ui_pet import OrbOverlay
                self._orb_win = OrbOverlay()
            self._orb_win.start()
        elif self._orb_win is not None:
            self._orb_win.stop()

    def shutdown(self) -> None:
        if self._orb_win is not None:
            try:
                self._orb_win.stop()
                self._orb_win.close()
            except Exception:
                pass
        if self._pet is not None:
            try:
                self._pet.stop()
                self._pet.close()
            except Exception:
                pass

    # commands page
    def _get_catalog(self):
        if self._catalog is None:
            from core.app_catalog import AppCatalog
            self._catalog = AppCatalog(logger=lambda _m: None)
        return self._catalog

    def _browse_target(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self._win, "Выбери программу", "",
                                              "Программы (*.exe *.lnk);;Все файлы (*.*)")
        if path:
            self._alias_target.setText(path)

    def _add_alias(self) -> None:
        phrase, target = self._alias_phrase.text().strip(), self._alias_target.text().strip()
        if not phrase or not target:
            return
        self._get_catalog().add_alias(phrase, target)
        self._alias_phrase.clear()
        self._alias_target.clear()
        self._reload_aliases()

    def _reload_aliases(self) -> None:
        while self._alias_box.count():
            it = self._alias_box.takeAt(0)
            if it and it.widget():
                it.widget().deleteLater()
        try:
            cat = self._get_catalog()
            for phrase, target in cat.aliases().items():
                row = QWidget()
                rl = QHBoxLayout(row)
                rl.setContentsMargins(0, 0, 0, 0)
                lab = QLabel(f"«{phrase}»  →  {target}")
                lab.setFont(_font(13))
                x = QPushButton("✕")
                x.setFixedSize(28, 28)
                x.setCursor(Qt.CursorShape.PointingHandCursor)
                x.setStyleSheet(f"QPushButton{{background:transparent;color:{P.DIM};border:none;}}"
                                f"QPushButton:hover{{color:{P.RED};}}")
                x.clicked.connect(lambda _=False, ph=phrase: (cat.remove_alias(ph), self._reload_aliases()))
                rl.addWidget(lab, 1)
                rl.addWidget(x)
                self._alias_box.addWidget(row)
            self._catalog_lbl.setText(f"Программ и игр в списке: {len(cat.entries)}")
        except Exception as exc:
            self._catalog_lbl.setText(f"Не удалось прочитать список: {exc}")

    def _refresh_catalog(self) -> None:
        cat = self._get_catalog()
        self._catalog_lbl.setText("Ищу программы и игры…")
        cat.refresh_async(force=True)
        QTimer.singleShot(4000, self._reload_aliases)

    # add-ons page
    def _reload_addons(self) -> None:
        while self._addons_box.count():
            it = self._addons_box.takeAt(0)
            if it and it.widget():
                it.widget().deleteLater()
        items = []
        try:
            cb = getattr(self._win, "get_plugins", None)
            items = list(cb()) if callable(cb) else []
        except Exception:
            items = []
        if not items:
            card, cl = _card()
            cl.addWidget(self._text("Дополнений пока нет."))
            self._addons_box.addWidget(card)
            return
        for it in items:
            card, cl = _card()
            row = QHBoxLayout()
            col = QVBoxLayout()
            col.setSpacing(3)
            valid = bool(it.get("valid", True))
            name = str(it.get("name", "?"))
            head = QLabel(name if valid else f"{name}  ·  ошибка")
            head.setFont(_font(16, True))
            if not valid:
                head.setStyleSheet(f"color:{P.RED};")
                head.setToolTip(str(it.get("error") or ""))
            col.addWidget(head)
            desc = str(it.get("description") or (it.get("error") if not valid else "") or "")
            if desc:
                col.addWidget(self._text(desc, px=13))
            row.addLayout(col, 1)
            sw = Toggle()
            sw.set_state(bool(it.get("enabled")) and valid)
            sw.setEnabled(valid)
            sw.toggled.connect(lambda on, n=name: self._plugin_toggle(n, on))
            row.addWidget(sw, 0, Qt.AlignmentFlag.AlignVCenter)
            cl.addLayout(row)
            self._addons_box.addWidget(card)

    # log / content / state
    def on_log(self, text: str) -> None:
        t = (text or "").strip()
        if not t:
            return
        low = t.lower()
        ai = (getattr(self._win, "_assistant_name", "") or "").lower()
        if low.startswith("you:"):
            body = t[4:].strip()
            self._recent.append(body)
            self._history.add(body, "user")
            self._chat_add("Ты", body, P.ACCENT_HI)
        elif low.startswith("sys:"):
            self._history.add(t[4:].strip(), "sys")
        elif low.startswith("err"):
            self._history.add(t, "err")
        elif ai and low.startswith(ai + ":"):
            body = t[len(ai) + 1:].strip()
            self._history.add(body, "ai")
            self._chat_add(self._title(), body, "#c9d1de")
        elif ": " in t[:40]:
            body = t.split(": ", 1)[1].strip()
            self._history.add(body, "ai")
            self._chat_add(self._title(), body, "#c9d1de")
        else:
            self._history.add(t, "sys")
        if self._page == 7:
            self._reload_history()

    def _chat_add(self, who: str, body: str, color: str) -> None:
        from html import escape
        self._chat_html.append(
            f"<p style='margin:0 0 10px 0'><b style='color:{color}'>{escape(who)}</b><br>"
            f"{escape(body).replace(chr(10), '<br>')}</p>")
        self._chat_html = self._chat_html[-60:]
        self._chat.setHtml("".join(self._chat_html))
        bar = self._chat.verticalScrollBar()
        bar.setValue(bar.maximum())

    def on_content(self, title: str, text: str) -> None:
        self._result_title.setText(title)
        self._result_text.setPlainText(text)
        self._result_card.show()
        self._history.add(f"📄 {title}", "sys")

    def on_state(self, state: str) -> None:
        self._state = state or "LISTENING"
        labels = {"LISTENING": ("●  Слушаю", "#6ee7c0"), "SPEAKING": ("●  Отвечаю", "#c4b5fd"),
                  "MUTED": ("●  Микрофон выключен", "#fb7185"), "SLEEPING": ("●  Спящий режим", "#b1aaba"),
                  "THINKING": ("●  Думаю", "#fbbf24")}
        label, color = labels.get(self._state, ("●  Готов", "#6ee7c0"))
        if hasattr(self, "_status_pill"):
            self._status_pill.setText(label)
            self._status_pill.setStyleSheet(f"color:{color}; background:rgba(255,255,255,0.07); border:1px solid {color}44; border-radius:11px; padding:6px 11px;")
        self._sync_state()

    # orb feed
    def set_level(self, level: float) -> None:
        self._level = max(self._level * 0.6, min(1.0, float(level) * 1.6))

    def push_schedule(self, frames, hop: float, at: float) -> None:
        try:
            self._sched.append((float(at), float(hop), [float(f[0]) for f in frames]))
        except Exception:
            pass

    def _scheduled_level(self) -> float | None:
        now = time.time()
        while self._sched:
            at, hop, lv = self._sched[0]
            end = at + hop * len(lv)
            if now >= end:
                self._sched.popleft()
                continue
            if now < at:
                return None
            return lv[min(len(lv) - 1, int((now - at) / hop))]
        return None

    def _on_tick(self) -> None:
        sched = self._scheduled_level()
        if sched is not None:
            self._level = max(self._level * 0.82, min(1.0, sched * 1.7))
        else:
            self._level *= 0.88
        if self._pet is not None:
            self._pet.set_level(self._level)
        if self._orb_win is not None:
            self._orb_win.set_level(self._level)
        if self._page == 0 and self.isVisible():
            self.update()

    # ── flat app background ───────────────────────────────────────────────────
    def paintEvent(self, _e):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(P.BG_A))


# ── the window ─────────────────────────────────────────────────────────────────
class ModernWindow(MainWindow):
    _desk_sig = pyqtSignal(str)          # voice: switch to a desk by name
    _quit_sig = pyqtSignal()

    def __init__(self, face_path: str):
        super().__init__(face_path)
        from ai_companion_patch.glass_theme import GLASS_QSS, enable_backdrop
        self.setStyleSheet(GLASS_QSS.replace(
            "'SF Pro Text','SFProText','Segoe UI Variable','Segoe UI'", f"'{_UI_FONT}','Segoe UI'"
        ))
        self._modern_central = None
        self._tray = None
        self._proactive = None
        self._shutdown_callbacks = []
        self._quitting = False
        self._quit_sig.connect(self._quit_app)
        self._backlog: deque = deque(maxlen=80)     # replayed into a rebuilt shell
        self._log_sig.connect(self._backlog.append)
        self._legacy_central = self.takeCentralWidget()
        try:
            self._legacy_central.hide()
            self._modern_central = ModernShell(self)
            self.setCentralWidget(self._modern_central)
        except Exception:
            traceback.print_exc()
            self._modern_central = None
            raise RuntimeError("Liquid-glass interface failed to initialize")

        self.setMinimumSize(900, 600)
        self.resize(1120, 740)
        try:
            self.setWindowOpacity(max(0.4, min(1.0, int(get_ui_setting("window_opacity", 100)) / 100.0)))
        except (TypeError, ValueError):
            pass
        # The notification service relies on the Windows notification area.
        # Keep a tray icon available even when closing the window exits normally.
        self.set_tray(True)
        self.setWindowTitle(self._modern_central._title())
        enable_backdrop(self)
        if get_ui_setting("always_on_top", False):
            self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)

        # feed the circles from the voice: the facade talks to the old HUD. The wrappers look
        # the shell up at call time, so they keep working after the shell is rebuilt.
        try:
            orig_level = self.hud.set_audio_level
            orig_vis = self.hud.push_visemes

            def _level(level, _o=orig_level, _w=self):
                _o(level)
                if _w._modern_central is not None:
                    _w._modern_central.set_level(level)

            def _vis(frames, hop, at, _o=orig_vis, _w=self):
                _o(frames, hop, at)
                if _w._modern_central is not None:
                    _w._modern_central.push_schedule(frames, hop, at)

            self.hud.set_audio_level = _level
            self.hud.push_visemes = _vis
        except Exception:
            traceback.print_exc()

        # The classic window built its API-key card BEFORE the new layout existed,
        # as a child of the old (now hidden) central widget — so it was invisible
        # and the app waited for a key nobody could enter. Replace it.
        if not getattr(self, "_ready", True):
            old = getattr(self, "_overlay", None)
            if old is not None:
                try:
                    old.hide()
                    old.deleteLater()
                except RuntimeError:
                    pass
                self._overlay = None
            self._show_setup()

    # first-run API key ------------------------------------------------------
    def _show_setup(self):
        cw = self.centralWidget()
        modern = getattr(self, "_modern_central", None)
        if modern is None or cw is not modern:
            return super()._show_setup()
        prev = getattr(self, "_overlay", None)
        if prev is not None:
            try:
                prev.hide()
            except RuntimeError:
                pass
        ov = ModernSetupOverlay(cw)
        self._center_overlay(ov)
        ov.done.connect(self._on_setup_done)
        ov.show()
        ov.raise_()
        self._overlay = ov

    def _center_overlay(self, ov) -> None:
        cw = self.centralWidget()
        ov.move(max(0, (cw.width() - ov.width()) // 2), max(0, (cw.height() - ov.height()) // 2))

    def _on_setup_done(self, key: str, os_name: str):
        """Save the key. Unlike the classic handler this keeps every other setting."""
        try:
            cfg = dict(_legacy._read_full_config() or {})
        except Exception:
            cfg = {}
        cfg["gemini_api_key"] = key
        cfg["os_system"] = os_name
        os.makedirs(_legacy.CONFIG_DIR, exist_ok=True)
        _legacy.API_FILE.write_text(json.dumps(cfg, indent=4, ensure_ascii=False), encoding="utf-8")
        self._ready = True
        ov = getattr(self, "_overlay", None)
        self._overlay = None
        if ov is not None:
            try:
                ov.hide()
                ov.deleteLater()
            except RuntimeError:
                pass
        self._apply_state("LISTENING")
        self._assistant_name = cfg.get("assistant_name") or "OMNIX AI"
        if self._assistant_name.strip().casefold() == "ai companion":
            self._assistant_name = "OMNIX AI"
        self._log_sig.emit(f"SYS: Ключ сохранён. ОС: {os_name}. Подключаюсь…")

    def resizeEvent(self, e):
        super().resizeEvent(e)
        ov = getattr(self, "_overlay", None)
        if isinstance(ov, ModernSetupOverlay):
            try:
                if ov.isVisible():
                    self._center_overlay(ov)
            except RuntimeError:
                pass

    # theme, tray ----------------------------------------------------------------
    def apply_theme(self, color: str) -> None:
        """New theme colour: the shell is rebuilt so every widget picks it up."""
        set_accent(color)
        save_ui_setting("ui_accent", color)
        self._rebuild_shell()

    def _rebuild_shell(self) -> None:
        old = self._modern_central
        if old is None:
            return
        try:
            shell = ModernShell(self)
        except Exception:
            traceback.print_exc()
            return
        if self.centralWidget() is old:
            self.takeCentralWidget()
            self.setCentralWidget(shell)
            shell.show()
        self._modern_central = shell
        for line in list(self._backlog):
            shell.on_log(line)
        try:
            old.shutdown()
            old.hide()
            old.deleteLater()
        except RuntimeError:
            pass

    def set_tray(self, on: bool) -> None:
        if on and self._tray is None:
            try:
                from PyQt6.QtGui import QAction, QIcon
                from PyQt6.QtWidgets import QMenu, QSystemTrayIcon
                if not QSystemTrayIcon.isSystemTrayAvailable():
                    return
                tray = QSystemTrayIcon(QIcon(Logo(64).grab()), self)
                menu = QMenu()
                show = QAction("Открыть", menu)
                show.triggered.connect(self._show_from_tray)
                quit_ = QAction("Выход", menu)
                quit_.triggered.connect(self._quit_app)
                menu.addAction(show)
                menu.addAction(quit_)
                tray.setContextMenu(menu)
                tray.activated.connect(self._on_tray_click)
                self._tray_menu = menu
                tray.show()
                self._tray = tray
                if self._proactive is None:
                    from ai_companion_patch.proactive_notify import Proactive
                    self._proactive = Proactive(tray)
                    self._proactive.start()
            except Exception:
                traceback.print_exc()
        elif not on and self._tray is not None:
            self._tray.hide()
            if self._proactive is not None:
                try:
                    self._proactive.stop()
                except Exception:
                    pass
                self._proactive = None
            self._tray = None

    def _on_tray_click(self, reason) -> None:
        try:
            from PyQt6.QtWidgets import QSystemTrayIcon
            if reason in (QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick):
                self._show_from_tray()
        except Exception:
            pass

    def _show_from_tray(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def _quit_app(self) -> None:
        self._quitting = True
        self.close()

    def closeEvent(self, e):
        if get_ui_setting("minimize_to_tray", False) and self._tray is not None and not self._quitting:
            e.ignore()
            self.hide()
            try:
                self._tray.showMessage(self._modern_central._title(),
                                       "Работаю в фоне. Нажми на значок в трее, чтобы открыть окно.")
            except Exception:
                pass
            return
        if self._tray is not None:
            try:
                self._tray.hide()
            except Exception:
                pass
        if self._proactive is not None:
            try:
                self._proactive.stop()
            except Exception:
                pass
        for callback in list(getattr(self, "_shutdown_callbacks", [])):
            try:
                callback()
            except Exception:
                traceback.print_exc()
        shell = getattr(self, "_modern_central", None)
        if shell is not None:
            try:
                shell.shutdown()
            except Exception:
                pass
        super().closeEvent(e)

    def apply_on_top(self, on: bool) -> None:
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, bool(on))
        self.show()          # changing a window flag hides the window

    def _apply_name_update(self, *a, **k):
        super()._apply_name_update(*a, **k)
        if self._modern_central is not None:
            self._modern_central.refresh_title()

    def showEvent(self, e):
        super().showEvent(e)
        if sys.platform == "win32" and not getattr(self, "_dark_bar", False):
            self._dark_bar = True
            try:   # dark title bar (Windows 10 20H1+ / 11)
                import ctypes
                hwnd = int(self.winId())
                for attr, val in ((20, 1), (19, 1)):
                    ctypes.windll.dwmapi.DwmSetWindowAttribute(
                        hwnd, attr, ctypes.byref(ctypes.c_int(val)), 4)
                # caption colour (Windows 11): 0x00BBGGRR of the page background
                ctypes.windll.dwmapi.DwmSetWindowAttribute(
                    hwnd, 35, ctypes.byref(ctypes.c_int(0x0018100e)), 4)
            except Exception:
                pass
