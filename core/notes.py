"""
core/notes.py — tasks, notes and calendar events, kept in data/notes.json.

Used by the widgets (Tasks, Notes, Calendar), by voice commands ("добавь задачу …",
"запиши заметку …") and by the model through the same file. Plain JSON, written
atomically, safe to call from any thread.
"""
from __future__ import annotations

import json
import os
import re
import sys
import threading
import time
from datetime import date, datetime
from pathlib import Path

_BASE = (Path(sys.executable).parent if getattr(sys, "frozen", False)
         else Path(__file__).resolve().parent.parent)
NOTES_FILE = _BASE / "data" / "notes.json"
_LOCK = threading.RLock()


def _empty() -> dict:
    return {"tasks": [], "notes": [], "events": [], "next_id": 1}


def _load() -> dict:
    try:
        data = json.loads(NOTES_FILE.read_text(encoding="utf-8"))
        for k, v in _empty().items():
            data.setdefault(k, v)
        return data
    except Exception:
        return _empty()


def _save(data: dict) -> None:
    NOTES_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = NOTES_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, NOTES_FILE)


def _new_id(data: dict) -> int:
    i = int(data.get("next_id", 1))
    data["next_id"] = i + 1
    return i


# ── tasks ──────────────────────────────────────────────────────────────────────
def add_task(text: str) -> dict | None:
    text = " ".join((text or "").split())
    if not text:
        return None
    with _LOCK:
        d = _load()
        task = {"id": _new_id(d), "text": text[:200], "done": False, "ts": time.time()}
        d["tasks"].append(task)
        _save(d)
        return task


def tasks(include_done: bool = True) -> list[dict]:
    with _LOCK:
        t = _load()["tasks"]
    return t if include_done else [x for x in t if not x.get("done")]


def set_task_done(task_id: int, done: bool) -> None:
    with _LOCK:
        d = _load()
        for t in d["tasks"]:
            if t["id"] == task_id:
                t["done"] = bool(done)
        _save(d)


def delete_task(task_id: int) -> None:
    with _LOCK:
        d = _load()
        d["tasks"] = [t for t in d["tasks"] if t["id"] != task_id]
        _save(d)


# ── notes ──────────────────────────────────────────────────────────────────────
def add_note(text: str) -> dict | None:
    text = " ".join((text or "").split())
    if not text:
        return None
    with _LOCK:
        d = _load()
        note = {"id": _new_id(d), "text": text[:2000], "ts": time.time()}
        d["notes"].append(note)
        _save(d)
        return note


def notes() -> list[dict]:
    with _LOCK:
        return list(reversed(_load()["notes"]))      # newest first


def delete_note(note_id: int) -> None:
    with _LOCK:
        d = _load()
        d["notes"] = [n for n in d["notes"] if n["id"] != note_id]
        _save(d)


# ── calendar events ────────────────────────────────────────────────────────────
def add_event(day: str, title: str, at: str = "") -> dict | None:
    """`day` is YYYY-MM-DD, `at` an optional HH:MM."""
    title = " ".join((title or "").split())
    try:
        datetime.strptime(day, "%Y-%m-%d")
    except (TypeError, ValueError):
        return None
    if not title:
        return None
    with _LOCK:
        d = _load()
        ev = {"id": _new_id(d), "day": day, "at": at, "title": title[:200]}
        d["events"].append(ev)
        _save(d)
        return ev


def events_on(day: str) -> list[dict]:
    with _LOCK:
        return sorted((e for e in _load()["events"] if e["day"] == day), key=lambda e: e.get("at", ""))


def upcoming_events(limit: int = 5, today: date | None = None) -> list[dict]:
    today_s = (today or date.today()).isoformat()
    with _LOCK:
        evs = [e for e in _load()["events"] if e["day"] >= today_s]
    return sorted(evs, key=lambda e: (e["day"], e.get("at", "")))[:limit]


def days_with_events(year: int, month: int) -> set[int]:
    prefix = f"{year:04d}-{month:02d}-"
    with _LOCK:
        return {int(e["day"][8:10]) for e in _load()["events"] if e["day"].startswith(prefix)}


def delete_event(event_id: int) -> None:
    with _LOCK:
        d = _load()
        d["events"] = [e for e in d["events"] if e["id"] != event_id]
        _save(d)


_EV_RE = re.compile(r"^\s*(\d{1,2})[./](\d{1,2})(?:[./](\d{2,4}))?\s+(?:(\d{1,2}):(\d{2})\s+)?(.+?)\s*$")


def parse_event(text: str, today: date | None = None):
    """'25.10 15:30 Встреча' -> ('2026-10-25', '15:30', 'Встреча'); None if it does not parse.
    Without a year, a date that already passed this year means next year."""
    m = _EV_RE.match(text or "")
    if not m:
        return None
    today = today or date.today()
    day, month, year, hh, mm, title = m.groups()
    try:
        if year:
            y = int(year) + (2000 if len(year) == 2 else 0)
            d = date(y, int(month), int(day))
        else:
            d = date(today.year, int(month), int(day))
            if d < today:
                d = date(today.year + 1, int(month), int(day))
        at = f"{int(hh):02d}:{mm}" if hh else ""
        if hh and not (0 <= int(hh) <= 23 and 0 <= int(mm) <= 59):
            return None
    except ValueError:
        return None
    return d.isoformat(), at, title
