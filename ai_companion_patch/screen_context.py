"""Контекст экрана: хоткей -> скриншот активного окна/области -> модель с vision."""
import io

import mss
from PIL import Image


def _active_box():
    try:
        import pygetwindow as gw
        w = gw.getActiveWindow()
        if w and w.width > 50 and w.height > 50:
            return {"left": max(w.left, 0), "top": max(w.top, 0), "width": w.width, "height": w.height}
    except Exception:
        pass
    return None


def capture_png(region=None, max_side=1600):
    """region: (left, top, width, height) или None = активное окно, иначе весь экран."""
    with mss.mss() as sct:
        box = ({"left": region[0], "top": region[1], "width": region[2], "height": region[3]}
               if region else (_active_box() or sct.monitors[1]))
        shot = sct.grab(box)
        img = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
    img.thumbnail((max_side, max_side))
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def ask_about_screen(question, ask_vision, region=None):
    """ask_vision(png_bytes, question)->str — функция вашей vision-модели (Gemini/Qwen2-VL)."""
    return ask_vision(capture_png(region), question or "Что на экране? Если ошибка — как исправить?")
