"""
core/widget_data.py — the data behind the widgets, free of any GUI code.

Weather comes from Open-Meteo and exchange rates from open.er-api.com: both are
free and need no key. Every network call takes an optional `opener` so tests
(and offline use) never touch the internet, and every call returns None instead
of raising when the network is down.
"""
from __future__ import annotations

import json
import ssl
import sys
import urllib.parse
import urllib.request

_WEATHER_CODES = {
    0: ("ясно", "☀"), 1: ("почти ясно", "🌤"), 2: ("переменная облачность", "⛅"), 3: ("пасмурно", "☁"),
    45: ("туман", "🌫"), 48: ("туман", "🌫"),
    51: ("морось", "🌦"), 53: ("морось", "🌦"), 55: ("сильная морось", "🌧"),
    61: ("дождь", "🌧"), 63: ("дождь", "🌧"), 65: ("сильный дождь", "🌧"),
    71: ("снег", "🌨"), 73: ("снег", "🌨"), 75: ("сильный снег", "❄"),
    80: ("ливень", "🌧"), 81: ("ливень", "🌧"), 82: ("сильный ливень", "⛈"),
    95: ("гроза", "⛈"), 96: ("гроза с градом", "⛈"), 99: ("гроза с градом", "⛈"),
}


def describe_weather(code: int) -> tuple[str, str]:
    return _WEATHER_CODES.get(int(code), ("погода", "🌡"))


def _ctx():
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()


def _get_json(url: str, opener=None, timeout: float = 8.0):
    try:
        if opener is not None:
            return json.loads(opener(url))
        with urllib.request.urlopen(url, context=_ctx(), timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception:
        return None


def fetch_weather(city: str, opener=None) -> dict | None:
    """-> {"city", "temp", "text", "icon"} or None."""
    city = (city or "").strip()
    if not city:
        return None
    geo = _get_json("https://geocoding-api.open-meteo.com/v1/search?count=1&language=ru&name="
                    + urllib.parse.quote(city), opener)
    try:
        hit = geo["results"][0]
        lat, lon, name = hit["latitude"], hit["longitude"], hit.get("name", city)
    except Exception:
        return None
    fc = _get_json(f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
                   f"&current=temperature_2m,weather_code", opener)
    try:
        cur = fc["current"]
        text, icon = describe_weather(cur["weather_code"])
        return {"city": name, "temp": round(float(cur["temperature_2m"])), "text": text, "icon": icon}
    except Exception:
        return None


def fetch_rates(opener=None) -> dict | None:
    """-> {"USD": rub_per_usd, "EUR": rub_per_eur} or None."""
    data = _get_json("https://open.er-api.com/v6/latest/USD", opener)
    try:
        rub = float(data["rates"]["RUB"])
        eur_per_usd = float(data["rates"]["EUR"])
        return {"USD": rub, "EUR": rub / eur_per_usd}
    except Exception:
        return None


def system_stats() -> dict:
    """-> {"cpu": %, "ram": %, "disk": %} (zeros if psutil is missing)."""
    try:
        import psutil
        root = "C:\\" if sys.platform == "win32" else "/"
        return {"cpu": psutil.cpu_percent(interval=None),
                "ram": psutil.virtual_memory().percent,
                "disk": psutil.disk_usage(root).percent}
    except Exception:
        return {"cpu": 0.0, "ram": 0.0, "disk": 0.0}


# ── media keys (work with any player: Spotify, browser, VLC …) ────────────────
_MEDIA_KEYS = {"play_pause": 0xB3, "next": 0xB0, "prev": 0xB1, "stop": 0xB2,
               "mute": 0xAD, "volume_down": 0xAE, "volume_up": 0xAF}


def press_media_key(name: str) -> bool:
    code = _MEDIA_KEYS.get(name)
    if code is None or sys.platform != "win32":
        return False
    try:
        import ctypes
        user32 = ctypes.windll.user32
        user32.keybd_event(code, 0, 0, 0)
        user32.keybd_event(code, 0, 2, 0)       # KEYEVENTF_KEYUP
        return True
    except Exception:
        return False


# ── away-from-keyboard lock ───────────────────────────────────────────────────
def idle_seconds() -> float:
    """Seconds since the last keyboard or mouse input (Windows; 0 elsewhere)."""
    if sys.platform != "win32":
        return 0.0
    try:
        import ctypes
        from ctypes import wintypes

        class LASTINPUTINFO(ctypes.Structure):
            _fields_ = [("cbSize", wintypes.UINT), ("dwTime", wintypes.DWORD)]

        info = LASTINPUTINFO()
        info.cbSize = ctypes.sizeof(LASTINPUTINFO)
        if not ctypes.windll.user32.GetLastInputInfo(ctypes.byref(info)):
            return 0.0
        return max(0.0, (ctypes.windll.kernel32.GetTickCount() - info.dwTime) / 1000.0)
    except Exception:
        return 0.0


def lock_workstation() -> bool:
    if sys.platform != "win32":
        return False
    try:
        import ctypes
        return bool(ctypes.windll.user32.LockWorkStation())
    except Exception:
        return False


class AwayLock:
    """Locks the PC once per idle period. Poll `check()` every few seconds."""

    def __init__(self, idle_fn=idle_seconds, lock_fn=lock_workstation):
        self._idle, self._lock = idle_fn, lock_fn
        self._locked_this_idle = False

    def check(self, enabled: bool, minutes: float) -> bool:
        if not enabled:
            self._locked_this_idle = False
            return False
        idle = self._idle()
        if idle < 5:                       # the user is back: re-arm
            self._locked_this_idle = False
            return False
        if idle >= minutes * 60 and not self._locked_this_idle:
            self._locked_this_idle = True
            self._lock()
            return True
        return False
