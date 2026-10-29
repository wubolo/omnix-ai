# Патч AI Companion: тема, голоса Fish Audio, MCP

Файлы (кладутся рядом с ui_modern.py / ui_panels.py):
- `glass_theme.py` — QSS «жидкое стекло», плавная смена страниц, скользящий индикатор вкладок (PyQt6).
- `voice_presets.py` — кнопки JARVIS / MiSide / Рик (пишут `tts_engine=fish` и `fish_reference_id`).
- `mcp_manager.py` — MCP-клиент (stdio). `mcp_card.py` — карточка в настройках.

Подключение в `_page_settings` (ui_modern.py):
    from voice_presets import FishVoicePresets
    from mcp_card import McpCard
    <layout>.addWidget(FishVoicePresets(self)); <layout>.addWidget(McpCard(self))
Тема: `app.setStyleSheet(GLASS_QSS)`; страницы — `SmoothStackedWidget` вместо QStackedWidget.

Для ассистента (main.py):
- в `_build_config` добавить `MCP.tool_declarations()` к списку функций;
- в `_execute_tool`: если имя содержит `__` — вернуть `MCP.call(name, args)`;
- при старте `MCP.start_enabled()`, при выходе `MCP.stop_all()`.

## Остальные функции
- `memory_store.py` — память: факты (`extract_facts(dialog, ask_llm)` после диалога), поиск `search_facts`, `prompt_block(текст)` в системный промпт, `add_message` + `timeline()` для вкладки «История». SQLite FTS5 вместо ChromaDB (её нет в сборке).
- `screen_context.py` — `ask_about_screen(вопрос, ask_vision)`; повесьте на хоткей.
- `clipboard_tools.py` — `ClipboardHotkeys(ask_llm, on_result).start()`: Ctrl+Alt+T/E/P — перевод/объяснение/правка письма.
- `proactive_notify.py` — `Proactive(tray).start()`: напоминание о разминке, `remind_in(минуты, текст)`.
