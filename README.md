# 🤖 OMNIX AI

### Ваш голосовой ИИ-компаньон для компьютера · Your voice-powered desktop assistant

[⬇️ Скачать AICompanion.exe для Windows](https://github.com/wubolo/omnix-ai/raw/refs/heads/main/AICompanion.exe)

**Русский**

OMNIX AI — настольный голосовой помощник с живым аватаром. Общайтесь с ним голосом, получайте ответы вслух и поручайте повседневные задачи за компьютером. Компаньон помогает работать с экраном и приложениями, запоминает полезные сведения, расширяется плагинами и позволяет выбрать микрофон, наушники и голос. Для важных действий требуется подтверждение; настройки и память хранятся на вашем устройстве.

**English**

OMNIX AI is a voice-first desktop assistant with an animated avatar. Talk naturally, hear spoken replies, and ask it to help with everyday tasks on your computer. It can work with your screen and apps, remember useful details, grow through plugins, and adapt to your microphone, speakers, and preferred voice. Important actions require your confirmation, while settings and memory stay on your device.

> 🎙️ Natural voice chat · 👀 Screen-aware help · 🖥️ Desktop actions · 🧠 Personal memory · 🧩 Extensible plugins

---## ✨ Overview

OMNIX AI is a real-time voice AI assistant with a holographic avatar, lip-sync, local wake word, plugin system and full computer control. It hears you, sees your screen, speaks back and does things on your machine.

---

## 🚀 Capabilities

### Core Features
| Feature | Description |
|---|---|
| 🧑‍🎤 Holographic Avatar | An animated human head in the HUD — real facial geometry, lit and drawn in software, no GPU or extra packages |
| 👄 Real Lip-Sync | ~50 mouth shapes a second from the audio's formants **and** the transcript — closures, spreads and rounds, not a volume meter |
| 🌍 Language-Free Mouth | Articulation is derived by Unicode reduction, so Latin, Cyrillic and Greek scripts all work from one rule set — and scripts that hide pronunciation fall back cleanly |
| 🙂 Facial Acting | Brows track the phrase, gaze saccades between fixations, natural blinking, a small nod on stressed syllables |
| 😐 Face as Status | Looks away while thinking, meets your eyes while listening, lids fall while asleep, glances down at new content |
| 🎚️ Push-to-Talk | Hold **Ctrl+Space** and the mic opens — closed the rest of the time. Truly global on Windows, window-scoped elsewhere |
| 🔇 Self-Echo Guard | Never answers its own last sentence: the tail of its own voice is recognised and dropped without muting you |
| 🪪 Runtime Self-Knowledge | Name, OS, abilities **and limits** are generated from the live system each session — rename it or add a plugin and it knows |
| 🎙️ Wake Word | Local **"Hey Jarvis"** detection — sleeps until called, auto-sleeps after 2 min of silence, and never streams audio while asleep |
| ⚡ Instant Acknowledgment | Speaks a short, context-aware reply in **your language** the instant a longer task starts — no more silent waiting |
| 🚀 Faster Live Engine | Runs on **Gemini 3.1 Flash Live** — roughly 2× faster time-to-first-word than the previous model |
| 🧩 Self-Describing Skills | Every bundled skill declares its own `TOOL` dict + handler and is auto-discovered at launch — adding one is a single file |
| 🧠 Recallable Memory | No size limit and nothing silently forgotten — the prompt carries what fits, the rest is looked up on demand from a local search |
| 👁️ Memory Panel | See every fact OMNIX AI has stored about you, when it learned it, and delete any of it in one click |
| ↩️ Undo | Take back what the assistant did — files it moved, renamed, created or wrote, and settings it changed |
| ⚠️ Real Confirmation | Shutdown, restart and WiFi wait for a button **you** press — the model cannot confirm its own irreversible actions |
| 🎧 Audio Device Picker | Choose the microphone and speakers by name, filtered to the short list your OS shows — and measured, so every entry actually works |
| 🔗 Session Continuity | A dropped connection, a voice change or a device change no longer wipes the conversation |
| 🧩 Plugin System | Drop a single `.py` file into `plugins/` — OMNIX AI learns a new skill on next launch |
| 📺 Video on the HUD | Plays YouTube, a local file or any video URL **where the avatar sits** — starts muted, sound on request |
| 🪜 Model Ladder | Nine Gemini models in one measured order — a quota, a timeout or an outage steps to the next rung instead of failing |
| 🎙️ Real-time Voice | Gemini Live conversation with locally synthesized Silero Russian speech |
| 🗣️ Local Whisper Recognition | PC microphone speech is transcribed on-device with faster-whisper, then sent to Gemini as text |
| 🇷🇺 Russian-First Voice | Russian is the default conversation language, with locally configured Russian Whisper recognition and clearer spoken replies |
| 🔊 Silero Russian TTS | Silero v5.5 produces Russian speech locally; choose xenia, baya, kseniya, aidar or eugene |
| 🎨 Live Theming | Recolour the entire HUD from a hue wheel or hex — the avatar retints with it |
| 〰️ Reactive HUD | Waveform pulses to real audio — your mic while listening, OMNIX AI while speaking |
| 🎙️ Voice Picker | Choose a Silero Russian speaker from the UI |
| ♾️ Unlimited Sessions | Sliding-window context compression — one conversation can last for hours |
| 🖥️ System Control | Launch apps, adjust volume/brightness, WiFi, shortcuts, power — all by voice |
| 🧩 Autonomous Tasks | High-level planning for complex multi-step goals via agent mode |
| 👁️ Visual Awareness | Screen capture and webcam vision piped into your main Gemini session, labelled by source |
| 🧠 Persistent Memory | Deeply remembers projects, preferences, and personal context across sessions |
| ⌨️ Hybrid Input | Seamlessly switch between keyboard typing and voice commands |
| 🌅 Morning Briefing | On first boot: greets you, reads the time, recaps yesterday, and fetches live news |
| 🔔 Proactive 2.0 | Time-aware, context-aware check-ins — knows the time of day, your projects, and what you've been discussing |
| 🗓️ Session Memory | Summarises each conversation and mentions it naturally next morning — consumed after use, never repeats |
| 👁️‍🗨️ Background Monitoring | User-configured topic watching — checks for new headlines once a day and alerts naturally |
| 📊 Hardware Monitoring | Continuous CPU, RAM, GPU and temperature telemetry with localized voice alerts |
| 🌤️ Weather Report | Live weather data for your city, personalized from memory |
| 🗺️ Dynamic Content Panel | Scrollable display layer beneath the HUD that renders web results, news, and search data |
| 🔍 Multi-Mode Web Search | `news` / `research` / `price` / `compare` / `search` — Gemini Grounded first, DDG fallback |
| ⏰ Smart Reminders | OS-native scheduled notifications (Windows Task Scheduler / macOS LaunchAgent / Linux systemd) |
| 📂 File Processor | Read, summarize, and answer questions about local files |
| 🧹 Safe Cleanup | Review old temporary files and large or old downloads; selected files go to the Recycle Bin |
| 🗑️ Empty Trash | Permanently empty the OS Recycle Bin / Trash only after an on-screen confirmation |
| 🌐 Browser Control | Open URLs, navigate tabs, and interact with the browser by voice |
| 📨 Send Message | Compose and send messages through WhatsApp, Telegram, and more |
| 🖱️ Desktop Control | Taskbar, window management, and desktop-level operations |
| 🧑‍💻 Silent Language Memory | Detects spoken language on first use — all future sessions adapt automatically |
| 📱 Remote Dashboard | Control the assistant from your phone via QR code pairing |
| ⚡ Auto-Start on Boot | Registers with the OS startup system (registry / LaunchAgent / .desktop) |
| 📋 Clipboard Intelligence | Copy any text → floating panel with Translate / Summarise / Explain / Fix |
| 🪪 Assistant Customization | Change the assistant name, your name, voice, and colour from the UI — takes effect immediately |

---

## 🆕 v5.5 — faster, fewer false triggers

- **Voice detection** (`core/vad.py`): the microphone opens for human speech, not for any loud sound. Uses WebRTC VAD (`webrtcvad-wheels`, tiny) or Silero VAD if torch is installed; falls back to the old volume threshold if neither is.
- **Local commands** (`core/local_commands.py`): "открой / запусти / закрой <программа или игра>" runs instantly without the model. Unknown names still go to the model, so ordinary conversation is not affected. Whisper's invented phrases ("Продолжение следует…") are dropped before they reach the model.
- **App & game catalog** (`core/app_catalog.py`): Steam libraries on every drive, Epic Games and Start-Menu shortcuts are indexed automatically (cached in `cache/app_catalog.json`). Russian speech matches English titles: "дота два" → Dota 2, "киберпанк" → Cyberpunk 2077. Own words: `data/app_aliases.json`, e.g. `{"моя катка": "Dota 2"}`.
- **Phrase cache + sentence streaming** (`core/tts.py`): replies are synthesized sentence by sentence, the first one plays while the next is prepared, and repeated sentences are read from `cache/tts/` (300 MB cap, oldest removed first).
- **Male voices**: Piper `dmitri` and `denis`, or Silero `aidar` and `eugene`. Two presets are built on them: `jarvis` (calm, slightly lowered, light AI-butler colouring) and `deep` (the lowest). Pick them under Settings → voice.
- **Game-safe confirmation** (`core/confirm.py`): when a full-screen game is in front, the on-screen CONFIRM banner is replaced by a spoken one — say «да» or «отмена». The answer comes from your microphone, never from the model.

## 🔧 v6.5

- **Voice typing**: «начни диктовку» → what you say is typed into the focused window (any program, any language). Say «запятая», «точка», «вопросительный знак», «новая строка», «новый абзац», «удали слово». «Закончи диктовку» stops. Also a switch on Home.
- **File search**: «найди файл договор», «найди папку проекты», «открой файл отчёт» — searches Desktop, Documents, Downloads, Pictures, Videos, Music (and OneDrive) and shows the first match in Explorer.
- **Action recording** (command editor → ⏺ Запись действий): the app minimises, you do the thing once, F8 stops; shortcuts, typing, clicks and pauses become actions. Needs `pynput` (in requirements.txt).
- **Fish Audio voice** (Settings → Speech): your key + optional voice model ID. Written from the public API description.
- **108 ready commands** in 10 packs: music, windows, browser, text/office, VS Code, Photoshop, YouTube, games, power.

## 🎛️ v6.4 — your own commands, voices, appearance

- **Command editor** (Commands page): name, activation phrases (`{n}` takes a number: «громкость на пятьдесят»), optional words, «confirm first», and a list of actions: launch a program, open a site, press keys, type text, click, volume, media keys, lock, sleep, shutdown, wait. **✦ Create with AI** builds a command from a description. 45 ready commands in 5 packs (music, windows, browser, editing, power), each pack has a switch.
- **Prefix mode** («Джарвис, включи музыку»): only phrases that start with the assistant's name are handled; words are configurable. Typed commands and the phone remote use the same local commands.
- **Speech engine**: Windows built-in voice (offline), Piper, OpenAI (own key), Silero. Voices follow the engine.
- **Interface**: theme colour, window transparency, animations, minimize to tray, live avatar (breathing circles) on the desktop.
- **Phone remote**: quick buttons (pause, next, louder, desktop, screenshot, lock) on the remote page.
- Settings file is now written atomically and under a lock.

## 🧩 v6.3 — desks, widgets, notes, pet

- **Desks and widgets** (Home → `+`): your own Home tabs. 12 starting presets (Work, Study, Games, Finance …) and 13 widgets: clock, weather, tasks, notes, calendar, exchange rates, system load, media keys, quick launch, command history, timer, pet, big circles. Pencil = edit mode: ◀ ▶ move, ⤢ resize, ✕ remove. Voice: «открой стол Игры».
- **Tasks, notes, calendar** (`core/notes.py`, `data/notes.json`): «добавь задачу …», «запиши заметку …», «добавь событие 25.10 15:30 …», «мои задачи».
- **Desktop pet** (`ui_pet.py`): four original pixel characters that walk, sit and dance to the voice. Settings → Pet.
- **Read aloud**: «прочитай вслух» reads the clipboard with the assistant's voice.
- **Lock when away** (Settings): locks Windows after N idle minutes.
- Weather uses Open-Meteo, rates use open.er-api.com (no keys needed).

## 🛠️ v6.2

- **Fixed:** with the new interface the first-run API-key card was created behind the hidden classic layout, so no key could be entered and the AI never started. The key card is now part of the new design (and saving a key no longer wipes your other settings).
- **New look for the rest:** Add-ons page with a real switch per plugin; the classic panels (plugin settings, devices, memory, customise, remote access, confirmations) now use the same dark-blue palette and a clean font.

## 🪶 v6.0 — Piper voice, no PyTorch

The default voice is now **Piper** (`piper-tts`, runs on onnxruntime): Russian voices `dmitri`, `denis` (male) and `irina`, plus the `jarvis` / `deep` presets. PyTorch (the biggest download) is no longer required. Install with `pip install -r requirements.txt -r requirements-voice.txt`; voice files go to `models/piper/` and are downloaded on first use. If Piper is missing the app uses Silero (`pip install -r requirements-silero.txt`); force an engine with `"tts_engine": "piper"` or `"silero"` in `config/api_keys.json`. `diagnose_voice.py` checks the whole chain step by step.

## 🖥️ v5.9 — new interface

The main interface uses a translucent liquid-glass style and a bottom navigation bar for Chat, Commands, Plugins, Help, Account and Settings. The OMNIX AI mark opens the home dashboard with command history and quick controls. The legacy menu is no longer exposed; configuration stored as `"ui_style": "classic"` is ignored.

## 📦 Windows installer and portable app

`packaging\build_installer.bat` builds `outputs\OMNIX-AI-Setup.exe` with NSIS from the already-built portable executable. The portable `outputs\AICompanion.exe` can also be launched directly without installation. The installer is per-user and creates Start-menu / desktop shortcuts. API keys are kept in the local `config\api_keys.json` and are never embedded in either executable.

## ⚡ Quick Start

```bash
git clone <your-repo-url>
cd omnix-ai
python setup.py        # installs deps for YOUR OS + the browser automation engine
python main.py
```

`setup.py` only ever installs what your operating system needs — the Windows-only libraries are skipped automatically on macOS and Linux, and vice-versa. It also checks your Python version up front, so a wrong interpreter fails with a sentence instead of a wall of pip output. Prefer to do it by hand? `pip install -r requirements.txt` works too.

The first launch downloads the Whisper `base` speech model (about 150 MB) and the Silero v5.5 Russian speech model once. PyTorch is installed by `setup.py`; after the model download, Silero speech synthesis runs locally. If the Silero download reports an SSL certificate error, check Windows date/time synchronization and install pending Windows updates; certificate verification remains enabled. If Whisper cannot load, the app reports the issue and falls back to Gemini's audio input. Cleanup scans only suggest candidates. Emptying the Recycle Bin / Trash requires a separate on-screen confirmation because the files cannot be restored afterward.

> ⚠️ **Installation Note:** If you hit a `ModuleNotFoundError` for an OS-specific package, install it with `pip install <module_name>`. The optional **wake word** engine is *not* installed here — grab it in one click from **⚙ → WAKE WORD** inside the app.

---

## 📋 Requirements

| Requirement | Details |
| --- | --- |
| **OS** | Windows 10/11, macOS, or Linux |
| **Python** | 3.11, 3.12 or 3.13 |
| **Microphone** | Required for voice interaction (and for the "Hey Jarvis" wake word) |
| **Speakers** | Required for voice replies |
| **API Key** | Free Gemini API key (entered on first launch → `config/api_keys.json`) |
| **GPU** | **Not required.** The avatar is rendered in software, and so is HUD video |
| **YouTube on the HUD** | `yt-dlp`, installed by `setup.py`. Without it, local files and direct URLs still play and YouTube links open in the browser with an explanation |
| **Wake word** *(optional)* | One-click download from ⚙ → WAKE WORD (`openwakeword`, a few MB, fully local) |

---

## 🗂️ Project Structure

```
OMNIX AI/
├── main.py                   # Core loop — Gemini Live session, audio I/O, viseme extraction, tool dispatch
├── ui.py                     # PyQt6 HUD — avatar canvas, waveform, log panel, settings drawer, camera feed
├── setup.py                  # OS-aware installer (skips wrong-OS dependencies, checks your Python)
├── .gitignore                # Keeps your API key, TLS key and memories out of the repository
├── plugins/
│   └── _template.py          # Copy this to write a new skill — one file, drop in, done
├── actions/                  # Bundled skills — each self-describes via a TOOL dict + handler
│                             #   Everything here drives the COMPUTER, which is what decides
│                             #   whether a new skill belongs in this folder at all.
│   ├── web_search.py         # Gemini + DDG parallel search (news, research, price, compare)
│   ├── screen_processor.py   # Screen & webcam capture for vision
│   ├── background_monitor.py # User-configured topic watching — daily DDG check
│   ├── proactive.py          # Proactive 2.0 — time/context/rotation-aware check-ins
│   ├── reminder.py           # OS-native scheduled notifications
│   ├── system_monitor.py     # CPU / RAM / GPU / temperature telemetry
│   ├── computer_settings.py  # Volume, brightness, WiFi, power (per-OS)
│   ├── computer_control.py   # Keyboard shortcuts, mouse, window management
│   ├── open_app.py           # Application launcher (per-OS name map)
│   ├── browser_control.py    # Web browser control
│   ├── file_controller.py    # File system operations
│   ├── file_processor.py     # Document reading and summarization
│   ├── send_message.py       # Messaging integration
│   ├── weather_report.py     # Live weather data
│   ├── video_player.py       # Plays video on the HUD, where the avatar normally is
│   └── desktop.py            # Desktop and taskbar control
├── memory/
│   ├── memory_manager.py     # Load/save long_term.json — sessions, monitors, identity
│   ├── config_manager.py     # api_keys.json access — key, OS, name, voice, colour, toggles
│   └── long_term.json        # Persistent store — created on first run
├── core/
│   ├── gemini.py             # One place for every one-shot Gemini call — model ladder, timeouts, cooldowns
│   ├── prompt.txt            # All prompt wording — {tokens} are filled from the live system at startup
│   ├── avatar.py             # Avatar renderer — lighting, pose, expression, mouth (QPainter)
│   ├── avatar_mesh.py        # Head geometry — loads the face, generates skull/neck/rigs
│   ├── face_model.obj        # The face itself (MediaPipe canonical model, Apache-2.0, 25 KB)
│   ├── viseme.py             # Transcript → mouth shapes, fused with the audio's timing
│   ├── echo.py               # Tells your voice from the assistant's own echo; self-calibrating
│   ├── hotkey.py             # Push-to-talk chord — global on Windows, windowed fallback elsewhere
│   ├── undo.py               # One shared undo stack — actions register how to reverse themselves
│   ├── confirm.py            # Irreversible-action gate — the token is issued by the UI, not the model
│   ├── audio_devices.py      # Microphone / speaker list — filtered, measured, resolved by name
│   ├── plugin_loader.py      # Plugin engine — discovery, validation, crash isolation
│   ├── action_loader.py      # Bundled-action engine — the built-in twin of plugin_loader
│   └── wake_word.py          # Local "Hey Jarvis" detector — own thread, offline, opt-in
└── config/
    ├── api_keys.json         # API key, name, voice, colour, toggles — created on first launch (git-ignored)
    └── certs/                # Self-signed TLS pair for the phone dashboard — generated locally (git-ignored)
```

---

## 🔒 Your Data

Everything stays on your machine. There is no OMNIX AI server, no telemetry and no account.

| What | Where | Notes |
|---|---|---|
| Gemini API key, plugin credentials | `config/api_keys.json` | **Plaintext.** Anyone with your user account can read it. Treat it like a password file. |
| Dashboard TLS certificate + private key | `config/certs/` | Generated locally, self-signed, never leaves the machine. |
| What the assistant remembers about you | `memory/long_term.json` | Delete the file to make it forget everything. |

All three are listed in `.gitignore`, so a fork or a pull request cannot leak them by accident. **If you have already committed `config/api_keys.json` anywhere public, revoke that key** at [aistudio.google.com](https://aistudio.google.com/app/apikey) and generate a new one — removing the file in a later commit does not remove it from the history.

Your voice is streamed to Google's Gemini Live API while a session is open; that is the one thing that leaves your computer, and it stops when you mute or close the app.

---

