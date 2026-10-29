"""
core/app_catalog.py — what is installed on this PC, findable by voice.

Windows: scans Steam libraries (every drive listed in libraryfolders.vdf), Epic
Games manifests and Start-Menu shortcuts, so "запусти Dota" or "открой Cyberpunk"
works without anyone wiring each game to a command by hand.

The scan costs a few hundred milliseconds, so it runs in a background thread,
is cached in cache/app_catalog.json and refreshed at most every 12 hours.

Spoken names are matched loosely: Russian speech is transliterated to Latin
("дота два" -> "dota2"), compared with difflib, and only a confident match wins.
An unknown name resolves to None — the caller then lets the model handle the
request instead of launching something wrong.

Own words for a program go in data/app_aliases.json:
    {"контру": "Counter-Strike 2", "мой редактор": "C:/Tools/editor.exe"}
"""
from __future__ import annotations

import difflib
import json
import os
import platform
import re
import sys
import subprocess
import threading
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional

# Next to the exe when installed (same rule as the rest of the app), else the project folder.
ROOT = (Path(sys.executable).parent if getattr(sys, "frozen", False)
        else Path(__file__).resolve().parent.parent)
CACHE_FILE = ROOT / "cache" / "app_catalog.json"
USER_ALIASES_FILE = ROOT / "data" / "app_aliases.json"
CACHE_TTL = 12 * 3600
MATCH_THRESHOLD = 0.80
_IS_WIN = platform.system() == "Windows"

# Never terminated by a voice command, whatever the name resolves to.
PROTECTED = {
    "explorer.exe", "system", "svchost.exe", "winlogon.exe", "csrss.exe",
    "services.exe", "lsass.exe", "wininit.exe", "dwm.exe", "smss.exe",
    "python.exe", "pythonw.exe", "py.exe", "cmd.exe", "conhost.exe",
}


@dataclass
class Entry:
    name: str
    kind: str            # steam | epic | shortcut | builtin | path
    launch: str          # steam:// URI, exe/lnk path, or open_app name
    exe: str = ""        # process names to close, comma separated, lowercase
    install_dir: str = ""


# ── name matching ──────────────────────────────────────────────────────────────

_RU = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ж": "zh", "з": "z",
    "и": "i", "й": "y", "к": "k", "л": "l", "м": "m", "н": "n", "о": "o", "п": "p",
    "р": "r", "с": "s", "т": "t", "у": "u", "ф": "f", "х": "h", "ц": "ts", "ч": "ch",
    "ш": "sh", "щ": "sch", "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
}
_NUMS = {
    "ноль": "0", "один": "1", "два": "2", "три": "3", "четыре": "4", "пять": "5",
    "шесть": "6", "семь": "7", "восемь": "8", "девять": "9", "десять": "10",
    "zero": "0", "one": "1", "two": "2", "three": "3", "four": "4", "five": "5",
    "six": "6", "seven": "7", "eight": "8", "nine": "9", "ten": "10",
}


def _norm(text: str) -> str:
    text = (text or "").lower().replace("ё", "е")
    text = re.sub(r"[^0-9a-zа-я]+", " ", text)
    return " ".join(_NUMS.get(t, t) for t in text.split())


def _phonetic(latin: str, c_as: str) -> str:
    """Make Latin spellings sound-alike: 'cyberpunk' and Russian 'киберпанк'
    should land close together. `c_as` is how a bare 'c' is read."""
    s = latin
    for a, b in (("ph", "f"), ("ck", "k"), ("sch", "sh"), ("kh", "h"), ("ee", "i"),
                 ("oo", "u"), ("q", "k"), ("w", "v"), ("x", "ks"), ("y", "i")):
        s = s.replace(a, b)
    s = s.replace("c", c_as)
    out = []
    for ch in s:
        if not out or ch != out[-1] or ch.isdigit():
            out.append(ch)               # collapse doubled letters, keep "77"
    return "".join(out)


def _key(text: str, c_as: str) -> str:
    latin = "".join(_RU.get(ch, ch) for ch in _norm(text)).replace(" ", "")
    return _phonetic(latin, c_as)


def match_key(text: str) -> str:
    """'Дота два' and 'Dota 2' both become 'dota2'."""
    return _key(text, "k")


def match_variants(text: str) -> set[str]:
    """'cyber' is read with a K by Russians and an S by English speakers."""
    return {_key(text, "k"), _key(text, "s")}


def _score(spoken_key: str, name_key: str) -> float:
    if not spoken_key or not name_key:
        return 0.0
    if spoken_key == name_key:
        return 1.0
    if len(spoken_key) >= 4 and (name_key.startswith(spoken_key) or spoken_key in name_key.split()):
        return 0.92
    if len(name_key) >= 4 and spoken_key.startswith(name_key):
        return 0.9
    if len(spoken_key) >= 5:
        # Spoken as the first word(s) of a longer title: "киберпанк" -> "Cyberpunk 2077"
        head = difflib.SequenceMatcher(None, spoken_key, name_key[:len(spoken_key)]).ratio()
        if head >= 0.85:
            return 0.82 + (head - 0.85) * 0.5
    return difflib.SequenceMatcher(None, spoken_key, name_key).ratio()


# ── built-in programs, by the way people say them ─────────────────────────────

# spoken -> (open_app name, process names)
BUILTIN: dict[str, tuple[str, str]] = {
    "стим": ("steam", "steam.exe,steamwebhelper.exe"),
    "steam": ("steam", "steam.exe,steamwebhelper.exe"),
    "дискорд": ("discord", "discord.exe"),
    "discord": ("discord", "discord.exe"),
    "телеграм": ("telegram", "telegram.exe"),
    "телега": ("telegram", "telegram.exe"),
    "telegram": ("telegram", "telegram.exe"),
    "хром": ("chrome", "chrome.exe"),
    "гугл хром": ("chrome", "chrome.exe"),
    "chrome": ("chrome", "chrome.exe"),
    "фаерфокс": ("firefox", "firefox.exe"),
    "firefox": ("firefox", "firefox.exe"),
    "опера": ("opera", "opera.exe"),
    "эдж": ("edge", "msedge.exe"),
    "спотифай": ("spotify", "spotify.exe"),
    "spotify": ("spotify", "spotify.exe"),
    "ватсап": ("whatsapp", "whatsapp.exe"),
    "whatsapp": ("whatsapp", "whatsapp.exe"),
    "зум": ("zoom", "zoom.exe"),
    "zoom": ("zoom", "zoom.exe"),
    "блокнот": ("notepad", "notepad.exe"),
    "notepad": ("notepad", "notepad.exe"),
    "калькулятор": ("calculator", "calculatorapp.exe,calc.exe,win32calc.exe"),
    "calculator": ("calculator", "calculatorapp.exe,calc.exe,win32calc.exe"),
    "проводник": ("explorer", ""),
    "диспетчер задач": ("task manager", "taskmgr.exe"),
    "ворд": ("word", "winword.exe"),
    "word": ("word", "winword.exe"),
    "эксель": ("excel", "excel.exe"),
    "excel": ("excel", "excel.exe"),
    "пейнт": ("paint", "mspaint.exe"),
    "паинт": ("paint", "mspaint.exe"),
    "терминал": ("terminal", "windowsterminal.exe,wt.exe"),
    "эпик геймс": ("epic games", "epicgameslauncher.exe"),
    "epic games": ("epic games", "epicgameslauncher.exe"),
    "обс": ("obs", "obs64.exe"),
    "obs": ("obs", "obs64.exe"),
    "тикток": ("tiktok", "tiktok.exe"),
    "visual studio code": ("vscode", "code.exe"),
    "вс код": ("vscode", "code.exe"),
}


# ── scanners ───────────────────────────────────────────────────────────────────

_KV = re.compile(r'"([^"]+)"\s+"([^"]*)"')
_STEAM_SKIP = ("steamworks", "proton", "steam linux runtime", "redistributable")


def _steam_roots() -> list[Path]:
    roots: list[Path] = []
    if _IS_WIN:
        try:
            import winreg
            for hive, sub, val in (
                (winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam", "SteamPath"),
                (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam", "InstallPath"),
            ):
                try:
                    with winreg.OpenKey(hive, sub) as k:
                        roots.append(Path(winreg.QueryValueEx(k, val)[0]))
                except OSError:
                    pass
        except Exception:
            pass
        for env in ("ProgramFiles(x86)", "ProgramFiles"):
            base = os.environ.get(env)
            if base:
                roots.append(Path(base) / "Steam")
    else:
        home = Path.home()
        roots += [home / ".steam" / "steam", home / ".local" / "share" / "Steam"]
    seen, out = set(), []
    for r in roots:
        if r.is_dir() and str(r).lower() not in seen:
            seen.add(str(r).lower())
            out.append(r)
    return out


def _steam_libraries(root: Path) -> list[Path]:
    libs = [root]
    vdf = root / "steamapps" / "libraryfolders.vdf"
    try:
        text = vdf.read_text(encoding="utf-8", errors="ignore")
        for m in re.finditer(r'"path"\s+"([^"]+)"', text):
            libs.append(Path(m.group(1).replace("\\\\", "\\")))
    except OSError:
        pass
    seen, out = set(), []
    for lib in libs:
        if str(lib).lower() not in seen and (lib / "steamapps").is_dir():
            seen.add(str(lib).lower())
            out.append(lib)
    return out


def scan_steam() -> list[Entry]:
    entries: list[Entry] = []
    seen_ids: set[str] = set()
    for root in _steam_roots():
        for lib in _steam_libraries(root):
            apps = lib / "steamapps"
            for acf in apps.glob("appmanifest_*.acf"):
                try:
                    kv = dict(_KV.findall(acf.read_text(encoding="utf-8", errors="ignore")))
                except OSError:
                    continue
                appid, name, folder = kv.get("appid"), kv.get("name"), kv.get("installdir")
                if not appid or not name or appid in seen_ids:
                    continue
                if any(s in name.lower() for s in _STEAM_SKIP):
                    continue
                seen_ids.add(appid)
                entries.append(Entry(name=name, kind="steam",
                                     launch=f"steam://rungameid/{appid}",
                                     install_dir=str(apps / "common" / folder) if folder else ""))
    return entries


def scan_epic() -> list[Entry]:
    entries: list[Entry] = []
    base = os.environ.get("ProgramData")
    if not (_IS_WIN and base):
        return entries
    for item in (Path(base) / "Epic" / "EpicGamesLauncher" / "Data" / "Manifests").glob("*.item"):
        try:
            data = json.loads(item.read_text(encoding="utf-8", errors="ignore"))
            name, loc, exe = data.get("DisplayName"), data.get("InstallLocation"), data.get("LaunchExecutable")
            if name and loc and exe:
                entries.append(Entry(name=name, kind="epic", launch=str(Path(loc) / exe),
                                     exe=Path(exe).name.lower(), install_dir=loc))
        except Exception:
            continue
    return entries


_LNK_SKIP = ("uninstall", "удалить", "удаление", "readme", "documentation", "help",
             "справка", "license", "лицензи", "website", "сайт")


def scan_shortcuts() -> list[Entry]:
    entries: list[Entry] = []
    if not _IS_WIN:
        return entries
    dirs = [Path(os.environ.get("ProgramData", "")) / "Microsoft/Windows/Start Menu/Programs",
            Path(os.environ.get("APPDATA", "")) / "Microsoft/Windows/Start Menu/Programs"]
    seen: set[str] = set()
    for d in dirs:
        if not d.is_dir():
            continue
        for lnk in d.rglob("*.lnk"):
            name = lnk.stem
            low = name.lower()
            if low in seen or any(s in low for s in _LNK_SKIP):
                continue
            seen.add(low)
            entries.append(Entry(name=name, kind="shortcut", launch=str(lnk)))
    return entries


# ── catalog ────────────────────────────────────────────────────────────────────

class AppCatalog:
    def __init__(self, logger=print):
        self._log = logger
        self._lock = threading.Lock()
        self.entries: list[Entry] = []
        self._loaded_at = 0.0
        self._aliases: dict[str, str] = {}
        self._aliases_mtime = 0.0
        self._refreshing = False
        self.load_cache()
        self.load_aliases()

    # persistence
    def load_cache(self) -> bool:
        try:
            data = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
            with self._lock:
                self.entries = [Entry(**e) for e in data.get("entries", [])]
                self._loaded_at = float(data.get("at", 0))
            return True
        except Exception:
            return False

    def load_aliases(self) -> None:
        try:
            self._aliases_mtime = USER_ALIASES_FILE.stat().st_mtime
            raw = json.loads(USER_ALIASES_FILE.read_text(encoding="utf-8"))
            self._aliases = {match_key(k): str(v) for k, v in raw.items()}
        except Exception:
            self._aliases = {}

    def aliases(self) -> dict[str, str]:
        """{spoken phrase: target} exactly as the user wrote them."""
        try:
            return {k: str(v) for k, v in json.loads(
                USER_ALIASES_FILE.read_text(encoding="utf-8")).items()}
        except Exception:
            return {}

    def remove_alias(self, spoken: str) -> None:
        raw = self.aliases()
        raw.pop(spoken, None)
        USER_ALIASES_FILE.parent.mkdir(parents=True, exist_ok=True)
        USER_ALIASES_FILE.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
        self.load_aliases()

    def add_alias(self, spoken: str, target: str) -> None:
        try:
            USER_ALIASES_FILE.parent.mkdir(parents=True, exist_ok=True)
            try:
                raw = json.loads(USER_ALIASES_FILE.read_text(encoding="utf-8"))
            except Exception:
                raw = {}
            raw[spoken.strip()] = target.strip()
            USER_ALIASES_FILE.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
        finally:
            self.load_aliases()

    @property
    def stale(self) -> bool:
        return (time.time() - self._loaded_at) > CACHE_TTL

    def refresh(self) -> int:
        entries: list[Entry] = []
        for scan in (scan_steam, scan_epic, scan_shortcuts):
            try:
                entries += scan()
            except Exception as exc:
                self._log(f"[Catalog] {scan.__name__} failed: {exc}")
        with self._lock:
            self.entries = entries
            self._loaded_at = time.time()
        try:
            CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
            CACHE_FILE.write_text(json.dumps(
                {"at": self._loaded_at, "entries": [asdict(e) for e in entries]},
                ensure_ascii=False), encoding="utf-8")
        except OSError:
            pass
        self._log(f"[Catalog] {len(entries)} apps and games indexed.")
        return len(entries)

    def refresh_async(self, force: bool = False) -> None:
        if self._refreshing or not (force or self.stale):
            return
        self._refreshing = True

        def _run():
            try:
                self.refresh()
            finally:
                self._refreshing = False

        threading.Thread(target=_run, daemon=True, name="AppCatalogScan").start()

    # lookup
    def resolve(self, spoken: str) -> Optional[Entry]:
        key = match_key(spoken)
        if not key:
            return None

        try:   # aliases edited in the app while it is running
            if USER_ALIASES_FILE.stat().st_mtime != self._aliases_mtime:
                self.load_aliases()
        except OSError:
            pass

        target = self._aliases.get(key)
        if target:
            if os.path.exists(target):
                return Entry(name=Path(target).stem, kind="path", launch=target,
                             exe=Path(target).name.lower())
            hit = self._best(match_key(target))
            if hit:
                return hit

        for phrase, (app, procs) in BUILTIN.items():
            if match_key(phrase) == key:
                return Entry(name=app, kind="builtin", launch=app, exe=procs)

        return self._best(key)

    def _best(self, key: str) -> Optional[Entry]:
        best, best_score = None, 0.0
        with self._lock:
            entries = list(self.entries)
        for e in entries:
            s = max(_score(key, v) for v in match_variants(e.name))
            if s > best_score:
                best, best_score = e, s
        return best if best and best_score >= MATCH_THRESHOLD else None


# ── actions ────────────────────────────────────────────────────────────────────

def launch(entry: Entry) -> str:
    """Start the program. Returns a short English status for logs."""
    if entry.kind == "builtin":
        from actions.open_app import open_app
        return open_app({"app_name": entry.launch})
    try:
        if _IS_WIN:
            os.startfile(entry.launch)  # type: ignore[attr-defined]
        else:
            opener = "open" if platform.system() == "Darwin" else "xdg-open"
            subprocess.Popen([opener, entry.launch],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return f"Opened {entry.name}."
    except Exception as exc:
        return f"Failed to open {entry.name}: {exc}"


def close(entry: Entry) -> int:
    """Politely terminate the program's processes. Returns how many were stopped."""
    try:
        import psutil
    except ImportError:
        return 0
    names = {n.strip().lower() for n in entry.exe.split(",") if n.strip()}
    guess = match_key(entry.name) if not names and not entry.install_dir else ""
    folder = entry.install_dir.lower().rstrip("\\/") if entry.install_dir else ""
    me = os.getpid()
    stopped = 0
    for proc in psutil.process_iter(["pid", "name", "exe"]):
        try:
            pname = (proc.info["name"] or "").lower()
            if proc.info["pid"] == me or pname in PROTECTED:
                continue
            pexe = (proc.info["exe"] or "").lower()
            hit = (pname in names
                   or (folder and pexe.startswith(folder + os.sep))
                   or (guess and _score(guess, match_key(Path(pname).stem)) >= 0.9))
            if hit:
                proc.terminate()
                stopped += 1
        except Exception:
            continue
    return stopped
