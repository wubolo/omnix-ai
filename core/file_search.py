"""
core/file_search.py — «найди файл договор».

Looks through the usual personal folders (Desktop, Documents, Downloads, Pictures,
Videos, Music and OneDrive versions of them) for file or folder names that contain
every word you said, newest first. A time and count limit keeps it from ever hanging.
"""
from __future__ import annotations

import os
import time
from pathlib import Path

from core.custom_commands import norm

_SKIP_DIRS = {"node_modules", ".git", "__pycache__", "appdata", "$recycle.bin", "venv", ".venv", "site-packages"}


def default_roots() -> list[Path]:
    home = Path.home()
    names = ["Desktop", "Documents", "Downloads", "Pictures", "Videos", "Music",
             "Рабочий стол", "Документы", "Загрузки"]
    roots: list[Path] = []
    for base in (home, home / "OneDrive"):
        for n in names:
            p = base / n
            if p.is_dir() and p not in roots:
                roots.append(p)
    return roots


def find_files(query: str, roots: list[Path] | None = None, limit: int = 5,
               want: str = "any", max_entries: int = 80_000, seconds: float = 3.0) -> list[str]:
    """Paths whose name holds all words of `query`. want: 'file' | 'dir' | 'any'."""
    words = norm(query).split()
    if not words:
        return []
    roots = roots if roots is not None else default_roots()
    deadline = time.monotonic() + seconds
    seen = 0
    hits: list[tuple[int, float, str]] = []
    stack = [str(r) for r in roots]
    while stack and seen < max_entries and time.monotonic() < deadline:
        d = stack.pop()
        try:
            it = os.scandir(d)
        except OSError:
            continue
        with it:
            for e in it:
                seen += 1
                try:
                    is_dir = e.is_dir(follow_symlinks=False)
                except OSError:
                    continue
                name = e.name
                if is_dir:
                    if name.lower() in _SKIP_DIRS or name.startswith("."):
                        continue
                    stack.append(e.path)
                    if want == "file":
                        continue
                elif want == "dir":
                    continue
                stem = norm(os.path.splitext(name)[0] if not is_dir else name)
                if all(w in stem for w in words):
                    rank = 0 if stem == " ".join(words) else (1 if stem.startswith(words[0]) else 2)
                    try:
                        mtime = e.stat().st_mtime
                    except OSError:
                        mtime = 0.0
                    hits.append((rank, -mtime, e.path))
    hits.sort()
    return [p for _, _, p in hits[:limit]]
