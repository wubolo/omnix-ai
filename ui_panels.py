"""
ui_panels.py — the bigger settings panels of the new interface.

    CommandsCard      your own commands (list, enable, edit, delete) + «New command»
    PacksCard         ready-made command packs, each with a switch
    CommandEditorDialog   name, phrases, actions, «create with AI»
    VoiceCard         engine picker (Windows / Piper / OpenAI / Silero), voice chips, OpenAI key
    InterfaceCard     theme colour, window transparency, animations, tray, live avatar
    PrefixCard        «Джарвис, …» prefix mode

They only use the shell's helpers (_card, _button, Toggle …), so the look stays in one place.
"""
from __future__ import annotations

import sys
import threading

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (QComboBox, QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton,
                             QScrollArea, QSlider, QTextEdit, QVBoxLayout, QWidget)

import ui_modern as K
import ui_widgets as W
from core import custom_commands as cc
from core.command_packs import PACKS
from memory.config_manager import get_ui_setting, get_voice, save_ui_setting, save_voice

P, _font, _card, _button, Toggle = K.P, K._font, K._card, K._button, K.Toggle
_lab = W._lab

def cc_needs_value(action_type) -> bool:
    return action_type in cc._NEEDS_VALUE


ACCENTS = ["#3b82f6", "#6366f1", "#8b5cf6", "#d946ef", "#22c55e", "#f97316", "#ec4899", "#06b6d4"]


def _row_label(text: str, sub: str = "") -> QVBoxLayout:
    col = QVBoxLayout()
    col.setSpacing(2)
    col.addWidget(_lab(text, 14, True))
    if sub:
        col.addWidget(_lab(sub, 12, False, P.DIM, True))
    return col


def _clear(layout) -> None:
    while layout.count():
        it = layout.takeAt(0)
        if it and it.widget():
            it.widget().deleteLater()


def _small_button(text: str, tip: str = "") -> QPushButton:
    b = QPushButton(text)
    b.setFixedSize(30, 30)
    b.setToolTip(tip)
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    b.setStyleSheet(f"QPushButton{{background:#232a37;color:{P.TEXT};border:1px solid {P.CARD_LINE};"
                    f"border-radius:9px;font-size:13px;}}QPushButton:hover{{background:{P.ACCENT};}}")
    return b


# ── command editor ─────────────────────────────────────────────────────────────
class CommandEditorDialog(W._Dialog):
    saved = pyqtSignal()
    _ai_done = pyqtSignal(object)
    _rec_done = pyqtSignal(object)
    W, H = 720, 700

    def __init__(self, parent, command: dict | None = None):
        super().__init__(parent)
        self._id = (command or {}).get("id")
        self._rows: list[tuple[QComboBox, QLineEdit, QWidget]] = []
        self._ai_done.connect(self._on_ai)
        self._rec_done.connect(self._on_recorded)
        self._recorder = None

        self.lay.addWidget(_lab("Редактировать команду" if command else "Новая команда", 22, True))
        top = QHBoxLayout()
        self._name = QLineEdit()
        self._name.setPlaceholderText("Название, например: Режим стрима")
        top.addWidget(self._name, 1)
        top.addWidget(_lab("Подтверждать", 13, False, P.DIM))
        self._confirm = Toggle()
        top.addWidget(self._confirm)
        self.lay.addLayout(top)

        cols = QHBoxLayout()
        left, right = QVBoxLayout(), QVBoxLayout()
        left.addWidget(_lab("Фразы для активации", 13, True, P.DIM))
        self._phrases = QTextEdit()
        self._phrases.setPlaceholderText("Каждая фраза с новой строки.\nДля числа: громкость на {n}")
        self._phrases.setFixedHeight(86)
        left.addWidget(self._phrases)
        right.addWidget(_lab("Необязательные слова", 13, True, P.DIM))
        self._optional = QTextEdit()
        self._optional.setPlaceholderText("Можно сказать вместе с командой,\nнапример: пожалуйста")
        self._optional.setFixedHeight(86)
        right.addWidget(self._optional)
        cols.addLayout(left, 1)
        cols.addLayout(right, 1)
        self.lay.addLayout(cols)

        head = QHBoxLayout()
        head.addWidget(_lab("Действия по порядку", 13, True, P.DIM))
        head.addStretch(1)
        add = _button("＋ Действие")
        add.clicked.connect(lambda: self._add_row())
        rec = _button("⏺ Запись действий")
        rec.clicked.connect(self._record)
        ai = _button("✦ Создать с помощью AI")
        ai.clicked.connect(self._toggle_ai)
        head.addWidget(add)
        head.addWidget(rec)
        head.addWidget(ai)
        self.lay.addLayout(head)

        self._ai_box = QWidget()
        al = QVBoxLayout(self._ai_box)
        al.setContentsMargins(0, 0, 0, 0)
        self._ai_text = QTextEdit()
        self._ai_text.setPlaceholderText("Опиши словами, что должна делать команда. "
                                         "Например: открой OBS, начни запись и убавь громкость до 20")
        self._ai_text.setFixedHeight(64)
        al.addWidget(self._ai_text)
        arow = QHBoxLayout()
        self._ai_status = _lab("", 12, False, P.DIM)
        self._ai_go = _button("Собрать", primary=True)
        self._ai_go.clicked.connect(self._run_ai)
        arow.addWidget(self._ai_status, 1)
        arow.addWidget(self._ai_go)
        al.addLayout(arow)
        self._ai_box.hide()
        self.lay.addWidget(self._ai_box)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        inner = QWidget()
        inner.setStyleSheet("background:transparent;")
        self._rows_lay = QVBoxLayout(inner)
        self._rows_lay.setContentsMargins(0, 0, 6, 0)
        self._rows_lay.setSpacing(6)
        self._rows_lay.addStretch(1)
        self._scroll.setWidget(inner)
        self.lay.addWidget(self._scroll, 1)

        self._err = _lab("", 12, False, P.RED, True)
        self.lay.addWidget(self._err)
        foot = QHBoxLayout()
        foot.addStretch(1)
        cancel = _button("Отмена")
        cancel.clicked.connect(self.closed.emit)
        save = _button("Сохранить", primary=True)
        save.clicked.connect(self._save)
        foot.addWidget(cancel)
        foot.addWidget(save)
        self.lay.addLayout(foot)

        if command:
            self._fill(command)
        else:
            self._add_row()

    # form <-> data -------------------------------------------------------------
    def _fill(self, c: dict) -> None:
        self._name.setText(c.get("name", ""))
        self._confirm.set_state(bool(c.get("confirm")))
        self._phrases.setPlainText("\n".join(c.get("phrases", [])))
        self._optional.setPlainText("\n".join(c.get("optional", [])))
        for r in list(self._rows):
            self._remove_row(r)
        for a in c.get("actions", []):
            self._add_row(a.get("type"), a.get("value", ""))
        if not self._rows:
            self._add_row()

    def _add_row(self, typ: str | None = None, value: str = "") -> None:
        row = QWidget()
        rl = QHBoxLayout(row)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(8)
        idx = _lab(str(len(self._rows) + 1), 13, True, P.FAINT)
        idx.setFixedWidth(18)
        combo = QComboBox()
        for t, (label, _hint) in cc.ACTION_TYPES.items():
            combo.addItem(label, t)
        combo.setMinimumWidth(240)
        val = QLineEdit()
        val.setText(value)

        def hint(_=None, c=combo, v=val):
            v.setPlaceholderText(cc.ACTION_TYPES.get(c.currentData(), ("", ""))[1] or "значение не нужно")

        combo.currentIndexChanged.connect(hint)
        if typ in cc.ACTION_TYPES:
            combo.setCurrentIndex(list(cc.ACTION_TYPES).index(typ))
        hint()
        x = _small_button("✕", "Убрать действие")
        rec = (combo, val, row)
        x.clicked.connect(lambda _=False, r=rec: self._remove_row(r))
        rl.addWidget(idx)
        rl.addWidget(combo)
        rl.addWidget(val, 1)
        rl.addWidget(x)
        self._rows_lay.insertWidget(self._rows_lay.count() - 1, row)
        self._rows.append(rec)

    def _remove_row(self, rec) -> None:
        if rec in self._rows:
            self._rows.remove(rec)
            rec[2].deleteLater()

    def _collect(self) -> dict:
        lines = lambda box: [ln.strip() for ln in box.toPlainText().splitlines() if ln.strip()]
        return {"id": self._id, "name": self._name.text(), "phrases": lines(self._phrases),
                "optional": lines(self._optional), "confirm": self._confirm.isChecked(),
                "actions": [{"type": c.currentData(), "value": v.text()} for c, v, _ in self._rows]}

    def _save(self) -> None:
        try:
            cc.save_command(self._collect())
        except ValueError as exc:
            self._err.setText(f"Не сохранено: {exc}")
            return
        self.saved.emit()
        self.closed.emit()

    # recording ---------------------------------------------------------------------
    def _record(self) -> None:
        from core import action_recorder as ar
        if not ar.available():
            self._err.setText("Для записи нужен пакет pynput: pip install pynput")
            return
        if self._recorder is not None:
            return
        try:
            self._recorder = ar.Recorder(lambda acts: self._rec_done.emit(acts))
            self._recorder.start()
        except Exception as exc:
            self._recorder = None
            self._err.setText(f"Не удалось начать запись: {exc}")
            return
        self._err.setText("Идёт запись: сделай нужные действия в других окнах и нажми F8.")
        try:
            self.shell._win.showMinimized()
        except Exception:
            pass

    def _on_recorded(self, actions) -> None:
        self._recorder = None
        try:
            self.shell._win.showNormal()
            self.shell._win.raise_()
        except Exception:
            pass
        for rec in list(self._rows):                       # drop untouched empty rows
            combo, val, _ = rec
            if cc_needs_value(combo.currentData()) and not val.text().strip():
                self._remove_row(rec)
        for a in actions or []:
            self._add_row(a["type"], a["value"])
        self._err.setText(f"Записано действий: {len(actions or [])}. Проверь список и сохрани."
                          if actions else "Ничего не записано.")

    # AI ----------------------------------------------------------------------------
    def _toggle_ai(self) -> None:
        self._ai_box.setVisible(not self._ai_box.isVisible())

    def _run_ai(self) -> None:
        desc = self._ai_text.toPlainText().strip()
        if not desc:
            self._ai_status.setText("Опиши команду словами.")
            return
        self._ai_go.setEnabled(False)
        self._ai_status.setText("Собираю…")

        def work():
            try:
                self._ai_done.emit(cc.generate_with_ai(desc))
            except Exception as exc:
                self._ai_done.emit(str(exc))
        threading.Thread(target=work, daemon=True, name="ai-command").start()

    def _on_ai(self, result) -> None:
        self._ai_go.setEnabled(True)
        if isinstance(result, dict):
            self._fill({**result, "id": self._id})
            self._ai_status.setText("Готово: проверь и сохрани.")
            self._ai_box.hide()
        else:
            self._ai_status.setText(f"Не получилось: {result}")


class CommandsCard(QFrame):
    def __init__(self, shell):
        super().__init__()
        self.shell = shell
        self.setObjectName("card")
        self._root = QVBoxLayout(self)
        self._root.setContentsMargins(22, 20, 22, 20)
        self._root.setSpacing(10)
        head = QHBoxLayout()
        head.addWidget(_lab("Мои команды", 18, True))
        head.addStretch(1)
        new = _button("＋ Новая команда", primary=True)
        new.clicked.connect(lambda: self.edit(None))
        head.addWidget(new)
        self._root.addLayout(head)
        self._list = QVBoxLayout()
        self._list.setSpacing(8)
        self._root.addLayout(self._list)
        self.reload()

    def edit(self, command: dict | None) -> None:
        dlg = CommandEditorDialog(self.shell, command)
        dlg.saved.connect(self.reload)
        self.shell.show_dialog(dlg)

    def reload(self) -> None:
        _clear(self._list)
        cmds = cc.user_commands()
        if not cmds:
            self._list.addWidget(_lab("Своих команд пока нет. Нажми «Новая команда»: "
                                      "можно собрать из действий или описать словами.", 13, False, P.DIM, True))
        for c in cmds:
            row = QHBoxLayout()
            row.addLayout(_row_label(c["name"], "«" + "», «".join(c["phrases"][:3]) + f"» · действий: {len(c['actions'])}"), 1)
            sw = Toggle()
            sw.set_state(bool(c.get("enabled", True)))
            sw.toggled.connect(lambda on, i=c["id"]: cc.set_command_enabled(i, on))
            edit = _small_button("✎", "Изменить")
            edit.clicked.connect(lambda _=False, cmd=c: self.edit(cmd))
            rm = _small_button("✕", "Удалить")
            rm.clicked.connect(lambda _=False, i=c["id"]: (cc.delete_command(i), self.reload()))
            for w in (sw, edit, rm):
                row.addWidget(w)
            holder = QWidget()
            holder.setLayout(row)
            row.setContentsMargins(0, 0, 0, 0)
            self._list.addWidget(holder)


class PacksCard(QFrame):
    def __init__(self, shell):
        super().__init__()
        self.setObjectName("card")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(22, 20, 22, 20)
        lay.setSpacing(10)
        total = sum(len(p["commands"]) for p in PACKS.values())
        lay.addWidget(_lab(f"Готовые наборы · {total} команд", 18, True))
        for pid, pack in PACKS.items():
            row = QHBoxLayout()
            examples = ", ".join(c["phrases"][0] for c in pack["commands"][:4])
            row.addLayout(_row_label(f"{pack['title']} · {len(pack['commands'])}",
                                     f"{pack['description']}. Например: {examples}"), 1)
            sw = Toggle()
            sw.set_state(cc.pack_enabled(pid))
            sw.toggled.connect(lambda on, p=pid: cc.set_pack_enabled(p, on))
            row.addWidget(sw)
            holder = QWidget()
            holder.setLayout(row)
            row.setContentsMargins(0, 0, 0, 0)
            lay.addWidget(holder)


# ── voice: engine + voice + OpenAI key ───────────────────────────────────────────────
class VoiceCard(QFrame):
    _voices_ready = pyqtSignal(list)

    VOICE_NAMES = {"jarvis": "jarvis · муж.", "deep": "deep · муж.", "aidar": "aidar · муж.",
                   "eugene": "eugene · муж.", "dmitri": "dmitri · муж.", "denis": "denis · муж.",
                   "xenia": "xenia · жен.", "baya": "baya · жен.", "kseniya": "kseniya · жен.",
                   "irina": "irina · жен."}

    def __init__(self, shell):
        super().__init__()
        from core import tts
        self.tts = tts
        self.shell = shell
        self.setObjectName("card")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(22, 20, 22, 20)
        lay.setSpacing(10)
        lay.addWidget(_lab("Синтез речи", 18, True))
        lay.addWidget(_lab("Чем ассистент говорит. Голос Windows работает без интернета и без установки.", 13, False, P.DIM, True))

        self._eng_btns: dict[str, QPushButton] = {}
        for key, (title, sub) in tts.ENGINES.items():
            if key == "windows" and sys.platform != "win32":
                continue
            b = QPushButton(f"{title}\n{sub}")
            b.setCheckable(True)
            b.setFixedHeight(58)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda _=False, k=key: self._pick_engine(k))
            lay.addWidget(b)
            self._eng_btns[key] = b

        self._key_row = QWidget()
        kl = QHBoxLayout(self._key_row)
        kl.setContentsMargins(0, 0, 0, 0)
        self._key = QLineEdit()
        self._key.setEchoMode(QLineEdit.EchoMode.Password)
        save = _button("Сохранить ключ")
        save.clicked.connect(self._save_key)
        kl.addWidget(self._key, 1)
        kl.addWidget(save)
        lay.addWidget(self._key_row)

        self._ref_row = QWidget()
        rl = QHBoxLayout(self._ref_row)
        rl.setContentsMargins(0, 0, 0, 0)
        self._ref = QLineEdit()
        self._ref.setPlaceholderText("ID голоса с fish.audio (можно оставить пустым)")
        self._ref.setText(str(get_ui_setting("fish_reference_id", "") or ""))
        rsave = _button("Сохранить ID")
        rsave.clicked.connect(self._save_ref)
        rl.addWidget(self._ref, 1)
        rl.addWidget(rsave)
        lay.addWidget(self._ref_row)

        self._status = _lab("", 12, False, P.DIM, True)
        lay.addWidget(self._status)
        lay.addWidget(_lab("Голос", 13, True, P.DIM))
        self._chips_box = QHBoxLayout()
        self._chips_box.setSpacing(8)
        lay.addLayout(self._chips_box)
        self._chips: dict[str, QPushButton] = {}
        self._voices_ready.connect(self._show_chips)
        self._refresh()

    # engines ---------------------------------------------------------------------------
    def _style_engines(self) -> None:
        cur = self.tts.detect_engine()
        for k, b in self._eng_btns.items():
            on = k == cur
            b.setChecked(on)
            b.setStyleSheet(
                f"QPushButton{{background:{'#243a66' if on else '#1b212c'};color:{P.TEXT};text-align:left;"
                f"border:1px solid {P.ACCENT if on else P.CARD_LINE};border-radius:12px;padding:6px 14px;font-size:13px;}}"
                f"QPushButton:hover{{background:#2b3342;}}")
        self._key_row.setVisible(cur in ("openai", "fish"))
        self._ref_row.setVisible(cur == "fish")
        if cur == "fish":
            self._key.setPlaceholderText("Ключ Fish Audio")
            self._key.setText(str(get_ui_setting("fish_api_key", "") or ""))
        elif cur == "openai":
            self._key.setPlaceholderText("Ключ OpenAI (sk-…)")
            self._key.setText(str(get_ui_setting("openai_api_key", "") or ""))

    def _pick_engine(self, key: str) -> None:
        save_ui_setting("tts_engine", key)
        self._notify()
        self._refresh()

    def _notify(self) -> None:
        cb = getattr(self.shell._win, "on_voice_change", None)
        if callable(cb):
            try:
                cb()
            except Exception as exc:
                self._status.setText(str(exc))

    def _save_key(self) -> None:
        name = "fish_api_key" if self.tts.detect_engine() == "fish" else "openai_api_key"
        save_ui_setting(name, self._key.text().strip())
        self._status.setText("Ключ сохранён.")
        self._notify()

    def _save_ref(self) -> None:
        save_ui_setting("fish_reference_id", self._ref.text().strip())
        self._status.setText("ID голоса сохранён.")
        self._notify()

    # voices -------------------------------------------------------------------------------
    def _refresh(self) -> None:
        self._style_engines()
        _clear(self._chips_box)
        self._chips = {}
        self._status.setText("Ищу голоса…" if self.tts.detect_engine() == "windows" else "")
        if self.tts.detect_engine() == "fish":
            self._show_chips([])
            return
        threading.Thread(target=lambda: self._voices_ready.emit(self.tts.available_voices()),
                         daemon=True, name="voices").start()

    def _current(self) -> str:
        eng = self.tts.detect_engine()
        key = self.tts.voice_setting_key(eng)
        if key:
            return str(get_ui_setting(key, "") or "")
        return get_voice()

    def _show_chips(self, voices: list) -> None:
        _clear(self._chips_box)
        self._chips = {}
        if self.tts.detect_engine() == "fish":
            self._status.setText("Голос задаётся ID модели с fish.audio. Без ID звучит голос по умолчанию.")
        elif not voices:
            self._status.setText("Голоса не найдены. Для Windows установи русский голос в параметрах речи.")
        elif self.tts.detect_engine() == "windows":
            self._status.setText("")
        for v in voices[:8]:
            b = QPushButton(self.VOICE_NAMES.get(v, v.replace("Microsoft ", "")))
            b.setCheckable(True)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setFixedHeight(34)
            b.setFont(_font(13, True))
            b.clicked.connect(lambda _=False, name=v: self._pick_voice(name))
            self._chips[v] = b
            self._chips_box.addWidget(b)
        self._chips_box.addStretch(1)
        self._style_chips()

    def _style_chips(self) -> None:
        cur = self._current() or (next(iter(self._chips), ""))
        for v, b in self._chips.items():
            on = v == cur
            b.setChecked(on)
            b.setStyleSheet(
                f"QPushButton{{background:{P.ACCENT if on else '#232a37'};color:{'white' if on else P.TEXT};"
                f"border:1px solid {P.ACCENT if on else P.CARD_LINE};border-radius:10px;padding:0 14px;}}"
                f"QPushButton:hover{{background:{P.ACCENT_HI if on else '#2b3342'};}}")

    def _pick_voice(self, name: str) -> None:
        key = self.tts.voice_setting_key(self.tts.detect_engine())
        if key:
            save_ui_setting(key, name)
        else:
            save_voice(name)
        self._style_chips()
        self._notify()


# ── interface ─────────────────────────────────────────────────────────────────────────────
class SpeechRecognitionCard(QFrame):
    """Choose local GigaAM, fast Groq transcription, or Gemini Live."""

    def __init__(self, shell):
        super().__init__()
        self.setObjectName("card")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(22, 20, 22, 20)
        lay.setSpacing(10)
        lay.addWidget(_lab("Распознавание речи", 18, True))
        lay.addWidget(_lab("GigaAM распознаёт русскую речь локально. Первый запуск загрузит модель; Groq работает через интернет, Gemini распознаёт поток напрямую.", 13, False, P.DIM, True))
        self._engine = QComboBox()
        self._engine.addItem("GigaAM-v3 — локально, без отправки аудио", "gigaam")
        self._engine.addItem("Groq Whisper — быстрее, нужен интернет", "groq")
        self._engine.addItem("Gemini Live — встроенное распознавание", "gemini")
        current = str(get_ui_setting("stt_engine", "groq") or "groq")
        idx = self._engine.findData(current)
        self._engine.setCurrentIndex(idx if idx >= 0 else self._engine.findData("groq"))
        lay.addWidget(self._engine)
        row = QHBoxLayout()
        self._key = QLineEdit()
        self._key.setEchoMode(QLineEdit.EchoMode.Password)
        self._key.setPlaceholderText("Ключ Groq Cloud (только для режима Groq)")
        self._key.setText(str(get_ui_setting("groq_api_key", "") or ""))
        save = _button("Сохранить")
        save.clicked.connect(self._save)
        row.addWidget(self._key, 1)
        row.addWidget(save)
        lay.addLayout(row)
        self._status = _lab("", 12, False, P.DIM, True)
        lay.addWidget(self._status)

    def _save(self) -> None:
        save_ui_setting("groq_api_key", self._key.text().strip())
        save_ui_setting("stt_engine", str(self._engine.currentData() or "groq"))
        self._status.setText("Настройки сохранены. Для смены движка распознавания перезапусти приложение.")


class InterfaceCard(QFrame):
    def __init__(self, shell):
        super().__init__()
        self.shell = shell
        self.setObjectName("card")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(22, 20, 22, 20)
        lay.setSpacing(12)
        lay.addWidget(_lab("Интерфейс", 18, True))

        row = QHBoxLayout()
        row.addWidget(_lab("Цвет темы", 14, False, P.DIM))
        row.addStretch(1)
        cur = str(get_ui_setting("ui_accent", ACCENTS[0]) or ACCENTS[0]).lower()
        for col in ACCENTS:
            b = QPushButton()
            b.setFixedSize(26, 26)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            sel = col.lower() == cur
            b.setStyleSheet(f"QPushButton{{background:{col};border-radius:13px;"
                            f"border:{'3px solid white' if sel else '2px solid #2a3140'};}}")
            b.clicked.connect(lambda _=False, c=col: shell._win.apply_theme(c))
            row.addWidget(b)
        lay.addLayout(row)

        orow = QHBoxLayout()
        orow.addWidget(_lab("Прозрачность окна", 14, False, P.DIM))
        self._op = QSlider(Qt.Orientation.Horizontal)
        self._op.setRange(40, 100)
        try:
            self._op.setValue(int(get_ui_setting("window_opacity", 100)))
        except (TypeError, ValueError):
            self._op.setValue(100)
        self._op_lbl = _lab(f"{self._op.value()}%", 14)
        self._op_lbl.setFixedWidth(46)
        self._op.valueChanged.connect(self._on_opacity)
        orow.addSpacing(18)
        orow.addWidget(self._op, 1)
        orow.addWidget(self._op_lbl)
        lay.addLayout(orow)

        self._switch(lay, "Анимации", "avatar_animation", True, lambda on: shell.update())
        self._switch(lay, "Сворачивать в трей при закрытии", "minimize_to_tray", False,
                     lambda on: shell._win.set_tray(on))
        self._switch(lay, "Живой аватар на рабочем столе", "orb_overlay", False,
                     lambda on: shell.set_orb_overlay(on))

    def _switch(self, lay, text, key, default, after) -> None:
        r = QHBoxLayout()
        r.addWidget(_lab(text, 14, False, P.DIM))
        r.addStretch(1)
        sw = Toggle()
        sw.set_state(bool(get_ui_setting(key, default)))

        def on(v, k=key):
            save_ui_setting(k, bool(v))
            after(bool(v))
        sw.toggled.connect(on)
        r.addWidget(sw)
        lay.addLayout(r)

    def _on_opacity(self, v: int) -> None:
        self._op_lbl.setText(f"{v}%")
        save_ui_setting("window_opacity", int(v))
        self.shell._win.setWindowOpacity(v / 100.0)


class PrefixCard(QFrame):
    def __init__(self, shell):
        super().__init__()
        self.shell = shell
        self.setObjectName("card")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(22, 20, 22, 20)
        lay.setSpacing(10)
        row = QHBoxLayout()
        row.addLayout(_row_label("Режим префикса",
                                 "Ассистент слушает только фразы, которые начинаются с его имени: "
                                 "«Джарвис, включи музыку». Остальное он игнорирует."), 1)
        self._sw = Toggle()
        self._sw.set_state(bool(get_ui_setting("prefix_mode", False)))
        self._sw.toggled.connect(shell._on_prefix)
        shell._prefix_cards.append(self._sw)
        row.addWidget(self._sw)
        lay.addLayout(row)
        self._words = QLineEdit()
        words = get_ui_setting("prefix_words", None) or cc.DEFAULT_PREFIX
        self._words.setText(", ".join(words))
        self._words.setPlaceholderText("Слова через запятую: джарвис, ассистент")
        self._words.editingFinished.connect(self._save_words)
        lay.addWidget(self._words)

    def _save_words(self) -> None:
        words = [w.strip() for w in self._words.text().split(",") if w.strip()]
        save_ui_setting("prefix_words", words or cc.DEFAULT_PREFIX)
