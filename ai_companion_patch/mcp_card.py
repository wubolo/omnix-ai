"""Карточка «MCP» для страницы настроек.

    from mcp_card import McpCard
    layout.addWidget(McpCard(shell))
"""
import threading

from PyQt6.QtCore import QObject, Qt, pyqtSignal
from PyQt6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QLineEdit,
                             QPushButton, QVBoxLayout, QWidget)

from .mcp_manager import MCP


class _Bus(QObject):
    done = pyqtSignal()
    status = pyqtSignal(str)


class McpCard(QFrame):
    def __init__(self, shell=None, parent=None):
        super().__init__(parent)
        self.shell = shell
        self.setObjectName("glassCard")
        self._bus = _Bus()
        self._bus.done.connect(self.reload)
        self._bus.status.connect(self.status_text)

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 16)
        root.setSpacing(10)
        t = QLabel("MCP-серверы")
        t.setObjectName("cardTitle")
        hint = QLabel("Подключайте инструменты по протоколу MCP: файлы, браузер, базы данных и др.")
        hint.setObjectName("dim")
        hint.setWordWrap(True)
        root.addWidget(t)
        root.addWidget(hint)

        self.list_box = QVBoxLayout()
        self.list_box.setSpacing(6)
        root.addLayout(self.list_box)

        self.name = QLineEdit(); self.name.setPlaceholderText("Название (files)")
        self.cmd = QLineEdit(); self.cmd.setPlaceholderText("Команда (npx)")
        self.args = QLineEdit(); self.args.setPlaceholderText("Аргументы через пробел: -y @modelcontextprotocol/server-filesystem C:/")
        for w in (self.name, self.cmd, self.args):
            root.addWidget(w)
        add = QPushButton("Добавить и проверить")
        add.setCursor(Qt.CursorShape.PointingHandCursor)
        add.clicked.connect(self._add)
        root.addWidget(add)

        self.status = QLabel("")
        self.status.setObjectName("dim")
        self.status.setWordWrap(True)
        root.addWidget(self.status)
        self.reload()

    def status_text(self, text):
        self.status.setText(str(text))

    def _changed(self):
        win = getattr(self.shell, "_win", None)
        cb = getattr(win, "on_mcp_changed", None)
        if callable(cb):
            cb()

    def reload(self):
        while self.list_box.count():
            w = self.list_box.takeAt(0).widget()
            if w:
                w.deleteLater()
        for cfg in MCP.load_config()["servers"]:
            self.list_box.addWidget(self._row(cfg))

    def _row(self, cfg):
        w = QWidget()
        h = QHBoxLayout(w)
        h.setContentsMargins(0, 0, 0, 0)
        name = cfg["name"]
        srv = MCP.servers.get(name)
        if srv:
            state = f"● {len(srv.tools)} инструм."
        elif name in MCP.errors:
            state = "● ошибка"
        else:
            state = "○ выкл."
        lab = QLabel(f"{name}   {state}")
        h.addWidget(lab, 1)
        tog = QPushButton("Выключить" if cfg.get("enabled", True) else "Включить")
        tog.clicked.connect(lambda: self._toggle(name))
        rm = QPushButton("Удалить")
        rm.clicked.connect(lambda: self._remove(name))
        h.addWidget(tog); h.addWidget(rm)
        if name in MCP.errors:
            lab.setToolTip(MCP.errors[name])
        return w

    def _save(self, cfg_all):
        MCP.save_config(cfg_all)

    def _add(self):
        name, cmd = self.name.text().strip(), self.cmd.text().strip()
        if not name or not cmd:
            self.status.setText("Укажите название и команду.")
            return
        cfg_all = MCP.load_config()
        cfg_all["servers"] = [s for s in cfg_all["servers"] if s["name"] != name]
        cfg = {"name": name, "command": cmd, "args": self.args.text().split(), "env": {}, "enabled": True}
        cfg_all["servers"].append(cfg)
        self._save(cfg_all)
        self.status.setText("Запускаю сервер…")
        self._start_async(cfg)

    def _start_async(self, cfg):
        def run():
            s = MCP.start_one(cfg)
            self._bus.status.emit(
                f"Готово: {len(s.tools)} инструментов." if s else f"Ошибка: {MCP.errors.get(cfg['name'])}")
            self._bus.done.emit()
            self._changed()
        threading.Thread(target=run, daemon=True).start()

    def _toggle(self, name):
        cfg_all = MCP.load_config()
        for s in cfg_all["servers"]:
            if s["name"] == name:
                s["enabled"] = not s.get("enabled", True)
                (self._start_async(s) if s["enabled"] else MCP.stop_one(name))
        self._save(cfg_all)
        self.reload()
        self._changed()

    def _remove(self, name):
        MCP.stop_one(name)
        cfg_all = MCP.load_config()
        cfg_all["servers"] = [s for s in cfg_all["servers"] if s["name"] != name]
        self._save(cfg_all)
        self.reload()
        self._changed()
