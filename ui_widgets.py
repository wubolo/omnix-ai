"""
ui_widgets.py — the widgets that fill a desk, the desk grid and its dialogs.

Every widget is a card with a `refresh()` the desk calls once a second. Network
widgets (weather, rates) fetch in a background thread and only while visible.
In edit mode each card shows ◀ ▶ (move), ⤢ (change size) and ✕ (remove).
"""
from __future__ import annotations

import calendar
import threading
import time
from datetime import date, datetime

from PyQt6.QtCore import Qt, QTimer, QRectF, QPointF, pyqtSignal
from PyQt6.QtGui import QPainter, QColor
from PyQt6.QtWidgets import (QApplication, QFrame, QGridLayout, QHBoxLayout, QLabel,
                             QLineEdit, QPushButton, QScrollArea, QVBoxLayout, QWidget)

import ui_modern as K
from core import desks, notes
from core import widget_data as wd
from memory.config_manager import get_ui_setting, save_ui_setting

P, _font, _card, _button, Toggle = K.P, K._font, K._card, K._button, K.Toggle

MONTHS = ["", "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
          "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"]
MONTHS_GEN = ["", "января", "февраля", "марта", "апреля", "мая", "июня",
              "июля", "августа", "сентября", "октября", "ноября", "декабря"]
WEEKDAYS = ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"]
WD_SHORT = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]


def _lab(text: str = "", px: int = 14, bold: bool = False, color: str = P.TEXT, wrap: bool = False) -> QLabel:
    lab = QLabel(text)
    lab.setFont(_font(px, bold))
    lab.setStyleSheet(f"color:{color};background:transparent;")
    lab.setWordWrap(wrap)
    return lab


def _tool_button(text: str, tip: str) -> QPushButton:
    b = QPushButton(text)
    b.setFixedSize(26, 26)
    b.setToolTip(tip)
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    b.setStyleSheet(f"QPushButton{{background:#232a37;color:{P.TEXT};border:1px solid {P.CARD_LINE};"
                    f"border-radius:8px;font-size:12px;}}QPushButton:hover{{background:{P.ACCENT};}}")
    return b


class Bar(QWidget):
    """A thin horizontal gauge."""

    def __init__(self):
        super().__init__()
        self.setFixedHeight(8)
        self.value = 0.0

    def set_value(self, v: float) -> None:
        self.value = max(0.0, min(100.0, float(v)))
        self.update()

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#2a3140"))
        p.drawRoundedRect(QRectF(0, 0, w, h), 4, 4)
        col = P.ACCENT if self.value < 70 else ("#f59e0b" if self.value < 90 else P.RED)
        p.setBrush(QColor(col))
        p.drawRoundedRect(QRectF(0, 0, max(h, w * self.value / 100.0), h), 4, 4)


# ── base card ──────────────────────────────────────────────────────────────────
class WidgetCard(QFrame):
    move_left = pyqtSignal()
    move_right = pyqtSignal()
    resize_me = pyqtSignal()
    remove_me = pyqtSignal()

    def __init__(self, shell, wtype: str):
        super().__init__()
        self.shell = shell
        self.wtype = wtype
        self.setObjectName("card")
        self._root = QVBoxLayout(self)
        self._root.setContentsMargins(16, 12, 16, 14)
        self._root.setSpacing(8)
        head = QHBoxLayout()
        head.setSpacing(6)
        self._title = _lab(desks.WIDGETS[wtype][0], 13, True, P.DIM)
        head.addWidget(self._title)
        head.addStretch(1)
        self._tools = QWidget()
        tl = QHBoxLayout(self._tools)
        tl.setContentsMargins(0, 0, 0, 0)
        tl.setSpacing(4)
        for text, tip, sig in (("◀", "Левее", self.move_left), ("▶", "Правее", self.move_right),
                               ("⤢", "Размер", self.resize_me), ("✕", "Убрать", self.remove_me)):
            b = _tool_button(text, tip)
            b.clicked.connect(lambda _=False, s=sig: s.emit())
            tl.addWidget(b)
        self._tools.hide()
        head.addWidget(self._tools)
        self._root.addLayout(head)
        self.build(self._root)

    def build(self, lay: QVBoxLayout) -> None:       # overridden
        pass

    def refresh(self) -> None:                       # overridden
        pass

    def set_edit(self, on: bool) -> None:
        self._tools.setVisible(on)


class _Fetching(WidgetCard):
    """Mixin-like base for cards that load data in a thread."""
    _loaded = pyqtSignal(object)

    def start_fetch(self, fn, *args) -> None:
        def run():
            try:
                self._loaded.emit(fn(*args))
            except Exception:
                self._loaded.emit(None)
        threading.Thread(target=run, daemon=True, name=f"fetch-{self.wtype}").start()


# ── concrete widgets ────────────────────────────────────────────────────────────
class ClockWidget(WidgetCard):
    def build(self, lay):
        self._time = _lab("--:--", 38, True)
        self._date = _lab("", 14, False, P.DIM)
        lay.addWidget(self._time)
        lay.addWidget(self._date)
        lay.addStretch(1)
        self.refresh()

    def refresh(self):
        now = datetime.now()
        self._time.setText(now.strftime("%H:%M"))
        self._date.setText(f"{WEEKDAYS[now.weekday()].capitalize()}, {now.day} {MONTHS_GEN[now.month]}")


class WeatherWidget(_Fetching):
    def build(self, lay):
        self._icon = _lab("", 34)
        self._temp = _lab("—", 34, True)
        self._where = _lab("", 13, False, P.DIM)
        row = QHBoxLayout()
        row.addWidget(self._icon)
        row.addWidget(self._temp)
        row.addStretch(1)
        lay.addLayout(row)
        lay.addWidget(self._where)
        self._city = QLineEdit()
        self._city.setPlaceholderText("Твой город, например: Москва")
        self._city.returnPressed.connect(self._save_city)
        lay.addWidget(self._city)
        lay.addStretch(1)
        self._loaded.connect(self._show)
        self._last = 0.0
        self._busy = False
        self.refresh()

    def _save_city(self):
        c = self._city.text().strip()
        if c:
            save_ui_setting("weather_city", c)
            self._city.clear()
            self._last = 0.0
            self.refresh()

    def refresh(self):
        city = str(get_ui_setting("weather_city", "") or "")
        self._city.setVisible(not city)
        if not city:
            self._where.setText("Укажи город, чтобы увидеть погоду")
            return
        if not self.isVisible() or self._busy or time.time() - self._last < 900:
            return
        self._busy, self._last = True, time.time()
        self.start_fetch(wd.fetch_weather, city)

    def _show(self, data):
        self._busy = False
        if not data:
            self._where.setText("Нет связи с сервисом погоды")
            self._last = time.time() - 840        # try again in a minute
            return
        self._icon.setText(data["icon"])
        self._temp.setText(f"{data['temp']:+d}°")
        self._where.setText(f"{data['city']} · {data['text']}")


class RatesWidget(_Fetching):
    def build(self, lay):
        self._usd = _lab("USD  —", 22, True)
        self._eur = _lab("EUR  —", 22, True)
        lay.addWidget(self._usd)
        lay.addWidget(self._eur)
        self._note = _lab("в рублях", 12, False, P.FAINT)
        lay.addWidget(self._note)
        lay.addStretch(1)
        self._loaded.connect(self._show)
        self._last, self._busy = 0.0, False
        self.refresh()

    def refresh(self):
        if not self.isVisible() or self._busy or time.time() - self._last < 1800:
            return
        self._busy, self._last = True, time.time()
        self.start_fetch(wd.fetch_rates)

    def _show(self, data):
        self._busy = False
        if not data:
            self._note.setText("нет связи с сервисом курсов")
            self._last = time.time() - 1740
            return
        self._usd.setText(f"USD  {data['USD']:.2f}")
        self._eur.setText(f"EUR  {data['EUR']:.2f}")
        self._note.setText("в рублях")


class SystemWidget(WidgetCard):
    def build(self, lay):
        self._rows = {}
        for key, name in (("cpu", "Процессор"), ("ram", "Память"), ("disk", "Диск")):
            row = QHBoxLayout()
            lab = _lab(name, 13, False, P.DIM)
            lab.setFixedWidth(84)
            val = _lab("0%", 13, True)
            val.setFixedWidth(44)
            val.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            bar = Bar()
            row.addWidget(lab)
            row.addWidget(bar, 1)
            row.addWidget(val)
            lay.addLayout(row)
            self._rows[key] = (bar, val)
        lay.addStretch(1)
        self._tick = 0
        self.refresh()

    def refresh(self):
        self._tick += 1
        if self._tick % 2 and self._tick > 1:
            return
        stats = wd.system_stats()
        for key, (bar, val) in self._rows.items():
            bar.set_value(stats[key])
            val.setText(f"{stats[key]:.0f}%")


class MediaWidget(WidgetCard):
    def build(self, lay):
        row = QHBoxLayout()
        row.addStretch(1)
        for text, key, tip in (("⏮", "prev", "Назад"), ("⏯", "play_pause", "Пауза / играть"), ("⏭", "next", "Дальше")):
            b = QPushButton(text)
            b.setFixedSize(54, 44)
            b.setToolTip(tip)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            big = key == "play_pause"
            b.setStyleSheet(f"QPushButton{{background:{P.ACCENT if big else '#232a37'};color:white;"
                            f"border:1px solid {P.ACCENT if big else P.CARD_LINE};border-radius:14px;font-size:20px;}}"
                            f"QPushButton:hover{{background:{P.ACCENT_HI};}}")
            b.clicked.connect(lambda _=False, k=key: wd.press_media_key(k))
            row.addWidget(b)
        row.addStretch(1)
        lay.addLayout(row)
        lay.addWidget(_lab("Работает с любым плеером: Spotify, браузер, VLC", 12, False, P.FAINT, True))
        lay.addStretch(1)


class AppsWidget(WidgetCard):
    DEFAULTS = ("steam", "discord", "chrome", "spotify", "telegram", "notepad")

    def build(self, lay):
        self._box = QGridLayout()
        self._box.setSpacing(8)
        lay.addLayout(self._box)
        lay.addStretch(1)
        self._catalog = None
        self.reload()

    def _cat(self):
        if self._catalog is None:
            from core.app_catalog import AppCatalog
            self._catalog = AppCatalog(logger=lambda _m: None)
        return self._catalog

    def reload(self):
        while self._box.count():
            it = self._box.takeAt(0)
            if it and it.widget():
                it.widget().deleteLater()
        names = list(self._cat().aliases().keys())[:6] or list(self.DEFAULTS)
        for i, name in enumerate(names):
            b = QPushButton(name)
            b.setFixedHeight(32)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setStyleSheet(f"QPushButton{{background:#232a37;color:{P.TEXT};border:1px solid {P.CARD_LINE};"
                            f"border-radius:10px;padding:0 12px;font-size:13px;}}"
                            f"QPushButton:hover{{background:{P.ACCENT};}}")
            b.clicked.connect(lambda _=False, n=name: self._launch(n))
            self._box.addWidget(b, i // 3, i % 3)

    def _launch(self, name: str):
        def run():
            from core import app_catalog
            entry = self._cat().resolve(name)
            if entry:
                app_catalog.launch(entry)
        threading.Thread(target=run, daemon=True).start()


class HistoryWidget(WidgetCard):
    def build(self, lay):
        self._items = QVBoxLayout()
        self._items.setSpacing(6)
        lay.addLayout(self._items)
        lay.addStretch(1)
        self._sig = None
        self.refresh()

    def refresh(self):
        recent = list(self.shell.recent_commands())[-8:]
        if recent == self._sig:
            return
        self._sig = recent
        while self._items.count():
            it = self._items.takeAt(0)
            if it and it.widget():
                it.widget().deleteLater()
        if not recent:
            self._items.addWidget(_lab("Пока пусто. Скажи что-нибудь ассистенту.", 13, False, P.FAINT, True))
        for text in reversed(recent):
            self._items.addWidget(_lab(text[:60], 14))


class TasksWidget(WidgetCard):
    def build(self, lay):
        self._list = QVBoxLayout()
        self._list.setSpacing(6)
        wrap = QWidget()
        wrap.setLayout(self._list)
        wrap.setStyleSheet("background:transparent;")
        sc = QScrollArea()
        sc.setWidgetResizable(True)
        sc.setFrameShape(QFrame.Shape.NoFrame)
        sc.setWidget(wrap)
        lay.addWidget(sc, 1)
        self._add = QLineEdit()
        self._add.setPlaceholderText("Новая задача…")
        self._add.returnPressed.connect(self._on_add)
        lay.addWidget(self._add)
        self._sig = None
        self.refresh()

    def _on_add(self):
        if notes.add_task(self._add.text()):
            self._add.clear()
            self.refresh()

    def refresh(self):
        tasks = notes.tasks()
        sig = [(t["id"], t["done"], t["text"]) for t in tasks]
        if sig == self._sig:
            return
        self._sig = sig
        while self._list.count():
            it = self._list.takeAt(0)
            if it and it.widget():
                it.widget().deleteLater()
        for t in tasks:
            row = QWidget()
            rl = QHBoxLayout(row)
            rl.setContentsMargins(0, 0, 0, 0)
            rl.setSpacing(8)
            chk = QPushButton("✓" if t["done"] else "")
            chk.setCheckable(True)
            chk.setChecked(t["done"])
            chk.setFixedSize(20, 20)
            chk.setCursor(Qt.CursorShape.PointingHandCursor)
            chk.setStyleSheet("QPushButton{border:2px solid #4a5160;border-radius:10px;background:transparent;"
                              "color:white;font-size:11px;padding:0;}"
                              "QPushButton:checked{background:#22c55e;border-color:#22c55e;}")
            chk.clicked.connect(lambda on, i=t["id"]: (notes.set_task_done(i, on), self.refresh()))
            txt = _lab(t["text"], 14, False, P.FAINT if t["done"] else P.TEXT, True)
            if t["done"]:
                txt.setText(f"<s>{t['text']}</s>")
            x = QPushButton("✕")
            x.setFixedSize(22, 22)
            x.setCursor(Qt.CursorShape.PointingHandCursor)
            x.setStyleSheet(f"QPushButton{{background:transparent;color:{P.FAINT};border:none;}}"
                            f"QPushButton:hover{{color:{P.RED};}}")
            x.clicked.connect(lambda _=False, i=t["id"]: (notes.delete_task(i), self.refresh()))
            rl.addWidget(chk)
            rl.addWidget(txt, 1)
            rl.addWidget(x)
            self._list.addWidget(row)
        if not tasks:
            self._list.addWidget(_lab("Задач нет. Скажи: «добавь задачу …»", 13, False, P.FAINT, True))
        self._list.addStretch(1)


class NotesWidget(WidgetCard):
    def build(self, lay):
        self._list = QVBoxLayout()
        self._list.setSpacing(8)
        wrap = QWidget()
        wrap.setLayout(self._list)
        wrap.setStyleSheet("background:transparent;")
        sc = QScrollArea()
        sc.setWidgetResizable(True)
        sc.setFrameShape(QFrame.Shape.NoFrame)
        sc.setWidget(wrap)
        lay.addWidget(sc, 1)
        self._add = QLineEdit()
        self._add.setPlaceholderText("Новая заметка…")
        self._add.returnPressed.connect(self._on_add)
        lay.addWidget(self._add)
        self._sig = None
        self.refresh()

    def _on_add(self):
        if notes.add_note(self._add.text()):
            self._add.clear()
            self.refresh()

    def refresh(self):
        items = notes.notes()
        sig = [(n["id"], n["text"]) for n in items]
        if sig == self._sig:
            return
        self._sig = sig
        while self._list.count():
            it = self._list.takeAt(0)
            if it and it.widget():
                it.widget().deleteLater()
        for n in items[:30]:
            row = QWidget()
            rl = QHBoxLayout(row)
            rl.setContentsMargins(0, 0, 0, 0)
            txt = _lab(n["text"], 14, False, P.TEXT, True)
            x = QPushButton("✕")
            x.setFixedSize(22, 22)
            x.setCursor(Qt.CursorShape.PointingHandCursor)
            x.setStyleSheet(f"QPushButton{{background:transparent;color:{P.FAINT};border:none;}}"
                            f"QPushButton:hover{{color:{P.RED};}}")
            x.clicked.connect(lambda _=False, i=n["id"]: (notes.delete_note(i), self.refresh()))
            rl.addWidget(txt, 1)
            rl.addWidget(x)
            self._list.addWidget(row)
        if not items:
            self._list.addWidget(_lab("Заметок нет. Скажи: «запиши заметку …»", 13, False, P.FAINT, True))
        self._list.addStretch(1)


class CalendarWidget(WidgetCard):
    def build(self, lay):
        t = date.today()
        self._y, self._m = t.year, t.month
        head = QHBoxLayout()
        prev = _tool_button("◀", "Прошлый месяц")
        nxt = _tool_button("▶", "Следующий месяц")
        prev.clicked.connect(lambda: self._shift(-1))
        nxt.clicked.connect(lambda: self._shift(1))
        self._month = _lab("", 15, True)
        head.addWidget(prev)
        head.addWidget(self._month, 1, Qt.AlignmentFlag.AlignHCenter)
        head.addWidget(nxt)
        lay.addLayout(head)
        self._grid = QGridLayout()
        self._grid.setSpacing(2)
        lay.addLayout(self._grid)
        self._upcoming = _lab("", 12, False, P.DIM, True)
        lay.addWidget(self._upcoming)
        self._add = QLineEdit()
        self._add.setPlaceholderText("Событие: 25.10 15:30 Встреча")
        self._add.returnPressed.connect(self._on_add)
        lay.addWidget(self._add)
        self._sig = None
        self.refresh(force=True)

    def _shift(self, d: int):
        m = self._m + d
        self._y += (m - 1) // 12
        self._m = (m - 1) % 12 + 1
        self.refresh(force=True)

    def _on_add(self):
        parsed = notes.parse_event(self._add.text())
        if parsed:
            notes.add_event(parsed[0], parsed[2], parsed[1])
            self._add.clear()
            self.refresh(force=True)
        else:
            self._add.setPlaceholderText("Не понял дату. Пример: 25.10 15:30 Встреча")

    def refresh(self, force: bool = False):
        marked = notes.days_with_events(self._y, self._m)
        up = notes.upcoming_events(3)
        sig = (self._y, self._m, date.today(), tuple(sorted(marked)), tuple((e["id"]) for e in up))
        if sig == self._sig and not force:
            return
        self._sig = sig
        self._month.setText(f"{MONTHS[self._m]} {self._y}")
        while self._grid.count():
            it = self._grid.takeAt(0)
            if it and it.widget():
                it.widget().deleteLater()
        for c, name in enumerate(WD_SHORT):
            self._grid.addWidget(_lab(name, 11, False, P.FAINT), 0, c, Qt.AlignmentFlag.AlignCenter)
        today = date.today()
        for r, week in enumerate(calendar.monthcalendar(self._y, self._m), start=1):
            for c, day in enumerate(week):
                if not day:
                    continue
                is_today = (self._y, self._m, day) == (today.year, today.month, today.day)
                dot = " •" if day in marked else ""
                lab = _lab(f"{day}{dot}", 12, is_today, "white" if is_today else P.TEXT)
                lab.setAlignment(Qt.AlignmentFlag.AlignCenter)
                if is_today:
                    lab.setStyleSheet(f"color:white;background:{P.ACCENT};border-radius:9px;")
                self._grid.addWidget(lab, r, c)
        if up:
            self._upcoming.setText("\n".join(
                f"{e['day'][8:10]}.{e['day'][5:7]} {e.get('at', '')} {e['title']}".replace("  ", " ") for e in up))
        else:
            self._upcoming.setText("Ближайших событий нет")


class TimerWidget(WidgetCard):
    def build(self, lay):
        self._left = 0
        self._end = 0.0
        self._lab = _lab("00:00", 32, True)
        lay.addWidget(self._lab, 0, Qt.AlignmentFlag.AlignHCenter)
        row = QHBoxLayout()
        for mins in (5, 10, 25):
            b = _button(f"{mins}")
            b.setFixedHeight(30)
            b.clicked.connect(lambda _=False, m=mins: self._start(m))
            row.addWidget(b)
        lay.addLayout(row)
        stop = _button("Сброс")
        stop.setFixedHeight(30)
        stop.clicked.connect(self._reset)
        lay.addWidget(stop)

    def _start(self, mins: int):
        self._end = time.time() + mins * 60
        self.refresh()

    def _reset(self):
        self._end = 0.0
        self._lab.setText("00:00")

    def refresh(self):
        if not self._end:
            return
        left = int(self._end - time.time())
        if left <= 0:
            self._end = 0.0
            self._lab.setText("Готово!")
            QApplication.beep()
        else:
            self._lab.setText(f"{left // 60:02d}:{left % 60:02d}")


class PetControlWidget(WidgetCard):
    def build(self, lay):
        row = QHBoxLayout()
        row.addWidget(_lab("Питомец на рабочем столе", 14))
        row.addStretch(1)
        self._sw = Toggle()
        self._sw.set_state(bool(get_ui_setting("pet_enabled", False)))
        self._sw.toggled.connect(lambda on: self.shell.set_pet(on))
        row.addWidget(self._sw)
        lay.addLayout(row)
        from ui_pet import KINDS
        kinds = QHBoxLayout()
        for k, name in KINDS.items():
            b = _button(name)
            b.setFixedHeight(30)
            b.clicked.connect(lambda _=False, key=k: self.shell.set_pet_kind(key))
            kinds.addWidget(b)
        lay.addLayout(kinds)
        lay.addStretch(1)

    def refresh(self):
        self._sw.set_state(bool(get_ui_setting("pet_enabled", False)))


class OrbWidget(WidgetCard):
    """Big concentric circles, same as the Home background, as a widget."""

    def build(self, lay):
        self._title.hide()
        lay.addStretch(1)

    def refresh(self):
        self.update()

    def paintEvent(self, e):
        super().paintEvent(e)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        cx, cy = w / 2, h / 2
        r0 = min(w, h) * 0.46
        lvl = getattr(self.shell, "_level", 0.0)
        for col, k in zip(K.ring_colors(P.ACCENT), (1.0, 0.8, 0.6, 0.42, 0.26)):
            r = r0 * (k + lvl * 0.04 * k + 0.012 * __import__("math").sin(time.time() * 1.3))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(col))
            p.drawEllipse(QPointF(cx, cy), r, r)


WIDGET_CLASSES = {
    "clock": ClockWidget, "weather": WeatherWidget, "tasks": TasksWidget, "notes": NotesWidget,
    "calendar": CalendarWidget, "rates": RatesWidget, "system": SystemWidget, "media": MediaWidget,
    "apps": AppsWidget, "history": HistoryWidget, "timer": TimerWidget, "pet": PetControlWidget,
    "orb": OrbWidget,
}


# ── the desk ────────────────────────────────────────────────────────────────────
class DeskView(QWidget):
    CELL_H = 132

    def __init__(self, shell, desk_id: int):
        super().__init__()
        self.shell = shell
        self.desk_id = desk_id
        self._edit = False
        self._cards: list[WidgetCard] = []
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        outer.addWidget(self._scroll)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(1000)
        self.rebuild()

    def _tick(self):
        if not self.isVisible():
            return
        for c in self._cards:
            try:
                c.refresh()
            except Exception:
                pass

    def set_edit(self, on: bool) -> None:
        self._edit = on
        for c in self._cards:
            c.set_edit(on)

    def rebuild(self) -> None:
        desk = desks.get_desk(self.desk_id) or {"widgets": []}
        inner = QWidget()
        inner.setStyleSheet("background:transparent;")
        grid = QGridLayout(inner)
        grid.setContentsMargins(0, 0, 8, 0)
        grid.setSpacing(12)
        for c in range(4):
            grid.setColumnStretch(c, 1)
        specs = desk["widgets"]
        places = desks.pack_layout([desks.parse_size(w.get("size", "2x1")) for w in specs])
        self._cards = []
        last_row = 0
        for i, (spec, (r, c, w, h)) in enumerate(zip(specs, places)):
            cls = WIDGET_CLASSES.get(spec["type"])
            if cls is None:
                continue
            card = cls(self.shell, spec["type"])
            card.set_edit(self._edit)
            card.move_left.connect(lambda i=i: self._act(desks.move_widget, i, -1))
            card.move_right.connect(lambda i=i: self._act(desks.move_widget, i, 1))
            card.resize_me.connect(lambda i=i: self._act(desks.cycle_size, i))
            card.remove_me.connect(lambda i=i: self._act(desks.remove_widget, i))
            grid.addWidget(card, r, c, h, w)
            self._cards.append(card)
            last_row = max(last_row, r + h)
        for r in range(last_row):
            grid.setRowMinimumHeight(r, self.CELL_H)
        grid.setRowStretch(last_row, 1)
        if not specs:
            hint = _lab("Стол пуст. Нажми карандаш сверху справа, затем «Добавить виджет».", 15, False, P.DIM, True)
            grid.addWidget(hint, 0, 0, 1, 4)
        self._scroll.setWidget(inner)

    def _act(self, fn, *args) -> None:
        fn(self.desk_id, *args)
        self.rebuild()


# ── dialogs (cards centred over the shell) ────────────────────────────────────
class _Dialog(QWidget):
    closed = pyqtSignal()
    W, H = 560, 520

    def __init__(self, parent):
        super().__init__(parent)
        self.setFixedSize(self.W, self.H)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"_Dialog{{background:{P.CARD};border:1px solid {P.CARD_LINE};border-radius:22px;}}"
                           f"QLabel{{background:transparent;color:{P.TEXT};}}"
                           f"QLineEdit{{background:#151a23;color:{P.TEXT};border:1px solid {P.CARD_LINE};"
                           f"border-radius:10px;padding:9px 12px;font-size:14px;}}"
                           f"QLineEdit:focus{{border:1px solid {P.ACCENT};}}"
                           f"QTextEdit{{background:#151a23;color:{P.TEXT};border:1px solid {P.CARD_LINE};"
                           f"border-radius:10px;padding:6px 10px;font-size:14px;}}"
                           f"QTextEdit:focus{{border:1px solid {P.ACCENT};}}"
                           f"QComboBox{{background:#232a37;color:{P.TEXT};border:1px solid {P.CARD_LINE};"
                           f"border-radius:10px;padding:6px 10px;font-size:13px;}}"
                           f"QComboBox QAbstractItemView{{background:#1b212c;color:{P.TEXT};"
                           f"selection-background-color:{P.ACCENT};border:1px solid {P.CARD_LINE};}}")
        self.lay = QVBoxLayout(self)
        self.lay.setContentsMargins(26, 22, 26, 20)
        self.lay.setSpacing(10)


class NewDeskDialog(_Dialog):
    created = pyqtSignal(str, str)
    H = 560

    def __init__(self, parent):
        super().__init__(parent)
        self._preset = "empty"
        self.lay.addWidget(_lab("Новый стол", 22, True))
        self.lay.addWidget(_lab("Своя страница с виджетами. Название и состав можно поменять потом.", 13, False, P.DIM, True))
        self._name = QLineEdit()
        self._name.setPlaceholderText("Название, например: Работа")
        self.lay.addWidget(self._name)
        self.lay.addWidget(_lab(f"С чего начать · {len(desks.PRESETS)} заготовок", 13, True, P.DIM))
        grid = QGridLayout()
        grid.setSpacing(8)
        self._tiles: dict[str, QPushButton] = {}
        for i, pr in enumerate(desks.PRESETS):
            b = QPushButton(f"{pr['name']}\n{pr['hint']}")
            b.setCheckable(True)
            b.setFixedHeight(62)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda _=False, k=pr["key"]: self._pick(k))
            grid.addWidget(b, i // 3, i % 3)
            self._tiles[pr["key"]] = b
        self.lay.addLayout(grid)
        self.lay.addStretch(1)
        row = QHBoxLayout()
        row.addStretch(1)
        cancel = _button("Отмена")
        cancel.clicked.connect(self.closed.emit)
        ok = _button("Создать стол", primary=True)
        ok.clicked.connect(self._ok)
        row.addWidget(cancel)
        row.addWidget(ok)
        self.lay.addLayout(row)
        self._pick("empty")

    def _pick(self, key: str) -> None:
        self._preset = key
        for k, b in self._tiles.items():
            on = k == key
            b.setChecked(on)
            b.setStyleSheet(
                f"QPushButton{{background:{'#243a66' if on else '#1b212c'};color:{P.TEXT};text-align:left;"
                f"border:1px solid {P.ACCENT if on else P.CARD_LINE};border-radius:12px;padding:6px 10px;font-size:12px;}}"
                f"QPushButton:hover{{background:#2b3342;}}")

    def _ok(self) -> None:
        name = self._name.text().strip()
        if not name:
            name = next((p["name"] for p in desks.PRESETS if p["key"] == self._preset), "Новый стол")
        self.created.emit(name, self._preset)


class AddWidgetDialog(_Dialog):
    chosen = pyqtSignal(str)
    H = 520

    def __init__(self, parent):
        super().__init__(parent)
        self.lay.addWidget(_lab("Добавить виджет", 22, True))
        grid = QGridLayout()
        grid.setSpacing(8)
        for i, (key, (title, _size, hint)) in enumerate(desks.WIDGETS.items()):
            b = QPushButton(f"{title}\n{hint}")
            b.setFixedHeight(56)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setStyleSheet(f"QPushButton{{background:#1b212c;color:{P.TEXT};text-align:left;"
                            f"border:1px solid {P.CARD_LINE};border-radius:12px;padding:6px 10px;font-size:12px;}}"
                            f"QPushButton:hover{{background:#243a66;border-color:{P.ACCENT};}}")
            b.clicked.connect(lambda _=False, k=key: self.chosen.emit(k))
            grid.addWidget(b, i // 2, i % 2)
        self.lay.addLayout(grid)
        self.lay.addStretch(1)
        row = QHBoxLayout()
        row.addStretch(1)
        close = _button("Закрыть")
        close.clicked.connect(self.closed.emit)
        row.addWidget(close)
        self.lay.addLayout(row)
