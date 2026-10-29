"""
core/desks.py — "desks": your own Home tabs, each a set of widgets.

A desk is {"id", "name", "widgets": [{"type", "size"}]}. Sizes are cells on a
4-column grid: "1x1", "2x1", "2x2", "4x2". The order of the list is the order on
screen (widgets are packed left-to-right, top-to-bottom), so moving a widget is
just swapping neighbours. Stored in data/desks.json.
"""
from __future__ import annotations

import difflib
import json
import os
import re
import sys
import threading
from pathlib import Path

_BASE = (Path(sys.executable).parent if getattr(sys, "frozen", False)
         else Path(__file__).resolve().parent.parent)
DESKS_FILE = _BASE / "data" / "desks.json"
_LOCK = threading.RLock()

# type -> (title, default size, short description)
WIDGETS: dict[str, tuple[str, str, str]] = {
    "clock":    ("Часы",            "2x1", "Время и дата"),
    "weather":  ("Погода",          "2x1", "Температура в твоём городе"),
    "tasks":    ("Задачи",          "2x2", "Список дел с галочками"),
    "notes":    ("Заметки",         "2x2", "Быстрые записи"),
    "calendar": ("Календарь",       "2x2", "Месяц и ближайшие события"),
    "rates":    ("Курсы валют",     "2x1", "Доллар и евро в рублях"),
    "system":   ("Компьютер",       "2x1", "Нагрузка процессора, памяти и диска"),
    "media":    ("Плеер",           "2x1", "Пауза, дальше, назад для любой музыки"),
    "apps":     ("Программы",       "2x1", "Быстрый запуск программ и игр"),
    "history":  ("История команд",  "2x2", "Что ты говорил ассистенту"),
    "timer":    ("Таймер",          "1x1", "Обратный отсчёт"),
    "pet":      ("Питомец",         "2x1", "Включить питомца на рабочем столе"),
    "orb":      ("Аватар",          "4x2", "Большие круги, которые дышат с голосом"),
}
SIZES = ["1x1", "2x1", "2x2", "4x2"]

# 12 starting points, as in the "new desk" dialog
PRESETS: list[dict] = [
    {"key": "empty",    "name": "Пустой",          "hint": "Добавишь виджеты сам",              "widgets": []},
    {"key": "morning",  "name": "Утро",            "hint": "Погода, события, задачи и курсы",   "widgets": ["clock", "weather", "tasks", "rates"]},
    {"key": "work",     "name": "Работа",          "hint": "Задачи, календарь, заметки",        "widgets": ["tasks", "calendar", "notes", "apps"]},
    {"key": "study",    "name": "Учёба",           "hint": "Таймер, задачи, заметки",           "widgets": ["timer", "tasks", "notes", "calendar"]},
    {"key": "time",     "name": "Время и заметки", "hint": "Часы, календарь, задачи и заметки", "widgets": ["clock", "calendar", "tasks", "notes"]},
    {"key": "finance",  "name": "Финансы",         "hint": "Курсы, заметки и задачи",           "widgets": ["rates", "notes", "tasks"]},
    {"key": "media",    "name": "Медиа",           "hint": "Плеер, часы и история команд",      "widgets": ["media", "clock", "history"]},
    {"key": "games",    "name": "Игры",            "hint": "Программы, плеер и нагрузка ПК",    "widgets": ["apps", "media", "system"]},
    {"key": "computer", "name": "Компьютер",       "hint": "Система, программы, команды",       "widgets": ["system", "apps", "history"]},
    {"key": "home",     "name": "Умный дом",       "hint": "Погода, часы и заметки",            "widgets": ["weather", "clock", "notes"]},
    {"key": "pet",      "name": "Питомец",         "hint": "Питомец и быстрые виджеты",         "widgets": ["pet", "clock", "tasks"]},
    {"key": "avatar",   "name": "Только аватар",   "hint": "Большие круги на весь стол",        "widgets": ["orb"]},
]


def _load() -> dict:
    try:
        d = json.loads(DESKS_FILE.read_text(encoding="utf-8"))
        d.setdefault("desks", [])
        d.setdefault("next_id", 1)
        return d
    except Exception:
        return {"desks": [], "next_id": 1}


def _save(d: dict) -> None:
    DESKS_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = DESKS_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, DESKS_FILE)


def default_size(wtype: str) -> str:
    return WIDGETS.get(wtype, ("", "2x1", ""))[1]


def parse_size(size: str) -> tuple[int, int]:
    m = re.fullmatch(r"([1-4])x([1-4])", size or "")
    return (int(m.group(1)), int(m.group(2))) if m else (2, 1)


def list_desks() -> list[dict]:
    with _LOCK:
        return _load()["desks"]


def get_desk(desk_id: int) -> dict | None:
    return next((d for d in list_desks() if d["id"] == desk_id), None)


def create_desk(name: str, preset_key: str = "empty") -> dict:
    name = " ".join((name or "").split())[:30] or "Новый стол"
    preset = next((p for p in PRESETS if p["key"] == preset_key), PRESETS[0])
    with _LOCK:
        d = _load()
        desk = {"id": d["next_id"], "name": name,
                "widgets": [{"type": t, "size": default_size(t)} for t in preset["widgets"]]}
        d["next_id"] += 1
        d["desks"].append(desk)
        _save(d)
        return desk


def delete_desk(desk_id: int) -> None:
    with _LOCK:
        d = _load()
        d["desks"] = [x for x in d["desks"] if x["id"] != desk_id]
        _save(d)


def rename_desk(desk_id: int, name: str) -> None:
    name = " ".join((name or "").split())[:30]
    if not name:
        return
    with _LOCK:
        d = _load()
        for x in d["desks"]:
            if x["id"] == desk_id:
                x["name"] = name
        _save(d)


def _with_desk(desk_id: int, fn) -> None:
    with _LOCK:
        d = _load()
        for x in d["desks"]:
            if x["id"] == desk_id:
                fn(x["widgets"])
        _save(d)


def add_widget(desk_id: int, wtype: str) -> None:
    if wtype in WIDGETS:
        _with_desk(desk_id, lambda w: w.append({"type": wtype, "size": default_size(wtype)}))


def remove_widget(desk_id: int, index: int) -> None:
    def fn(w):
        if 0 <= index < len(w):
            w.pop(index)
    _with_desk(desk_id, fn)


def move_widget(desk_id: int, index: int, delta: int) -> None:
    def fn(w):
        j = index + delta
        if 0 <= index < len(w) and 0 <= j < len(w):
            w[index], w[j] = w[j], w[index]
    _with_desk(desk_id, fn)


def cycle_size(desk_id: int, index: int) -> None:
    def fn(w):
        if 0 <= index < len(w):
            cur = w[index].get("size", "2x1")
            w[index]["size"] = SIZES[(SIZES.index(cur) + 1) % len(SIZES)] if cur in SIZES else SIZES[0]
    _with_desk(desk_id, fn)


def find_desk(spoken: str) -> dict | None:
    """'игры', 'стол Игры', 'работа' -> the best matching desk (or None)."""
    want = re.sub(r"[^0-9a-zа-я ]+", " ", (spoken or "").lower().replace("ё", "е")).split()
    want = " ".join(w for w in want if w not in ("стол", "стола", "столе", "на", "в"))
    if not want:
        return None
    best, score = None, 0.0
    for desk in list_desks():
        name = re.sub(r"[^0-9a-zа-я ]+", " ", desk["name"].lower().replace("ё", "е")).strip()
        s = 1.0 if name == want else (0.9 if want in name or name in want else
                                      difflib.SequenceMatcher(None, want, name).ratio())
        if s > score:
            best, score = desk, s
    return best if score >= 0.72 else None


def pack_layout(sizes: list[tuple[int, int]], cols: int = 4) -> list[tuple[int, int, int, int]]:
    """First-fit packing of (w, h) cells onto a `cols`-wide grid, in list order.
    Returns (row, col, w, h) per widget. A widget wider than the grid is clamped."""
    taken: set[tuple[int, int]] = set()
    out: list[tuple[int, int, int, int]] = []
    for w, h in sizes:
        w = max(1, min(cols, int(w)))
        h = max(1, int(h))
        r = 0
        while True:
            placed = False
            for c in range(0, cols - w + 1):
                if all((r + dr, c + dc) not in taken for dr in range(h) for dc in range(w)):
                    for dr in range(h):
                        for dc in range(w):
                            taken.add((r + dr, c + dc))
                    out.append((r, c, w, h))
                    placed = True
                    break
            if placed:
                break
            r += 1
    return out
