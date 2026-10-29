"""
core/action_recorder.py — «Запись действий» for the command editor.

Press record, minimise the app, do the thing once (shortcuts, typing, clicks) and press
F8: what you did becomes a list of actions. The decisions live in RecorderModel and know
nothing about the keyboard hook, so they are testable; Recorder connects them to pynput.

    ctrl+shift+s           -> Keys.Press  ctrl+shift+s
    typing «привет»        -> Keys.Type   привет
    a click at (960, 540)  -> Mouse.ClickLeft  960,540
    a pause of 2 seconds   -> Wait  2
"""
from __future__ import annotations

import threading
import time

from core.custom_commands import _KEY_NAMES

MODS = ("ctrl", "alt", "shift", "win")
STOP_KEY = "f8"

_SPECIAL = {"ctrl_l": "ctrl", "ctrl_r": "ctrl", "ctrl": "ctrl", "alt_l": "alt", "alt_r": "alt",
            "alt_gr": "alt", "alt": "alt", "shift_l": "shift", "shift_r": "shift", "shift": "shift",
            "cmd": "win", "cmd_l": "win", "cmd_r": "win", "page_up": "pageup", "page_down": "pagedown",
            "print_screen": "printscreen", "caps_lock": "capslock", "media_play_pause": "playpause",
            "media_next": "nexttrack", "media_previous": "prevtrack", "media_volume_up": "volumeup",
            "media_volume_down": "volumedown", "media_volume_mute": "volumemute"}


def key_name(key, ctrl_held: bool = False) -> str | None:
    """pynput key object -> the name used in Keys.Press, or None if it cannot be replayed."""
    name = getattr(key, "name", None)
    if name:
        name = _SPECIAL.get(name, name)
        return name if (name in _KEY_NAMES or name == "space") else None
    ch = getattr(key, "char", None)
    if ch and len(ch) == 1:
        if ord(ch) < 32:                                   # ctrl+s arrives as \x13 on Windows
            return chr(ord(ch) + 96) if ctrl_held and ord(ch) <= 26 else None
        return ch
    vk = getattr(key, "vk", None)
    if isinstance(vk, int) and (65 <= vk <= 90):
        return chr(vk + 32)
    if isinstance(vk, int) and (48 <= vk <= 57):
        return chr(vk)
    return None


class RecorderModel:
    def __init__(self, clock=time.monotonic, gap: float = 0.7, max_wait: float = 10.0):
        self._clock, self._gap, self._max_wait = clock, gap, max_wait
        self._actions: list[dict] = []
        self._mods: set[str] = set()
        self._text = ""
        self._last: float | None = None

    @property
    def mods(self) -> set[str]:
        return set(self._mods)

    def _flush(self) -> None:
        if self._text:
            self._actions.append({"type": "Keys.Type", "value": self._text})
            self._text = ""

    def _before_event(self) -> None:
        now = self._clock()
        if self._last is not None and now - self._last >= self._gap:
            self._flush()
            wait = min(self._max_wait, round(now - self._last, 1))
            if wait > 0:
                self._actions.append({"type": "Wait", "value": str(wait)})
        self._last = now

    def _combo(self, key: str) -> str:
        return "+".join([m for m in MODS if m in self._mods] + [key])

    def key_down(self, name: str) -> None:
        if name in MODS:
            self._mods.add(name)
            return
        if not (name in _KEY_NAMES or len(name) == 1 or name == "space"):
            return
        self._before_event()
        printable = len(name) == 1 or name == "space"
        if printable and not (self._mods & {"ctrl", "alt", "win"}):
            self._text += " " if name == "space" else name
            return
        self._flush()
        self._actions.append({"type": "Keys.Press", "value": self._combo(name)})

    def key_up(self, name: str) -> None:
        self._mods.discard(name)

    def click(self, x: int, y: int, left: bool = True, pressed: bool = True) -> None:
        if not (left and pressed):
            return
        self._before_event()
        self._flush()
        self._actions.append({"type": "Mouse.ClickLeft", "value": f"{int(x)},{int(y)}"})

    def finish(self) -> list[dict]:
        self._flush()
        acts = list(self._actions)
        while acts and acts[-1]["type"] == "Wait":
            acts.pop()
        return acts


def available() -> bool:
    try:
        import pynput  # noqa: F401
        return True
    except Exception:
        return False


class Recorder:
    """Global keyboard + mouse hook. F8 stops and hands the actions to `on_done`."""

    def __init__(self, on_done):
        self.model = RecorderModel()
        self._on_done = on_done
        self._kl = self._ml = None
        self._done = False
        self._lock = threading.Lock()

    def start(self) -> None:
        from pynput import keyboard, mouse

        def press(key):
            name = key_name(key, "ctrl" in self.model.mods)
            if name == STOP_KEY:
                threading.Thread(target=self.stop, daemon=True).start()
            elif name:
                self.model.key_down(name)

        def release(key):
            name = key_name(key, "ctrl" in self.model.mods)
            if name:
                self.model.key_up(name)

        def click(x, y, button, pressed):
            self.model.click(x, y, button == mouse.Button.left, pressed)

        self._kl = keyboard.Listener(on_press=press, on_release=release)
        self._ml = mouse.Listener(on_click=click)
        self._kl.start()
        self._ml.start()

    def stop(self) -> None:
        with self._lock:
            if self._done:
                return
            self._done = True
        for lst in (self._kl, self._ml):
            try:
                if lst is not None:
                    lst.stop()
            except Exception:
                pass
        self._on_done(self.model.finish())
