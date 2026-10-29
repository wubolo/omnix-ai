"""
core/custom_commands.py — your own voice commands, plus ready-made packs.

A command is: a name, one or more activation phrases, optional filler phrases, a
"confirm first" flag and a list of actions that run in order:

    Launch.File        open a program, file or app by name        Steam | C:\\tools\\a.exe
    Web.Open           open a web address                          https://youtube.com
    Keys.Press         press a key combination                     ctrl+shift+s
    Keys.Type          type text into the focused window           Привет!
    Mouse.ClickLeft    click at a screen position                  960,540
    System.VolumeSet   master volume 0-100                         35
    System.VolumeChange  louder / quieter by N                      10  or  -10
    System.Mute        mute / unmute
    Media.PlayPause | Media.Next | Media.Prev
    System.Lock | System.Sleep | System.Shutdown | System.Restart | System.CancelShutdown
    Wait               pause, seconds                              1.5

A phrase may contain {n}: "громкость на {n}" hears "громкость на пятьдесят" and
passes 50 into any action whose value contains {n}.

Everything stored in data/commands.json (your commands + which packs are on).
Backends (keyboard, mouse, volume …) are injectable, so the logic is testable
without a desktop.
"""
from __future__ import annotations

import difflib
import json
import os
import re
import sys
import threading
import time
import uuid
from pathlib import Path

_BASE = (Path(sys.executable).parent if getattr(sys, "frozen", False)
         else Path(__file__).resolve().parent.parent)
COMMANDS_FILE = _BASE / "data" / "commands.json"
_LOCK = threading.RLock()

# type -> (label for the editor, hint for the value field)
ACTION_TYPES: dict[str, tuple[str, str]] = {
    "Launch.File":         ("Запустить программу или файл", "Steam  или  C:\\Tools\\app.exe"),
    "Web.Open":            ("Открыть сайт", "https://youtube.com"),
    "Keys.Press":          ("Нажать клавиши", "ctrl+shift+s"),
    "Keys.Type":           ("Напечатать текст", "Текст, который нужно ввести"),
    "Mouse.ClickLeft":     ("Клик мышью", "960,540"),
    "System.VolumeSet":    ("Громкость (0–100)", "35"),
    "System.VolumeChange": ("Громче / тише на", "10  или  -10"),
    "System.Mute":         ("Включить / выключить звук", ""),
    "Media.PlayPause":     ("Плеер: пауза / играть", ""),
    "Media.Next":          ("Плеер: следующий трек", ""),
    "Media.Prev":          ("Плеер: предыдущий трек", ""),
    "System.Lock":         ("Заблокировать компьютер", ""),
    "System.Sleep":        ("Спящий режим", ""),
    "System.Shutdown":     ("Выключить компьютер (через 30 с)", ""),
    "System.Restart":      ("Перезагрузить (через 30 с)", ""),
    "System.CancelShutdown": ("Отменить выключение", ""),
    "Wait":                ("Пауза, секунд", "1"),
}
_NEEDS_VALUE = {"Launch.File", "Web.Open", "Keys.Press", "Keys.Type", "Mouse.ClickLeft",
                "System.VolumeSet", "System.VolumeChange", "Wait"}

_KEY_NAMES = {"ctrl", "alt", "shift", "win", "enter", "esc", "tab", "space", "backspace", "delete",
              "up", "down", "left", "right", "home", "end", "pageup", "pagedown", "printscreen",
              "insert", "capslock", "volumeup", "volumedown", "volumemute", "playpause",
              "nexttrack", "prevtrack"} | {f"f{i}" for i in range(1, 25)}
PH = "xxnumxx"                      # stands in for {n} while a phrase is normalised

# ── numbers ────────────────────────────────────────────────────────────────────
_UNITS = {"ноль": 0, "один": 1, "одна": 1, "два": 2, "две": 2, "три": 3, "четыре": 4, "пять": 5,
          "шесть": 6, "семь": 7, "восемь": 8, "девять": 9, "десять": 10, "одиннадцать": 11,
          "двенадцать": 12, "тринадцать": 13, "четырнадцать": 14, "пятнадцать": 15,
          "шестнадцать": 16, "семнадцать": 17, "восемнадцать": 18, "девятнадцать": 19}
_TENS = {"двадцать": 20, "тридцать": 30, "сорок": 40, "пятьдесят": 50, "шестьдесят": 60,
         "семьдесят": 70, "восемьдесят": 80, "девяносто": 90}
_HUNDREDS = {"сто": 100}


def parse_number_ru(text: str) -> int | None:
    """'50' | 'пятьдесят' | 'двадцать пять' | 'сто' -> int, else None."""
    t = (text or "").strip().lower().replace("ё", "е").replace("%", " ").replace("процентов", " ")
    t = t.replace("процента", " ").replace("процент", " ")
    words = t.split()
    if not words:
        return None
    if len(words) == 1 and words[0].isdigit():
        return int(words[0])
    total = 0
    for w in words:
        if w in _HUNDREDS:
            total += _HUNDREDS[w]
        elif w in _TENS:
            total += _TENS[w]
        elif w in _UNITS:
            total += _UNITS[w]
        else:
            return None
    return total


def norm(text: str) -> str:
    t = (text or "").lower().replace("ё", "е")
    return " ".join(re.sub(r"[^0-9a-zа-я ]+", " ", t).split())


# ── validation ─────────────────────────────────────────────────────────────────
def validate_action(action: dict) -> str | None:
    """None if the action is fine, else a short reason (Russian, for the editor)."""
    typ, val = action.get("type"), str(action.get("value", "")).strip()
    if typ not in ACTION_TYPES:
        return f"неизвестное действие «{typ}»"
    if typ in _NEEDS_VALUE and not val:
        return "не заполнено значение"
    templ = "{n}" in val
    if typ == "Keys.Press":
        keys = [k.strip().lower() for k in val.split("+") if k.strip()]
        bad = [k for k in keys if not (k in _KEY_NAMES or len(k) == 1)]
        if not keys or bad:
            return "клавиши: " + (", ".join(bad) if bad else "пусто") + " не распознаны"
    elif typ == "Mouse.ClickLeft":
        m = re.fullmatch(r"\s*(\d{1,5})\s*[,; ]\s*(\d{1,5})\s*", val)
        if not m:
            return "нужны координаты: 960,540"
    elif typ == "System.VolumeSet":
        if not templ and not (val.isdigit() and 0 <= int(val) <= 100):
            return "громкость — число от 0 до 100"
    elif typ == "System.VolumeChange":
        if not templ and not re.fullmatch(r"[+-]?\d{1,3}", val):
            return "нужно число, например 10 или -10"
    elif typ == "Wait":
        try:
            if not 0 <= float(val.replace(",", ".")) <= 60:
                return "пауза от 0 до 60 секунд"
        except ValueError:
            return "пауза — число секунд"
    elif typ == "Web.Open":
        if not re.match(r"https?://", val, re.I):
            return "адрес должен начинаться с https://"
    return None


def sanitize_command(raw: dict) -> dict:
    """Clean a command coming from the editor or the AI. Raises ValueError if unusable."""
    name = " ".join(str(raw.get("name", "")).split())[:60]
    phrases = [" ".join(str(p).split()) for p in raw.get("phrases", []) if str(p).strip()]
    optional = [" ".join(str(p).split()) for p in raw.get("optional", []) if str(p).strip()]
    actions = []
    for a in raw.get("actions", []):
        act = {"type": str(a.get("type", "")), "value": str(a.get("value", "")).strip()}
        problem = validate_action(act)
        if problem:
            raise ValueError(f"{act['type'] or 'действие'}: {problem}")
        actions.append(act)
    if not name:
        raise ValueError("не указано название")
    if not phrases:
        raise ValueError("нужна хотя бы одна фраза для активации")
    if not actions:
        raise ValueError("добавь хотя бы одно действие")
    return {"id": str(raw.get("id") or uuid.uuid4().hex[:10]), "name": name, "phrases": phrases,
            "optional": optional, "confirm": bool(raw.get("confirm")),
            "enabled": bool(raw.get("enabled", True)), "actions": actions}


# ── storage ────────────────────────────────────────────────────────────────────
def _load() -> dict:
    try:
        d = json.loads(COMMANDS_FILE.read_text(encoding="utf-8"))
    except Exception:
        d = {}
    d.setdefault("commands", [])
    d.setdefault("packs", {})
    return d


def _save(d: dict) -> None:
    COMMANDS_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = COMMANDS_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, COMMANDS_FILE)


def user_commands() -> list[dict]:
    with _LOCK:
        return list(_load()["commands"])


def save_command(raw: dict) -> dict:
    cmd = sanitize_command(raw)
    with _LOCK:
        d = _load()
        d["commands"] = [c for c in d["commands"] if c["id"] != cmd["id"]] + [cmd]
        _save(d)
    return cmd


def delete_command(cmd_id: str) -> None:
    with _LOCK:
        d = _load()
        d["commands"] = [c for c in d["commands"] if c["id"] != cmd_id]
        _save(d)


def set_command_enabled(cmd_id: str, on: bool) -> None:
    with _LOCK:
        d = _load()
        for c in d["commands"]:
            if c["id"] == cmd_id:
                c["enabled"] = bool(on)
        _save(d)


def pack_enabled(pack_id: str) -> bool:
    with _LOCK:
        return bool(_load()["packs"].get(pack_id, True))      # packs are on by default


def set_pack_enabled(pack_id: str, on: bool) -> None:
    with _LOCK:
        d = _load()
        d["packs"][pack_id] = bool(on)
        _save(d)


def all_commands() -> list[dict]:
    """Your enabled commands first, then the enabled packs."""
    from core.command_packs import PACKS
    out = [c for c in user_commands() if c.get("enabled", True)]
    for pid, pack in PACKS.items():
        if pack_enabled(pid):
            out.extend(pack["commands"])
    return out


# ── matching ───────────────────────────────────────────────────────────────────
_GLOBAL_OPTIONAL = ("пожалуйста", "ка", "ну", "мне", "давай", "а ну")


def _strip_words(text: str, words: list[str]) -> str:
    t = f" {text} "
    for w in sorted((norm(x) for x in words if x), key=len, reverse=True):
        if w:
            t = t.replace(f" {w} ", " ")
    return " ".join(t.split())


def match(text: str):
    """-> (command, params) for the best matching command, or None."""
    t = norm(text)
    if not t:
        return None
    best, best_key = None, (0.0, 0)
    for cmd in all_commands():
        opt = list(cmd.get("optional", [])) + list(_GLOBAL_OPTIONAL)
        tt = _strip_words(t, opt) or t
        for phrase in cmd["phrases"]:
            p = norm(phrase.replace("{n}", f" {PH} "))
            if PH in p:
                left, _, right = p.partition(PH)
                rx = "^" + re.escape(left.strip()) + r"\s*(?P<n>.+?)\s*" + re.escape(right.strip()) + "$"
                m = re.match(rx, tt)
                if not m:
                    continue
                num = parse_number_ru(m.group("n"))
                if num is None:
                    continue
                key, params = (1.0, len(p)), {"n": str(num)}
            else:
                if tt == p:
                    key, params = (1.0, len(p)), {}
                else:
                    r = difflib.SequenceMatcher(None, tt, p).ratio()
                    if len(p) < 6 or r < 0.9:
                        continue
                    key, params = (r, len(p)), {}
            if key > best_key:
                best, best_key, best_params = cmd, key, params
    return (best, best_params) if best else None


# ── running ────────────────────────────────────────────────────────────────────
class Backends:
    """The real thing. Tests pass their own object with the same methods."""

    def launch(self, target: str) -> None:
        from core import app_catalog
        if os.path.exists(target):
            app_catalog.launch(app_catalog.Entry(name=Path(target).stem, kind="path", launch=target))
            return
        entry = app_catalog.AppCatalog(logger=lambda _m: None).resolve(target)
        if entry is None:
            raise RuntimeError(f"не нашла «{target}» на этом компьютере")
        app_catalog.launch(entry)

    def reveal(self, path: str) -> None:
        """Show a file in its folder (Explorer highlights it)."""
        import subprocess
        if sys.platform == "win32":
            subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
        else:
            subprocess.Popen(["xdg-open", os.path.dirname(path) or "."],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def open_path(self, path: str) -> None:
        from core import app_catalog
        app_catalog.launch(app_catalog.Entry(name=Path(path).stem, kind="path", launch=path))

    def open_url(self, url: str) -> None:
        import webbrowser
        webbrowser.open(url)

    def hotkey(self, keys: list[str]) -> None:
        import pyautogui
        pyautogui.FAILSAFE = False
        pyautogui.hotkey(*keys)

    def type_text(self, text: str) -> None:
        import pyautogui
        import pyperclip
        old = None
        try:
            old = pyperclip.paste()
        except Exception:
            pass
        pyperclip.copy(text)
        pyautogui.hotkey("ctrl", "v")
        time.sleep(0.15)
        if old is not None:
            try:
                pyperclip.copy(old)
            except Exception:
                pass

    def click(self, x: int, y: int) -> None:
        import pyautogui
        pyautogui.FAILSAFE = False
        pyautogui.click(x, y)

    def _endpoint(self):
        from ctypes import POINTER, cast
        from comtypes import CLSCTX_ALL
        from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
        dev = AudioUtilities.GetSpeakers()
        if hasattr(dev, "EndpointVolume"):
            return dev.EndpointVolume
        iface = dev.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
        return cast(iface, POINTER(IAudioEndpointVolume))

    def set_volume(self, pct: int) -> None:
        pct = max(0, min(100, int(pct)))
        try:
            self._endpoint().SetMasterVolumeLevelScalar(pct / 100.0, None)
        except Exception:                                   # no pycaw: walk it with the volume keys
            from core import widget_data as wd
            for _ in range(50):
                wd.press_media_key("volume_down")
            for _ in range(pct // 2):
                wd.press_media_key("volume_up")

    def change_volume(self, delta: int) -> None:
        try:
            ep = self._endpoint()
            cur = ep.GetMasterVolumeLevelScalar() * 100
            ep.SetMasterVolumeLevelScalar(max(0.0, min(100.0, cur + delta)) / 100.0, None)
        except Exception:
            from core import widget_data as wd
            for _ in range(max(1, abs(int(delta)) // 2)):
                wd.press_media_key("volume_up" if delta > 0 else "volume_down")

    def media(self, key: str) -> None:
        from core import widget_data as wd
        if not wd.press_media_key(key):
            raise RuntimeError("медиаклавиши недоступны на этой системе")

    def lock(self) -> None:
        from core import widget_data as wd
        wd.lock_workstation()

    def power(self, what: str) -> None:
        import subprocess
        cmd = {"shutdown": ["shutdown", "/s", "/t", "30"], "restart": ["shutdown", "/r", "/t", "30"],
               "cancel": ["shutdown", "/a"],
               "sleep": ["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"]}[what]
        subprocess.run(cmd, check=False)

    def sleep(self, seconds: float) -> None:
        time.sleep(seconds)


def _sub(value: str, params: dict) -> str:
    return value.replace("{n}", params.get("n", "")) if "{n}" in value else value


def run_actions(actions: list[dict], params: dict | None = None, backends=None) -> list[str]:
    """Run the actions in order. Returns a list of error texts (empty = all fine).
    One failing step does not stop the rest — a half-done «режим стрима» is still useful."""
    be = backends or Backends()
    params = params or {}
    errors: list[str] = []
    for act in actions:
        typ, val = act["type"], _sub(str(act.get("value", "")), params).strip()
        try:
            problem = validate_action({"type": typ, "value": val})
            if problem:
                raise ValueError(problem)
            if typ == "Launch.File":
                be.launch(val)
            elif typ == "Web.Open":
                be.open_url(val)
            elif typ == "Keys.Press":
                be.hotkey([k.strip().lower() for k in val.split("+") if k.strip()])
            elif typ == "Keys.Type":
                be.type_text(val)
            elif typ == "Mouse.ClickLeft":
                x, y = (int(v) for v in re.split(r"[,; ]+", val.strip()))
                be.click(x, y)
            elif typ == "System.VolumeSet":
                be.set_volume(int(val))
            elif typ == "System.VolumeChange":
                be.change_volume(int(val))
            elif typ == "System.Mute":
                be.media("mute")
            elif typ == "Media.PlayPause":
                be.media("play_pause")
            elif typ == "Media.Next":
                be.media("next")
            elif typ == "Media.Prev":
                be.media("prev")
            elif typ == "System.Lock":
                be.lock()
            elif typ == "System.Sleep":
                be.power("sleep")
            elif typ == "System.Shutdown":
                be.power("shutdown")
            elif typ == "System.Restart":
                be.power("restart")
            elif typ == "System.CancelShutdown":
                be.power("cancel")
            elif typ == "Wait":
                be.sleep(float(val.replace(",", ".")))
        except Exception as exc:
            errors.append(f"{typ}: {exc}")
    return errors


# ── prefix mode: «Джарвис, …» ─────────────────────────────────────────────────
DEFAULT_PREFIX = ["джарвис", "ассистент", "компьютер"]
_FILLERS = {"эй", "привет", "слушай", "ну", "окей", "ок", "хей"}


def apply_prefix(text: str, enabled: bool, words: list[str] | None = None) -> str | None:
    """Prefix mode. Returns the text to process, '' if only the name was said,
    or None when the phrase was not addressed to the assistant (ignore it)."""
    if not enabled:
        return text
    words = [norm(w) for w in (words or DEFAULT_PREFIX) if w]
    toks = text.split()
    i = 0
    while i < len(toks) and norm(toks[i]) in _FILLERS:
        i += 1
    if i >= len(toks):
        return None
    first = norm(toks[i])
    if any(first == w or (len(w) >= 5 and difflib.SequenceMatcher(None, first, w).ratio() >= 0.8) for w in words):
        return " ".join(toks[i + 1:]).lstrip(" ,.:;-!?").strip()
    return None


# ── "create with AI" ──────────────────────────────────────────────────────────
_AI_PROMPT = """Ты помогаешь собрать голосовую команду для управления компьютером с Windows.
Пользователь описал её словами. Верни ТОЛЬКО JSON без пояснений такого вида:
{{"name": "короткое название", "phrases": ["фраза для активации", "..."], "optional": [],
  "confirm": false, "actions": [{{"type": "...", "value": "..."}}]}}

Разрешённые type и value:
{types}

Правила: 2-4 разные естественные русские фразы; confirm=true для выключения, перезагрузки и удаления;
{{n}} можно использовать в фразе и в value для чисел (например фраза "громкость на {{n}}").
Описание пользователя: {desc}"""


def build_ai_prompt(description: str) -> str:
    types = "\n".join(f"- {t}: {lab}" + (f" (пример: {hint})" if hint else "")
                      for t, (lab, hint) in ACTION_TYPES.items())
    return _AI_PROMPT.format(types=types, desc=description.strip())


def generate_with_ai(description: str, ask=None) -> dict:
    """Describe a command in words -> a validated command dict (not saved yet).
    `ask(prompt)` returns parsed JSON; by default Gemini is used. Raises ValueError."""
    if not description.strip():
        raise ValueError("опиши команду словами")
    if ask is None:
        from core import gemini
        ask = lambda prompt: gemini.as_json(prompt, tier=gemini.SMART)
    raw = ask(build_ai_prompt(description))
    if not isinstance(raw, dict):
        raise ValueError("ИИ не вернул команду. Проверь ключ Gemini и интернет.")
    return sanitize_command(raw)
