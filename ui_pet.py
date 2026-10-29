"""
ui_pet.py — the desktop pet.

A small transparent window that stays on top, walks along the bottom of the
screen, sits, blinks and dances when the assistant talks or music plays. You can
click it (it dances and sends hearts) or drag it somewhere else; let go and it
drops back to the taskbar.

The four characters are original and drawn here with rectangles on a 32x32
pixel canvas, then scaled up without smoothing — no image files.
"""
from __future__ import annotations

import math

from PyQt6.QtCore import Qt, QTimer, QPointF
from PyQt6.QtGui import QColor, QFont, QImage, QPainter
from PyQt6.QtWidgets import QApplication, QWidget

from core.pet_brain import PetBrain

N = 32                 # sprite canvas, in "pixels"
SCALE = 4              # on-screen size of one pixel
KINDS = {"blob": "Капелька", "cat": "Котик", "ghost": "Призрак", "robo": "Робот"}


# ── pixel helpers ──────────────────────────────────────────────────────────────
def _rect(p: QPainter, x: int, y: int, w: int, h: int, color: str) -> None:
    p.fillRect(int(x), int(y), int(w), int(h), QColor(color))


def _ellipse(p: QPainter, cx: float, cy: float, rx: float, ry: float, color: str) -> None:
    c = QColor(color)
    for y in range(int(cy - ry), int(cy + ry) + 1):
        t = 1 - ((y + 0.5 - cy) / ry) ** 2
        if t <= 0:
            continue
        half = math.sqrt(t) * rx
        p.fillRect(int(round(cx - half)), y, max(1, int(round(half * 2))), 1, c)


def _eyes(p: QPainter, cx: int, y: int, gap: int, blink: bool, color: str = "#1b2236") -> None:
    for sx in (cx - gap, cx + gap):
        if blink:
            _rect(p, sx - 1, y + 1, 3, 1, color)
        else:
            _rect(p, sx - 1, y - 1, 2, 4, color)
            _rect(p, sx - 1, y - 1, 1, 1, "#ffffff")


def draw_sprite(kind: str, state: str, frame: int, blink: bool) -> QImage:
    """One animation frame as a 32x32 image (facing right)."""
    img = QImage(N, N, QImage.Format.Format_ARGB32)
    img.fill(QColor(0, 0, 0, 0))
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, False)

    bob = 1 if (state in ("walk", "dance") and frame) else 0
    sit = state == "sit"
    base = 29 if not sit else 29
    sway = (frame * 2 - 1) if state == "dance" else 0          # -1 / +1
    dancing = state == "dance"
    walking = state == "walk"

    if kind == "blob":
        body, shade = "#4f8cff", "#2f66d6"
        ry = 8 if not sit else 6
        cy = base - ry - bob
        _ellipse(p, 16 + sway, cy + 1, 11, ry, shade)
        _ellipse(p, 16 + sway, cy, 11, ry, body)
        _rect(p, 10 + sway, cy - ry + 2, 3, 2, "#a9c7ff")
        _eyes(p, 16 + sway, cy - 1, 4, blink)
        _rect(p, 8 + sway, cy + 2, 2, 1, "#ff9ec0")
        _rect(p, 22 + sway, cy + 2, 2, 1, "#ff9ec0")
        if dancing:
            up = frame
            _rect(p, 4 + sway, cy - 3 - up * 3, 3, 4, body)
            _rect(p, 25 + sway, cy - 3 - (1 - up) * 3, 3, 4, body)
        if walking:
            _rect(p, 11 + (frame * 4), base - 1, 3, 2, shade)
            _rect(p, 19 - (frame * 4), base - 1, 3, 2, shade)

    elif kind == "cat":
        fur, dark = "#f2994a", "#c46f22"
        ry = 6 if not sit else 5
        cy = base - ry - bob
        # tail
        _rect(p, 24 + sway, cy - 2, 3, 2, dark)
        _rect(p, 26 + sway, cy - 6 - frame * 2, 2, 5, dark)
        _ellipse(p, 16 + sway, cy + 1, 9, ry, dark)
        _ellipse(p, 16 + sway, cy, 9, ry, fur)
        hy = cy - ry - 2
        _ellipse(p, 16 + sway, hy + 1, 8, 6, fur)
        for sx, d in ((9, 1), (21, -1)):                              # ears
            _rect(p, sx + sway, hy - 7, 3, 3, fur)
            _rect(p, sx + (1 if d > 0 else 0) + sway, hy - 6, 1, 2, "#ff9ec0")
        _eyes(p, 16 + sway, hy, 4, blink, "#2a1a0a")
        _rect(p, 15 + sway, hy + 3, 2, 1, "#e0607e")
        for sy in (hy + 3, hy + 4):                                   # whiskers
            _rect(p, 6 + sway, sy, 3, 1, "#fff3e0")
            _rect(p, 23 + sway, sy, 3, 1, "#fff3e0")
        if walking:
            _rect(p, 10 + frame * 3, base - 1, 3, 2, dark)
            _rect(p, 19 - frame * 3, base - 1, 3, 2, dark)
        if dancing:
            _rect(p, 6 + sway, cy - 4 - frame * 2, 3, 3, fur)
            _rect(p, 23 + sway, cy - 4 - (1 - frame) * 2, 3, 3, fur)

    elif kind == "ghost":
        body, shade = "#eef2ff", "#b9c3e6"
        top = 8 - bob + (1 if sit else 0)
        _ellipse(p, 16 + sway, top + 7, 9, 7, shade)
        _ellipse(p, 16 + sway, top + 6, 9, 7, body)
        _rect(p, 7 + sway, top + 6, 18, 12, body)
        for i in range(5):                                            # wavy hem
            _rect(p, 7 + sway + i * 4 + (frame * 2 if i % 2 else 0), top + 17, 4, 2 + (i + frame) % 2, body)
        _eyes(p, 16 + sway, top + 8, 4, blink)
        _rect(p, 15 + sway, top + 12, 3, 2, "#6a7bb0")
        _rect(p, 7 + sway, top + 11, 2, 1, "#ffb3c8")
        _rect(p, 23 + sway, top + 11, 2, 1, "#ffb3c8")
        if dancing:
            _rect(p, 3 + sway, top + 6 - frame * 3, 4, 3, body)
            _rect(p, 25 + sway, top + 6 - (1 - frame) * 3, 4, 3, body)

    else:   # robo
        metal, dark = "#aeb8c8", "#6c788d"
        h = 8 if not sit else 6
        top = base - 12 - h - bob
        _rect(p, 15 + sway, top - 5, 2, 5, dark)                      # antenna
        _rect(p, 14 + sway, top - 7, 4, 3, "#ff5d6c" if (frame or dancing) else "#c23a48")
        _rect(p, 7 + sway, top, 18, h + 4, dark)
        _rect(p, 8 + sway, top + 1, 16, h + 2, metal)
        for sx in (11, 19):                                           # eyes
            if blink:
                _rect(p, sx + sway - 1, top + 4, 3, 1, "#0b1a2a")
            else:
                _rect(p, sx + sway - 1, top + 3, 3, 3, "#33e0ff")
        _rect(p, 12 + sway, top + h, 8, 1, dark)
        _rect(p, 9 + sway, top + h + 4, 14, 8, metal)
        _rect(p, 9 + sway, top + h + 11, 14, 1, dark)
        _rect(p, 14 + sway, top + h + 6, 4, 3, "#33e0ff" if frame else "#1fa2bd")
        if walking:
            _rect(p, 10 + frame * 4, base - 2, 4, 3, dark)
            _rect(p, 18 - frame * 4, base - 2, 4, 3, dark)
        else:
            _rect(p, 10, base - 2, 4, 3, dark)
            _rect(p, 18, base - 2, 4, 3, dark)
        if dancing:
            _rect(p, 4 + sway, top + h + 2 - frame * 4, 3, 7, metal)
            _rect(p, 25 + sway, top + h + 2 - (1 - frame) * 4, 3, 7, metal)
    p.end()
    return img


# ── the window ─────────────────────────────────────────────────────────────────
class PetWindow(QWidget):
    PAD_TOP = 28                       # room for hearts above the sprite

    def __init__(self, kind: str = "blob"):
        super().__init__(None, Qt.WindowType.FramelessWindowHint
                         | Qt.WindowType.WindowStaysOnTopHint
                         | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.kind = kind if kind in KINDS else "blob"
        self._size = N * SCALE
        self.resize(self._size, self._size + self.PAD_TOP)
        self.brain = PetBrain(self._size)
        self._level = 0.0
        self._hearts: list[list[float]] = []       # [x, y, age]
        self._drag_off: QPointF | None = None
        self._dragged = False
        self._falling = False
        self._y = 0.0
        self._cache: dict[tuple, QImage] = {}

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._place_on_ground()

    # public ---------------------------------------------------------------------
    def set_kind(self, kind: str) -> None:
        if kind in KINDS:
            self.kind = kind
            self._cache.clear()
            self.update()

    def set_level(self, level: float) -> None:
        self._level = max(self._level, float(level))

    def start(self) -> None:
        self._place_on_ground()
        self.show()
        self._timer.start(33)

    def stop(self) -> None:
        self._timer.stop()
        self.hide()

    # geometry ---------------------------------------------------------------------
    def _screen(self):
        scr = self.screen() or QApplication.primaryScreen()
        return scr.availableGeometry()

    def _ground_y(self) -> float:
        g = self._screen()
        return g.bottom() - self.height() + 8

    def _place_on_ground(self) -> None:
        g = self._screen()
        self.brain.set_bounds(g.left(), g.right())
        self._y = self._ground_y()
        self.move(int(self.brain.x), int(self._y))

    # loop ---------------------------------------------------------------------------
    def _tick(self) -> None:
        dt = 0.033
        lvl, self._level = self._level, self._level * 0.5
        if self._falling:
            self._y += 14
            if self._y >= self._ground_y():
                self._y = self._ground_y()
                self._falling = False
        elif self._drag_off is None:
            g = self._screen()
            self.brain.set_bounds(g.left(), g.right())
            self.brain.step(dt, lvl)
        self.move(int(self.brain.x), int(self._y))
        for h in self._hearts:
            h[1] -= 1.6
            h[2] += dt
        self._hearts = [h for h in self._hearts if h[2] < 1.2]
        self.update()

    # drawing ------------------------------------------------------------------------
    def _frame_image(self) -> QImage:
        state = "walk" if self.brain.state == "walk" else self.brain.state
        key = (self.kind, state, self.brain.frame, self.brain.blink, self.brain.dir)
        img = self._cache.get(key)
        if img is None:
            img = draw_sprite(self.kind, state, self.brain.frame, self.brain.blink)
            if self.brain.dir < 0:
                img = img.mirrored(True, False)
            img = img.scaled(self._size, self._size, Qt.AspectRatioMode.IgnoreAspectRatio,
                             Qt.TransformationMode.FastTransformation)
            if len(self._cache) > 64:
                self._cache.clear()
            self._cache[key] = img
        return img

    def paintEvent(self, _e):
        p = QPainter(self)
        p.drawImage(0, self.PAD_TOP, self._frame_image())
        if self._hearts:
            p.setPen(QColor("#ff6b9a"))
            f = QFont("Segoe UI Symbol")
            f.setPixelSize(18)
            p.setFont(f)
            for x, y, age in self._hearts:
                p.setOpacity(max(0.0, 1.0 - age / 1.2))
                p.drawText(int(x), int(y), "♥")

    # mouse --------------------------------------------------------------------------
    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._drag_off = e.globalPosition() - QPointF(self.pos())
            self._dragged = False

    def mouseMoveEvent(self, e):
        if self._drag_off is not None:
            pos = e.globalPosition() - self._drag_off
            if abs(pos.x() - self.x()) + abs(pos.y() - self.y()) > 4:
                self._dragged = True
            if self._dragged:
                self.brain.x = pos.x()
                self._y = pos.y()
                self.move(int(pos.x()), int(pos.y()))

    def mouseReleaseEvent(self, e):
        if e.button() != Qt.MouseButton.LeftButton:
            return
        was_drag, self._drag_off = self._dragged, None
        if was_drag:
            self._falling = self._y < self._ground_y()
        else:
            self.brain.poke()
            cx = self._size // 2
            self._hearts += [[cx - 14, self.PAD_TOP, 0.0], [cx + 4, self.PAD_TOP + 6, 0.2]]


class OrbOverlay(QWidget):
    """The live avatar: the assistant's breathing circles in a corner of the desktop.
    Drag it anywhere; it pulses with the assistant's voice."""
    SIZE = 220

    def __init__(self):
        super().__init__(None, Qt.WindowType.FramelessWindowHint
                         | Qt.WindowType.WindowStaysOnTopHint
                         | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.resize(self.SIZE, self.SIZE)
        self._level = 0.0
        self._smooth = 0.0
        self._t = 0.0
        self._drag: QPointF | None = None
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)

    def set_level(self, level: float) -> None:
        self._level = max(self._level, float(level))

    def start(self) -> None:
        g = (self.screen() or QApplication.primaryScreen()).availableGeometry()
        self.move(g.right() - self.SIZE - 24, g.bottom() - self.SIZE - 24)
        self.show()
        self._timer.start(33)

    def stop(self) -> None:
        self._timer.stop()
        self.hide()

    def _tick(self) -> None:
        self._t += 0.033
        self._smooth = max(self._level, self._smooth * 0.88)
        self._level *= 0.5
        self.update()

    def paintEvent(self, _e):
        import ui_modern as K
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        cx = cy = self.SIZE / 2
        r0 = self.SIZE * 0.46
        for col, k in zip(K.ring_colors(K.P.ACCENT), (1.0, 0.8, 0.6, 0.42, 0.26)):
            r = r0 * (k + self._smooth * 0.05 * k + 0.012 * math.sin(self._t * 1.3))
            c = QColor(col)
            c.setAlpha(235)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(c)
            p.drawEllipse(QPointF(cx, cy), r, r)

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._drag = e.globalPosition() - QPointF(self.pos())

    def mouseMoveEvent(self, e):
        if self._drag is not None:
            pos = e.globalPosition() - self._drag
            self.move(int(pos.x()), int(pos.y()))

    def mouseReleaseEvent(self, _e):
        self._drag = None
