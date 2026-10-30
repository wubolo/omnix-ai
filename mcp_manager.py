"""Минимальный MCP-клиент (stdio, JSON-RPC) без внешних зависимостей.

Конфиг: <папка данных>/mcp_servers.json
  {"servers": [{"name": "files", "command": "npx",
                "args": ["-y", "@modelcontextprotocol/server-filesystem", "C:/Users/me"],
                "env": {}, "enabled": true}]}

Для ассистента:
  tools = MCP.tool_declarations()          # добавить в _build_config (функции Gemini)
  result = MCP.call("files__read_file", {"path": "..."})   # вызвать из _execute_tool
"""
import json
import os
import subprocess
import threading
from pathlib import Path

PROTOCOL = "2024-11-05"
_NO_WINDOW = 0x08000000 if os.name == "nt" else 0


def _config_path() -> Path:
    base = Path(os.environ.get("AICOMPANION_DATA", Path.home() / ".ai_companion"))
    base.mkdir(parents=True, exist_ok=True)
    return base / "mcp_servers.json"


class _Server:
    def __init__(self, cfg):
        self.cfg = cfg
        self.name = cfg["name"]
        self.proc = None
        self.tools = []
        self._id = 0
        self._lock = threading.Lock()

    def start(self, timeout=30):
        env = {**os.environ, **{k: str(v) for k, v in cfg_env(self.cfg).items()}}
        self.proc = subprocess.Popen(
            [self.cfg["command"], *self.cfg.get("args", [])],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            env=env, creationflags=_NO_WINDOW, text=True, encoding="utf-8", shell=(os.name == "nt"),
        )
        self.request("initialize", {
            "protocolVersion": PROTOCOL, "capabilities": {},
            "clientInfo": {"name": "OMNIX AI", "version": "1.0"}}, timeout)
        self._send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        self.tools = self.request("tools/list", {}, timeout).get("tools", [])

    def _send(self, msg):
        self.proc.stdin.write(json.dumps(msg) + "\n")
        self.proc.stdin.flush()

    def request(self, method, params, timeout=60):
        with self._lock:
            self._id += 1
            rid = self._id
            self._send({"jsonrpc": "2.0", "id": rid, "method": method, "params": params})
            result = {}

            def reader():
                nonlocal result
                while True:
                    line = self.proc.stdout.readline()
                    if not line:
                        result = {"error": {"message": "сервер закрыл соединение"}}
                        return
                    try:
                        data = json.loads(line)
                    except ValueError:
                        continue
                    if data.get("id") == rid:
                        result = data
                        return

            t = threading.Thread(target=reader, daemon=True)
            t.start()
            t.join(timeout)
            if t.is_alive():
                raise TimeoutError(f"MCP '{self.name}': нет ответа на {method}")
            if "error" in result:
                raise RuntimeError(result["error"].get("message", "ошибка MCP"))
            return result.get("result", {})

    def stop(self):
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
        self.proc = None


def cfg_env(cfg):
    return cfg.get("env") or {}


class McpManager:
    def __init__(self):
        self.servers = {}
        self.errors = {}

    # ---- конфиг ----
    def load_config(self):
        p = _config_path()
        if not p.exists():
            return {"servers": []}
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except ValueError:
            return {"servers": []}

    def save_config(self, cfg):
        _config_path().write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")

    # ---- жизненный цикл ----
    def start_enabled(self):
        for cfg in self.load_config()["servers"]:
            if cfg.get("enabled", True):
                self.start_one(cfg)

    def start_one(self, cfg):
        self.stop_one(cfg["name"])
        try:
            s = _Server(cfg)
            s.start()
            self.servers[cfg["name"]] = s
            self.errors.pop(cfg["name"], None)
            return s
        except Exception as e:
            self.errors[cfg["name"]] = str(e)
            return None

    def stop_one(self, name):
        s = self.servers.pop(name, None)
        if s:
            s.stop()

    def stop_all(self):
        for n in list(self.servers):
            self.stop_one(n)

    # ---- для ассистента ----
    def tool_declarations(self):
        out = []
        for s in self.servers.values():
            for t in s.tools:
                out.append({
                    "name": f"{s.name}__{t['name']}",
                    "description": t.get("description", "")[:500],
                    "parameters": t.get("inputSchema", {"type": "object", "properties": {}}),
                })
        return out

    def call(self, full_name, args):
        server, _, tool = full_name.partition("__")
        s = self.servers.get(server)
        if not s:
            return f"MCP-сервер '{server}' не запущен"
        res = s.request("tools/call", {"name": tool, "arguments": args or {}}, timeout=120)
        parts = [c.get("text", "") for c in res.get("content", []) if c.get("type") == "text"]
        return "\n".join(parts) or json.dumps(res, ensure_ascii=False)


MCP = McpManager()
