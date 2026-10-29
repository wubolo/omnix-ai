"""Долговременная память: SQLite + FTS5 (локально, без внешних баз).

- facts: факты о пользователе (авто-извлечение из диалогов)
- messages: история диалогов с временной шкалой
Поиск по смыслу слов — через FTS5 (быстро, офлайн).
"""
import os
import re
import sqlite3
import threading
import time
from pathlib import Path

_DB = Path(os.environ.get("AICOMPANION_DATA", Path.home() / ".ai_companion")) / "memory.db"
_lock = threading.Lock()

EXTRACT_PROMPT = (
    "Из диалога выпиши устойчивые факты о пользователе (предпочтения, проекты, имена, "
    "часто используемый софт). По одному короткому факту на строку, без нумерации. "
    "Если фактов нет — ответь словом НЕТ.\n\n{dialog}"
)


def _conn():
    _DB.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(_DB)
    c.executescript("""
    CREATE TABLE IF NOT EXISTS facts(id INTEGER PRIMARY KEY, text TEXT UNIQUE, ts REAL);
    CREATE VIRTUAL TABLE IF NOT EXISTS facts_fts USING fts5(text, content='facts', content_rowid='id');
    CREATE TABLE IF NOT EXISTS messages(id INTEGER PRIMARY KEY, role TEXT, text TEXT, ts REAL);
    CREATE VIRTUAL TABLE IF NOT EXISTS msg_fts USING fts5(text, content='messages', content_rowid='id');
    """)
    return c


def _q(text):
    words = re.findall(r"\w+", text.lower())
    # префиксный поиск по основе слова: «ассистент» находит «ассистента»
    return " OR ".join(f'"{w[:max(4, len(w) - 2)]}"*' for w in words[:12] if len(w) > 2)


def add_message(role, text):
    if not text.strip():
        return
    with _lock, _conn() as c:
        cur = c.execute("INSERT INTO messages(role,text,ts) VALUES(?,?,?)", (role, text, time.time()))
        c.execute("INSERT INTO msg_fts(rowid,text) VALUES(?,?)", (cur.lastrowid, text))


def add_fact(text):
    text = text.strip(" -•\t")
    if len(text) < 4:
        return False
    with _lock, _conn() as c:
        try:
            cur = c.execute("INSERT INTO facts(text,ts) VALUES(?,?)", (text, time.time()))
        except sqlite3.IntegrityError:
            return False
        c.execute("INSERT INTO facts_fts(rowid,text) VALUES(?,?)", (cur.lastrowid, text))
        return True


def extract_facts(dialog, ask_llm):
    """ask_llm(prompt)->str — любая функция вашей модели. Возвращает число новых фактов."""
    reply = ask_llm(EXTRACT_PROMPT.format(dialog=dialog[-6000:])) or ""
    if reply.strip().upper().startswith("НЕТ"):
        return 0
    return sum(add_fact(line) for line in reply.splitlines())


def search_facts(query, limit=8):
    q = _q(query)
    if not q:
        return []
    with _lock, _conn() as c:
        rows = c.execute("SELECT f.text FROM facts_fts JOIN facts f ON f.id=facts_fts.rowid "
                         "WHERE facts_fts MATCH ? ORDER BY rank LIMIT ?", (q, limit)).fetchall()
    return [r[0] for r in rows]


def all_facts():
    with _lock, _conn() as c:
        return [r[0] for r in c.execute("SELECT text FROM facts ORDER BY ts DESC")]


def delete_fact(text):
    with _lock, _conn() as c:
        row = c.execute("SELECT id FROM facts WHERE text=?", (text,)).fetchone()
        if row:
            c.execute("INSERT INTO facts_fts(facts_fts,rowid,text) VALUES('delete',?,?)", (row[0], text))
            c.execute("DELETE FROM facts WHERE id=?", (row[0],))


def search_history(query, limit=20):
    q = _q(query)
    if not q:
        return []
    with _lock, _conn() as c:
        return c.execute("SELECT m.ts,m.role,m.text FROM msg_fts JOIN messages m ON m.id=msg_fts.rowid "
                         "WHERE msg_fts MATCH ? ORDER BY m.ts DESC LIMIT ?", (q, limit)).fetchall()


def timeline(days=7, limit=200):
    """Сообщения по дням для вкладки «История»: [(дата, [(время, роль, текст)])]."""
    since = time.time() - days * 86400
    with _lock, _conn() as c:
        rows = c.execute("SELECT ts,role,text FROM messages WHERE ts>? ORDER BY ts DESC LIMIT ?",
                         (since, limit)).fetchall()
    out = {}
    for ts, role, text in rows:
        out.setdefault(time.strftime("%d.%m.%Y", time.localtime(ts)), []).append(
            (time.strftime("%H:%M", time.localtime(ts)), role, text))
    return list(out.items())


def prompt_block(user_text, limit=6):
    """Блок для системного промпта: релевантные факты."""
    facts = search_facts(user_text, limit)
    return ("Что известно о пользователе:\n- " + "\n- ".join(facts)) if facts else ""
