"""
Проверка голоса по шагам:  python diagnose_voice.py
Запускай из папки проекта (в том же окружении, где запускаешь приложение).
Ничего не меняет: пробует создать движок голоса, озвучить фразу и проиграть её,
и говорит, на каком шаге сломалось.
"""
import sys, time, traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))


def step(t): print(f"\n── {t}")
def ok(m): print(f"   ✓ {m}")
def fail(m, hint=""):
    print(f"   ✗ {m}")
    if hint: print(f"     → {hint}")


step("1. numpy / sounddevice")
try:
    import numpy as np
    import sounddevice as sd
    ok(f"numpy {np.__version__}, sounddevice {sd.__version__}")
except Exception as e:
    fail(str(e), "pip install -r requirements.txt"); sys.exit(1)

step("2. Устройство вывода звука")
try:
    ok("по умолчанию: " + sd.query_devices(kind="output")["name"])
except Exception as e:
    fail(f"нет устройства вывода: {e}", "Проверь колонки/наушники в Windows.")

step("3. Какие голосовые движки установлены")
import importlib.util as iu
have_piper = iu.find_spec("piper") is not None
have_torch = iu.find_spec("torch") is not None
print(f"   Piper: {'есть' if have_piper else 'нет'}   ·   torch (Silero): {'есть' if have_torch else 'нет'}")
if not (have_piper or have_torch):
    fail("ни один движок не установлен", "pip install -r requirements-voice.txt"); sys.exit(1)

step("4. Файлы голосов Piper")
if have_piper:
    from core.tts import PIPER_VOICES, piper_voice_paths
    for n in PIPER_VOICES:
        o, c = piper_voice_paths(n)
        print(f"   {n}: {'есть' if o.exists() and c.exists() else 'нет (скачается при первом запуске)'}")
else:
    print("   · пропущено")

step("5. Создание движка (core/tts.py)")
try:
    from memory.config_manager import get_voice
    from core.tts import create_tts_engine, detect_engine, available_voices
    voice = get_voice()
    print(f"   движок: {detect_engine()}, голос в настройках: {voice}")
    t0 = time.time()
    eng = create_tts_engine(voice, 24_000)
    ok(f"{type(eng).__name__} готов за {time.time()-t0:.1f} с")
except Exception as e:
    fail(str(e)); traceback.print_exc(); sys.exit(1)

step("6. Синтез и проигрывание: выбранный голос, затем остальные мужские")
order = list(dict.fromkeys([voice] + [v for v in available_voices() if v in ("jarvis", "deep", "dmitri", "denis", "aidar", "eugene")]))
tried = []
for v in order[:4]:
    try:
        eng.set_speaker(v)
        t0 = time.time()
        audio = eng.synthesize("Проверка голоса. Если ты это слышишь, всё работает.")
        peak = float(np.max(np.abs(audio))) if audio.size else 0.0
        if peak < 0.01:
            fail(f"«{v}»: синтез вернул тишину"); tried.append((v, False)); continue
        ok(f"«{v}»: {audio.size/24000:.1f} с звука, синтез {time.time()-t0:.1f} с — играю…")
        sd.play(audio, 24_000); sd.wait(); tried.append((v, True))
    except Exception as e:
        fail(f"«{v}»: {e}"); traceback.print_exc(); tried.append((v, False))

print("\n══ ИТОГ ══")
good = [v for v, r in tried if r]
if good:
    print("Синтез работает для:", ", ".join(good))
    print("Слышал звук — значит проблема в приложении: пришли строки «ERR» из окна лога или app.log.")
    print("Звука не было, хотя ✓ — проблема в устройстве вывода Windows.")
else:
    print("Ни один голос не заработал — смотри ошибки выше.")
