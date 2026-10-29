"""
core/local_commands.py — what can be done without asking the model.

Every phrase used to travel: microphone -> Whisper -> Gemini -> tool call -> action.
That is slow for "открой Steam" and, worse, it lets the model *interpret* sounds
that were never a command (a TV, a half-heard sentence, a Whisper hallucination)
and act on them.

Now there are two stages:

  1. is_noise_transcript()  — drops what Whisper makes up from silence and noise
     ("Продолжение следует...", "Субтитры сделал ...", a lone "а").
  2. LocalRouter.handle()   — "открой / запусти / закрой <name>" is executed on
     the spot when <name> is an app or game this PC actually has (see
     core/app_catalog.py). Anything else returns None and goes to the model
     exactly as before, so "открой мне интересный факт" is still a conversation.
"""
from __future__ import annotations

import os
import re
from typing import Optional

from core import app_catalog, confirm, custom_commands, desks, file_search, notes

# ── stage 1: Whisper noise ─────────────────────────────────────────────────────

_HALLUCINATIONS = (
    "продолжение следует", "субтитры сделал", "субтитры создавал", "субтитры подогнал",
    "редактор субтитров", "корректор а", "спасибо за просмотр", "спасибо за внимание",
    "подписывайтесь на канал", "подписывайтесь на мой канал", "ставьте лайки",
    "dimatorzok", "amara.org",
    "thanks for watching", "thank you for watching", "subtitles by", "please subscribe",
)


def is_noise_transcript(text: str) -> bool:
    t = re.sub(r"[^\w\s]", " ", (text or "").lower().replace("ё", "е"))
    t = " ".join(t.split())
    if len(t) < 2:
        return True
    if any(h in t for h in _HALLUCINATIONS) and len(t) < 90:
        return True
    words = t.split()
    # "а а а а а" / "да да да да" — a looping decoder, not a sentence.
    if len(words) >= 4 and len(set(words)) == 1 and len(words[0]) <= 3:
        return True
    return False


# ── stage 2: app / game commands ───────────────────────────────────────────────

_LEAD = r"^(?:(?:ну|слушай|давай|пожалуйста|а|и)[,\s]+)*"
_OPEN_RE = re.compile(
    _LEAD + r"(?:открой|открыть|запусти|запустить|запускай|стартани|включи|"
    r"open|launch|start|run)[,\s]+(?:(?:мне|пожалуйста|please)[,\s]+)*(.+)$")
_CLOSE_RE = re.compile(
    _LEAD + r"(?:закрой|закрыть|заверши|завершить|останови|выключи|"
    r"close|quit|kill|stop)[,\s]+(?:(?:мне|пожалуйста|please)[,\s]+)*(.+)$")
_FILLER = re.compile(r"^(?:приложение|программу|программа|игру|игра|app|the|game|program)\s+|"
                     r"\s+(?:пожалуйста|please|плиз)$")


def _target(raw: str) -> str:
    t = re.sub(r"[.!?,]+$", "", raw.strip().lower())
    prev = None
    while prev != t:
        prev, t = t, _FILLER.sub("", t).strip()
    return t


def _cyr(text: str) -> bool:
    return bool(re.search(r"[а-яА-ЯёЁ]", text))


_TASK_RE = re.compile(_LEAD + r"(?:добавь|запиши|создай|поставь|new|add)\s+(?:мне\s+)?(?:новую\s+)?(?:задачу|дело|task)[:,\s]+(.+)$")
_NOTE_RE = re.compile(_LEAD + r"(?:запиши|сделай|добавь|создай|сохрани|note)\s+(?:мне\s+)?(?:новую\s+)?(?:заметку|заметка)[:,\s]+(.+)$")
_TASKS_LIST_RE = re.compile(_LEAD + r"(?:что\s+(?:у\s+меня\s+)?в\s+(?:списке\s+)?задач\w*|мои\s+задачи|какие\s+(?:у\s+меня\s+)?задачи|что\s+мне\s+(?:сегодня\s+)?делать)\??$")
_FIND_RE = re.compile(_LEAD + r"(?:найди|поищи|ищи|найти)\s+(?:мне\s+)?(файл|документ|папку|папка|презентацию|фото|картинку|видео)\s+(.+)$")
_OPENFILE_RE = re.compile(_LEAD + r"(?:открой|открыть|запусти)\s+(?:мой\s+)?(?:файл|документ|презентацию)\s+(.+)$")
_EVENT_RE = re.compile(_LEAD + r"(?:добавь|запиши|создай|поставь)\s+(?:мне\s+)?(?:новое\s+)?(?:событие|встречу|напоминание)[:,\s]+(.+)$")
_DESK_RE = re.compile(_LEAD + r"(?:открой|покажи|переключись\s+на|перейди\s+на|включи)\s+стол\s+(.+)$")
_READ_RE = re.compile(_LEAD + r"(?:прочитай|прочти|озвучь|read)\s+(?:мне\s+)?(?:вслух|буфер(?:\s+обмена)?|скопированное|то,?\s+что\s+скопировано)\s*$")


class LocalRouter:
    """Returns the sentence to say back when it handled the phrase, else None."""

    def __init__(self, catalog: Optional[app_catalog.AppCatalog] = None, logger=print):
        self.catalog = catalog or app_catalog.AppCatalog(logger=logger)
        self._log = logger
        self.catalog.refresh_async()
        # The UI / clipboard are not known here; main.py plugs them in.
        self.desk_cb = None            # callable(name: str) -> bool, switches the Home desk
        self.clipboard_fn = None       # callable() -> str
        self.backends = None           # keyboard/mouse/volume backends; None = the real ones
        self.file_roots = None         # folders to search; None = the usual personal ones

    def handle(self, text: str) -> Optional[str]:
        clean = " ".join((text or "").strip().split())
        low = clean.lower()

        reply = self._notes_and_desks(clean, low)
        if reply is not None:
            return reply

        hit = custom_commands.match(clean)          # your commands and the packs
        if hit:
            return self._run_custom(hit[0], hit[1])

        for regex, action in ((_OPEN_RE, self._open), (_CLOSE_RE, self._close)):
            m = regex.match(low)
            if not m:
                continue
            target = _target(m.group(1))
            # A long tail is a sentence, not an app name.
            if not target or len(target.split()) > 4:
                return None
            entry = self.catalog.resolve(target)
            if entry is None:
                return None
            return action(entry, ru=_cyr(clean))
        return None

    def _files(self, m, low: str) -> str:
        from core.custom_commands import Backends
        be = self.backends or Backends()
        opening = _OPENFILE_RE.match(low) is not None and _FIND_RE.match(low) is None
        kind = "any" if opening else m.group(1)
        query = m.group(2) if not opening else m.group(1)
        want = "dir" if kind in ("папку", "папка") else ("file" if kind != "any" else "any")
        found = file_search.find_files(query, roots=self.file_roots, want=want)
        if not found:
            return f"Не нашла «{query}» в личных папках."
        names = ", ".join(os.path.basename(p) for p in found[:3])
        try:
            if opening:
                be.open_path(found[0])
                return f"Открываю {os.path.basename(found[0])}."
            be.reveal(found[0])
        except Exception as exc:
            return f"Нашла, но не смогла показать: {exc}"
        more = f" Всего подходящих: {len(found)}." if len(found) > 1 else ""
        return f"Нашла: {names}. Показываю первый.{more}"

    def _run_custom(self, cmd: dict, params: dict) -> str:
        name = cmd["name"]

        def run() -> str:
            errors = custom_commands.run_actions(cmd["actions"], params, self.backends)
            self._log(f"[Local] command {name!r} params={params} errors={errors}")
            return "done" if not errors else "problems: " + "; ".join(errors)

        if cmd.get("confirm"):
            detail = ", ".join(a["type"] for a in cmd["actions"])
            confirm.request(f"cmd:{cmd['id']}", name, detail, run)
            return f"Нужно подтверждение: {name}. Скажи «да» или нажми на экране."
        errors = custom_commands.run_actions(cmd["actions"], params, self.backends)
        self._log(f"[Local] command {name!r} params={params} errors={errors}")
        if errors:
            return f"Не получилось выполнить «{name}»: {errors[0]}"
        return f"Выполнено: {name}."

    # ── tasks, notes, desks, read aloud ───────────────────────────────────────
    def _notes_and_desks(self, clean: str, low: str) -> Optional[str]:
        m = _NOTE_RE.match(low)
        if m:
            body = re.sub(r"[.!?]+$", "", clean[len(clean) - len(m.group(1)):]).strip()
            note = notes.add_note(body)
            return f"Записала заметку: {note['text']}" if note else None
        m = _TASK_RE.match(low)
        if m:
            body = re.sub(r"[.!?]+$", "", clean[len(clean) - len(m.group(1)):]).strip()
            task = notes.add_task(body)
            return f"Добавлено в задачи: {task['text']}" if task else None
        m = _FIND_RE.match(low) or _OPENFILE_RE.match(low)
        if m:
            return self._files(m, low)
        m = _EVENT_RE.match(low)
        if m:
            parsed = notes.parse_event(clean[len(clean) - len(m.group(1)):])
            if parsed is None:
                return "Не поняла дату. Скажи, например: добавь событие 25.10 15:30 встреча."
            day, at, title = parsed
            notes.add_event(day, title, at)
            return f"Добавлено в календарь: {title}, {day[8:10]}.{day[5:7]}" + (f" в {at}" if at else "") + "."
        if _TASKS_LIST_RE.match(low):
            open_tasks = notes.tasks(include_done=False)
            if not open_tasks:
                return "Список задач пуст."
            shown = "; ".join(t["text"] for t in open_tasks[:5])
            more = f" И ещё {len(open_tasks) - 5}." if len(open_tasks) > 5 else ""
            return f"Задач: {len(open_tasks)}. {shown}.{more}"
        m = _DESK_RE.match(low)
        if m:
            desk = desks.find_desk(m.group(1))
            if desk is None:
                return None                      # not one of our desks: let the model answer
            ok = bool(self.desk_cb and self.desk_cb(desk["name"]))
            return f"Открываю стол «{desk['name']}»." if ok else None
        if _READ_RE.match(low):
            try:
                text_ = (self.clipboard_fn() if self.clipboard_fn else "") or ""
            except Exception:
                text_ = ""
            text_ = " ".join(text_.split())
            if not text_:
                return "В буфере обмена нет текста."
            return text_[:2500]
        return None

    def _open(self, entry: app_catalog.Entry, ru: bool) -> str:
        status = app_catalog.launch(entry)
        self._log(f"[Local] open {entry.name} ({entry.kind}) -> {status}")
        if status.lower().startswith(("failed", "could not")):
            return (f"Не получилось открыть {entry.name}." if ru
                    else f"I could not open {entry.name}.")
        return f"Открываю {entry.name}." if ru else f"Opening {entry.name}."

    def _close(self, entry: app_catalog.Entry, ru: bool) -> str:
        n = app_catalog.close(entry)
        self._log(f"[Local] close {entry.name} ({entry.kind}) -> {n} process(es)")
        if n == 0:
            return (f"{entry.name} сейчас не запущен." if ru
                    else f"{entry.name} is not running.")
        return f"Закрываю {entry.name}." if ru else f"Closing {entry.name}."
