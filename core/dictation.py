"""
core/dictation.py — voice typing.

Say «начни диктовку»: from then on everything you say is typed into whatever window
has focus (instead of being sent to the AI), until you say «закончи диктовку».
While dictating you can say:

    запятая · точка · вопросительный знак · восклицательный знак · двоеточие · тире
    новая строка · новый абзац · удали слово

Sentences start with a capital letter after a full stop. Text is entered through the
clipboard, so Russian and any other language work in any program.
"""
from __future__ import annotations

import re
import threading

from core.custom_commands import norm

_ON = re.compile(r"^(?:начни|начать|включи|запусти|давай|включить)\s+(?:режим\s+)?диктовк\w*$")
_OFF = re.compile(r"^(?:закончи|закончить|останови|выключи|заверши|хватит|стоп|выключить|прекрати)\s+(?:режим\s+)?диктовк\w*$")

_PUNCT = {"запятая": ",", "точка": ".", "вопросительный знак": "?", "восклицательный знак": "!",
          "двоеточие": ":", "тире": "—", "многоточие": "…", "точка с запятой": ";"}
_KEYS = {"новая строка": ["enter"], "с новой строки": ["enter"], "новый абзац": ["enter", "enter"],
         "удали слово": ["ctrl+backspace"], "удали последнее слово": ["ctrl+backspace"]}
_SENTENCE_END = (".", "!", "?", "…")


class Dictation:
    def __init__(self):
        self.active = False
        self._cap = True            # capitalise the next word
        self._line_start = True     # nothing typed yet on this line
        self._lock = threading.Lock()

    def set_active(self, on: bool) -> None:
        with self._lock:
            self.active = bool(on)
            self._cap, self._line_start = True, True

    def handle(self, text: str) -> list[tuple[str, str]] | None:
        """-> list of ("say"|"type"|"key", value) to perform, or None when this
        phrase is not for dictation (so the normal pipeline handles it)."""
        n = norm(text)
        if not self.active:
            if _ON.match(n):
                self.set_active(True)
                return [("say", "Диктовка включена. Говори, я печатаю.")]
            return None
        if _OFF.match(n):
            self.set_active(False)
            return [("say", "Диктовка выключена.")]
        return self._ops(text)

    def handle_control(self, text: str) -> list[tuple[str, str]] | None:
        """Only «начни / закончи диктовку» — for text typed in the chat, which must never be
        typed into another window."""
        n = norm(text)
        if _ON.match(n):
            self.set_active(True)
            return [("say", "Диктовка включена. Говори, я печатаю.")]
        if self.active and _OFF.match(n):
            self.set_active(False)
            return [("say", "Диктовка выключена.")]
        return None

    # ── turning speech into typing ────────────────────────────────────────────
    def _ops(self, text: str) -> list[tuple[str, str]]:
        # Whisper's own punctuation is dropped: punctuation is only what you SAY.
        words = re.sub(r"[,.!?…]+", " ", text.strip()).split()
        lowered = [w.lower().replace("ё", "е") for w in words]
        ops: list[tuple[str, str]] = []
        buf = ""

        def flush() -> None:
            nonlocal buf
            if buf:
                ops.append(("type", buf))
                buf = ""

        i = 0
        while i < len(words):
            step = 0
            for size in (3, 2, 1):                        # longest spoken command first
                chunk = lowered[i:i + size]
                if len(chunk) < size:
                    continue
                phrase = " ".join(chunk)
                if phrase in _KEYS:
                    flush()
                    ops.extend(("key", k) for k in _KEYS[phrase])
                    if not phrase.startswith("удали"):
                        self._cap, self._line_start = True, True
                    step = size
                    break
                if phrase in _PUNCT:
                    mark = _PUNCT[phrase]
                    buf = (buf + " " + mark) if mark == "—" else (buf.rstrip() + mark)
                    self._cap = mark in _SENTENCE_END
                    self._line_start = False
                    step = size
                    break
            if step:
                i += step
                continue
            word = words[i]
            if self._cap:
                word = word[:1].upper() + word[1:]
                self._cap = False
            buf += word if self._line_start else " " + word
            self._line_start = False
            i += 1
        flush()
        return ops


STATE = Dictation()         # shared by the voice pipeline and the Home switch
