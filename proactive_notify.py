"""Проактивные уведомления через трей: разминка, напоминания."""
import threading
import time

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QSystemTrayIcon


class Proactive:
    def __init__(self, tray: QSystemTrayIcon, work_minutes=120):
        self.tray = tray
        self.work_ms = work_minutes * 60_000
        self.reminders = []  # (timestamp, text)
        self._work = QTimer(); self._work.timeout.connect(self._break)
        self._tick = QTimer(); self._tick.timeout.connect(self._check)

    def start(self):
        self._work.start(self.work_ms)
        self._tick.start(15_000)

    def stop(self):
        self._work.stop(); self._tick.stop()

    def notify(self, text, title="OMNIX AI"):
        self.tray.showMessage(title, text, QSystemTrayIcon.MessageIcon.Information, 8000)

    def remind_in(self, minutes, text):
        self.reminders.append((time.time() + minutes * 60, text))

    def _break(self):
        self.notify("Вы за ПК уже давно — пора сделать разминку.")

    def _check(self):
        now = time.time()
        due = [r for r in self.reminders if r[0] <= now]
        self.reminders = [r for r in self.reminders if r[0] > now]
        for _, text in due:
            self.notify(f"Напоминание: {text}")
