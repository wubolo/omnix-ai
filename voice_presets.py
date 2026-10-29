"""Кнопки выбора голоса Fish Audio: JARVIS / MiSide / Рик.

Подключение (ui_panels.py, VoiceCard или страница настроек в ui_modern.py):
    from voice_presets import FishVoicePresets
    layout.addWidget(FishVoicePresets(shell))
"""
import os

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

from memory.config_manager import get_ui_setting, save_ui_setting

# Never commit provider credentials. Set FISH_AUDIO_API_KEY in the environment
# to enable one-click key entry, or enter a personal key in the Voice settings.
FISH_BUILTIN_API_KEY = os.environ.get("FISH_AUDIO_API_KEY", "").strip()

VOICES = {
    "JARVIS": "b091202702664f49833895c62115ec10",
    "MiSide": "6dc11f3f67a543f6ad4537a4a347e224",
    "Рик": "eba91828dae94a99a2f830de4913237d",
}


class FishVoicePresets(QFrame):
    def __init__(self, shell=None, parent=None):
        super().__init__(parent)
        self.shell = shell
        self.setObjectName("glassCard")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 16, 18, 16)
        lay.setSpacing(10)

        title = QLabel("Голос (Fish Audio)")
        title.setObjectName("cardTitle")
        lay.addWidget(title)

        row = QHBoxLayout()
        row.setSpacing(8)
        self._btns = {}
        for name, ref in VOICES.items():
            b = QPushButton(name)
            b.setCheckable(True)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setFixedHeight(38)
            b.clicked.connect(lambda _=False, n=name: self._pick(n))
            row.addWidget(b)
            self._btns[name] = b
        row.addStretch(1)
        lay.addLayout(row)

        self.builtin = QPushButton("Использовать ключ из окружения")
        self.builtin.setCursor(Qt.CursorShape.PointingHandCursor)
        self.builtin.clicked.connect(self._use_builtin_key)
        lay.addWidget(self.builtin, 0, Qt.AlignmentFlag.AlignLeft)

        self.status = QLabel("")
        self.status.setObjectName("dim")
        lay.addWidget(self.status)
        self._sync()

    def _use_builtin_key(self):
        if not FISH_BUILTIN_API_KEY:
            self.status.setText("Ключ не задан. Введите свой ключ Fish Audio в настройках голоса.")
            return
        save_ui_setting("fish_api_key", FISH_BUILTIN_API_KEY)
        save_ui_setting("tts_engine", "fish")
        if not get_ui_setting("fish_reference_id", ""):
            save_ui_setting("fish_reference_id", VOICES["JARVIS"])
        self._sync()
        if self.shell is not None:
            from PyQt6.QtWidgets import QLineEdit
            for field in self.shell.findChildren(QLineEdit):
                placeholder = field.placeholderText()
                if placeholder == "Ключ Fish Audio":
                    field.setText(FISH_BUILTIN_API_KEY)
                elif placeholder.startswith("ID голоса"):
                    field.setText(str(get_ui_setting("fish_reference_id", "") or ""))
        self.status.setText("Ключ Fish Audio загружен из окружения.")
        win = getattr(self.shell, "_win", None)
        callback = getattr(win, "on_voice_change", None)
        if callable(callback):
            try:
                callback()
            except Exception as exc:
                self.status.setText(f"Ключ сохранён, но голос применить не удалось: {exc}")

    def _sync(self):
        cur = str(get_ui_setting("fish_reference_id", "") or "")
        for name, b in self._btns.items():
            b.setChecked(VOICES[name] == cur)

    def _pick(self, name):
        save_ui_setting("tts_engine", "fish")
        save_ui_setting("fish_reference_id", VOICES[name])
        self._sync()
        has_key = bool(str(get_ui_setting("fish_api_key", "") or "").strip())
        self.status.setText(
            f"Голос: {name}." if has_key
            else f"Голос: {name}. Осталось вставить ключ Fish Audio выше."
        )
        win = getattr(self.shell, "_win", None)
        cb = getattr(win, "on_voice_change", None)
        if callable(cb):
            try:
                cb()
            except Exception as e:  # не роняем интерфейс
                self.status.setText(f"Не удалось применить голос: {e}")
