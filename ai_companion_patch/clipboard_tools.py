"""Буфер обмена + глобальные хоткеи: перевести / объяснить код / поправить письмо."""
import threading

import pyperclip
from pynput import keyboard

ACTIONS = {
    "translate": "Переведи на русский (если текст русский — на английский), только перевод:\n\n{t}",
    "explain": "Объясни кратко и по делу, что делает этот код или текст:\n\n{t}",
    "polish": "Отредактируй письмо: исправь ошибки и сделай вежливо и ясно, верни только текст:\n\n{t}",
}


class ClipboardHotkeys:
    """hotkeys: {'<ctrl>+<alt>+t': 'translate', ...}; ask_llm(prompt)->str; on_result(action, text)."""

    def __init__(self, ask_llm, on_result, hotkeys=None):
        self.ask_llm, self.on_result = ask_llm, on_result
        self.hotkeys = hotkeys or {"<ctrl>+<alt>+t": "translate", "<ctrl>+<alt>+e": "explain",
                                   "<ctrl>+<alt>+p": "polish"}
        self._listener = None

    def _run(self, action):
        def work():
            text = pyperclip.paste().strip()
            if not text:
                return self.on_result(action, "Буфер обмена пуст.")
            try:
                self.on_result(action, self.ask_llm(ACTIONS[action].format(t=text[:8000])))
            except Exception as e:
                self.on_result(action, f"Ошибка: {e}")
        threading.Thread(target=work, daemon=True).start()

    def start(self):
        self._listener = keyboard.GlobalHotKeys({k: (lambda a=a: self._run(a)) for k, a in self.hotkeys.items()})
        self._listener.daemon = True
        self._listener.start()

    def stop(self):
        if self._listener:
            self._listener.stop()
