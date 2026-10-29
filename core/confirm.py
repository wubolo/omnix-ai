"""
core/confirm.py — a confirmation the model cannot forge.

THE PROBLEM WITH THE OLD GATE
    computer_settings guarded shutdown and restart like this:

        confirmed = str(params.get("confirmed", "")).lower()
        if confirmed not in ("yes", "true", "1", "confirm"):
            return "Please confirm by calling again with confirmed=yes."

    `confirmed` is a tool parameter, which means the *model* writes it. Nothing
    stops it from sending confirmed=yes on the first call, and nothing checks
    that a human was ever involved. It is a convention, not a gate — and its
    coverage was two actions, so deleting files and switching off the WiFi the
    assistant is talking over went through with no gate at all.

THE DESIGN HERE
    The confirmation token is issued by the *interface*, never by the model:

      1. An action calls `request(...)` with a callable that does the real work.
      2. This module hands the UI a banner with CONFIRM / CANCEL and returns
         IMMEDIATELY with a sentence for the model to say out loud.
      3. If — and only if — the user presses CONFIRM, the UI calls `resolve()`,
         which runs the stored callable off the Qt thread.

    Nothing blocks. The model keeps talking while the banner is up, so this
    costs no latency at all; in fact it is cheaper than the old gate, which
    burned two tool round trips (reject, then re-call) on every shutdown.

WHAT BELONGS HERE AND WHAT DOES NOT
    Only genuinely irreversible things. Anything that can be reversed should be
    done at once and pushed onto core/undo.py instead — undo is faster than a
    question, and an assistant that asks before every action is one nobody uses.
"""

from __future__ import annotations

import os
import re
import sys
import threading
import time
from dataclasses import dataclass
from typing import Callable, Optional

# A pending confirmation is abandoned after this long. Chosen to outlast a
# normal "hang on, let me look at the screen" pause without leaving a live
# shutdown button sitting on the HUD for the rest of the day.
TIMEOUT_SECONDS = 90.0


@dataclass
class _Pending:
    key:     str
    title:   str
    detail:  str
    run:     Callable[[], str]
    at:      float
    voice:   bool = False   # a full-screen app is in front: the answer may be spoken


_pending: Optional[_Pending] = None
_lock = threading.Lock()

# Set once at startup by main.py. Signature: (title, detail) -> None for show,
# and () -> None for hide. Both are marshalled onto the Qt thread by the UI.
_show_cb: Optional[Callable[[str, str], None]] = None
_hide_cb: Optional[Callable[[], None]] = None
_log_cb:  Optional[Callable[[str], None]] = None


def bind(show, hide, log=None) -> None:
    """Wire this module to the HUD. Called once from main.py at startup."""
    global _show_cb, _hide_cb, _log_cb
    _show_cb, _hide_cb, _log_cb = show, hide, log


def _log(msg: str) -> None:
    if _log_cb:
        try:
            _log_cb(msg)
        except Exception:
            pass


def request(key: str, title: str, detail: str, run: Callable[[], str]) -> str:
    """Park an irreversible action behind the on-screen gate.

    Returns the sentence the tool should hand back to the model — phrased as an
    instruction so the assistant asks the user out loud in their own language,
    rather than reading an English string verbatim."""
    global _pending

    if _show_cb is None:
        # No interface bound (headless, or a very early call). Refuse rather
        # than silently performing something irreversible.
        return (f"I cannot confirm '{title}' right now because the interface is "
                f"not available, so I have not done it.")

    voice = foreground_is_fullscreen()
    with _lock:
        _pending = _Pending(key=key, title=title, detail=detail,
                            run=run, at=time.monotonic(), voice=voice)

    try:
        _show_cb(title, detail)
    except Exception as e:
        with _lock:
            _pending = None
        return f"Could not ask for confirmation: {e}. Nothing was done."

    _log(f"SYS: Awaiting confirmation — {title}")
    if voice:
        # A game is covering the screen, so the HUD banner is probably invisible.
        # The answer can then be spoken: core/confirm.try_voice_answer() hears it
        # from the user's own microphone, never from the model.
        return (
            f"[CONFIRMATION_PENDING] A full-screen app is in front, so the on-screen "
            f"confirmation for '{title}' may be hidden. Say ONE short sentence in the "
            f"user's own language asking them to say \"да\" to confirm or \"отмена\" "
            f"to cancel. Do not claim it is done."
        )
    return (
        f"[CONFIRMATION_PENDING] I have put a confirmation on screen for: {title}. "
        f"Say ONE short sentence in the user's own language telling them you need "
        f"them to confirm it on the HUD before you do it. Do not claim it is done."
    )


def resolve(accepted: bool) -> None:
    """Called by the UI when the user presses CONFIRM or CANCEL.

    Runs the stored callable on a worker thread — this is invoked from the Qt
    thread, and shutting the machine down from inside a button handler would
    freeze the interface on its way out."""
    global _pending

    with _lock:
        p, _pending = _pending, None

    if _hide_cb:
        try:
            _hide_cb()
        except Exception:
            pass

    if p is None:
        return

    if time.monotonic() - p.at > TIMEOUT_SECONDS:
        _log(f"SYS: Confirmation expired — {p.title}")
        return

    if not accepted:
        _log(f"SYS: Cancelled — {p.title}")
        return

    def _worker():
        try:
            result = p.run() or "Done."
            _log(f"SYS: Confirmed — {p.title}. {result}")
        except Exception as e:
            _log(f"ERR: {p.title} failed — {e}")

    threading.Thread(target=_worker, daemon=True,
                     name=f"confirm-{p.key}").start()


def pending_title() -> str:
    """'' when nothing is waiting. Lets an action avoid stacking two banners."""
    with _lock:
        if _pending is None:
            return ""
        if time.monotonic() - _pending.at > TIMEOUT_SECONDS:
            return ""
        return _pending.title


# ── game-safe confirmation ────────────────────────────────────────────────────
#
# A confirmation banner drawn over a full-screen game either never shows or
# yanks the player out of the game. So when something full-screen is in front,
# the same gate can be answered by voice instead. The security property is
# unchanged: the answer comes from the user's microphone through Whisper, and
# the model has no way to produce it.

def foreground_is_fullscreen() -> bool:
    """True when another program's window covers its whole monitor (a game,
    a video player). Always False off Windows and for this app's own windows."""
    if sys.platform != "win32":
        return False
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return False

        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value == os.getpid():
            return False

        cls = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(hwnd, cls, 256)
        if cls.value in ("Progman", "WorkerW", "Shell_TrayWnd", "Shell_SecondaryTrayWnd"):
            return False

        class _MONITORINFO(ctypes.Structure):
            _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT),
                        ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD)]

        rect = wintypes.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rect))
        mon = user32.MonitorFromWindow(hwnd, 2)          # MONITOR_DEFAULTTONEAREST
        info = _MONITORINFO()
        info.cbSize = ctypes.sizeof(_MONITORINFO)
        if not user32.GetMonitorInfoW(mon, ctypes.byref(info)):
            return False
        m = info.rcMonitor
        return (rect.left <= m.left and rect.top <= m.top
                and rect.right >= m.right and rect.bottom >= m.bottom)
    except Exception:
        return False


_YES = {"да", "подтверждаю", "подтверди", "подтвердить", "давай", "делай", "выполняй",
        "ага", "конечно", "yes", "confirm", "ok", "okay", "yeah"}
_NO = {"нет", "отмена", "отмени", "отменить", "стоп", "не", "надо", "нужно",
       "cancel", "no", "stop", "nope"}
_FILLER = {"пожалуйста", "джарвис", "please"}


def _parse_answer(text: str) -> Optional[bool]:
    words = re.sub(r"[^\w\s]", " ", (text or "").lower().replace("ё", "е")).split()
    words = [w for w in words if w not in _FILLER]
    if not words or len(words) > 3:
        return None
    yes = any(w in _YES for w in words)
    no = any(w in _NO for w in words)
    if yes == no:                    # neither, or "да нет" — not an answer
        return None
    if no and not all(w in _NO for w in words):
        return None
    if yes and not all(w in _YES for w in words):
        return None
    return yes


def voice_pending() -> bool:
    """True while a confirmation is waiting that may be answered by voice."""
    with _lock:
        return bool(_pending and _pending.voice
                    and time.monotonic() - _pending.at <= TIMEOUT_SECONDS)


def try_voice_answer(text: str) -> Optional[bool]:
    """If a voice-answerable confirmation is waiting and `text` is a clear
    yes/no, resolve it and return the answer. Otherwise None and nothing changes."""
    with _lock:
        p = _pending
        if (p is None or not p.voice
                or time.monotonic() - p.at > TIMEOUT_SECONDS
                or time.monotonic() - p.at < 1.0):    # not our own question echoing back
            return None
    answer = _parse_answer(text)
    if answer is None:
        return None
    resolve(answer)
    return answer
