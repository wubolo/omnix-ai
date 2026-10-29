"""
Text-to-Speech engines for AI Companion.

EdgeTTS     – free Microsoft TTS (internet required, no API key)
Kokoro      – fully offline neural TTS (~330 MB model)
ElevenLabs  – cloud API (API key required, best quality)
"""
from __future__ import annotations

import asyncio
import hashlib
import os
import queue as _queue
import re
import shutil
import sys
import threading
from typing import Callable, Optional

import numpy as np
import sounddevice as sd
from pathlib import Path
import tempfile



# USE_TF=0 stops transformers from importing TensorFlow (saves 4-8 s startup).
# Do NOT set USE_TORCH or USE_JAX explicitly — forcing those values breaks
# transformers' lazy-loader on certain versions, causing AutoModel and other
# classes to vanish from the public namespace.  Auto-detection is reliable.
os.environ.setdefault("USE_TF",                 "0")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")


# ---------------------------------------------------------------------------
# Audio playback helpers
# ---------------------------------------------------------------------------

def _to_numpy(samples) -> np.ndarray:
    """Convert samples to float32 numpy array.

    Handles both numpy arrays and PyTorch tensors (Kokoro >= 0.9).

    PyTorch built against numpy 1.x raises RuntimeError('Numpy is not available')
    when numpy 2.x is installed.  The .tolist() fallback always works regardless
    of PyTorch / numpy version pairing.
    """
    if hasattr(samples, "detach"):                  # PyTorch tensor
        t = samples.detach().cpu().float()
        try:
            return t.numpy()                        # fast path (compatible versions)
        except RuntimeError:
            # PyTorch/numpy version mismatch — convert via Python list (always safe)
            return np.asarray(t.tolist(), dtype=np.float32)
    return np.asarray(samples, dtype=np.float32)


def _compress_silence(
    arr: np.ndarray,
    sample_rate: int    = 24_000,
    max_silence_ms: int = 500,    # cap punctuation pauses — keeps natural rhythm
    threshold: float    = 0.003,  # RMS below this = silence; lower = less clipping
) -> np.ndarray:
    """
    Shorten Kokoro's very long punctuation pauses (1-2 s → ≤500 ms).
    Conservative settings preserve natural prosody; only trims extreme pauses.
    """
    max_samp  = int(max_silence_ms * sample_rate / 1000)
    frame_len = 240                   # ~10 ms at 24 kHz
    out: list[np.ndarray] = []
    silent_acc = 0

    for i in range(0, len(arr), frame_len):
        chunk = arr[i : i + frame_len]
        if np.sqrt(np.mean(chunk ** 2) + 1e-12) < threshold:
            silent_acc += len(chunk)
            if silent_acc <= max_samp:
                out.append(chunk)
        else:
            silent_acc = 0
            out.append(chunk)

    return np.concatenate(out) if out else arr


def _play_np(samples, sample_rate: int) -> None:
    """Play float32 mono (or stereo) audio via sounddevice.
    Accepts numpy arrays or PyTorch tensors.
    """
    sd.play(_to_numpy(samples), sample_rate)
    sd.wait()


def _play_audio_bytes(audio_bytes: bytes) -> None:
    """Decode MP3/WAV/OGG bytes and play via sounddevice (uses miniaudio)."""
    import miniaudio
    decoded = miniaudio.decode(
        audio_bytes,
        output_format=miniaudio.SampleFormat.FLOAT32,
        nchannels=1,
    )
    samples = np.array(decoded.samples, dtype=np.float32)
    sd.play(samples, decoded.sample_rate)
    sd.wait()


# ---------------------------------------------------------------------------
# Voice presets: a Silero speaker + prosody + a light "AI butler" colouring
# ---------------------------------------------------------------------------
#
# These are original character voices built on Silero's own male speakers, not
# imitations of any actor. "pitch" and "rate" are SSML prosody values Silero
# understands (x-low … x-high / x-slow … x-fast); "fx" switches on the studio
# colouring in _ai_colour(). If this Silero build rejects SSML the preset still
# works, just without the pitch shift.

VOICE_PRESETS: dict[str, dict] = {
    # calm, measured, slightly lowered — a composed AI-butler feel
    "jarvis": {"base": "eugene", "pitch": "low",   "rate": "medium", "fx": True},
    # the deepest option: aidar, pitched down
    "deep":   {"base": "aidar",  "pitch": "x-low", "rate": "medium", "fx": True},
}
_FX_VERSION = "fx1"      # bump to invalidate cached audio when the colouring changes


def _ai_colour(audio: np.ndarray, sample_rate: int) -> np.ndarray:
    """Studio colouring: more chest, a little presence, a faint metallic double
    and a very short room. Pure numpy (one FFT per utterance), no extra packages."""
    if audio.size < 256:
        return audio
    tail = int(0.06 * sample_rate)
    x = np.concatenate((audio.astype(np.float64), np.zeros(tail)))
    spec = np.fft.rfft(x)
    f = np.fft.rfftfreq(x.size, 1.0 / sample_rate)
    gain = (1.0 + 0.7 / (1.0 + (f / 250.0) ** 4)              # body below ~250 Hz
            + 0.25 * np.exp(-((f - 3000.0) / 1200.0) ** 2))   # presence
    gain *= 1.0 / (1.0 + (f / 10000.0) ** 4)                   # soften the top
    y = np.fft.irfft(spec * gain, n=x.size)

    def _delayed(sig: np.ndarray, seconds: float, level: float) -> np.ndarray:
        d = int(seconds * sample_rate)
        out = np.zeros_like(sig)
        out[d:] = sig[:-d] * level
        return out

    y = y + _delayed(y, 0.011, 0.16) + _delayed(y, 0.037, 0.07)
    peak = float(np.max(np.abs(y))) or 1.0
    y = np.tanh(y / peak * 1.1) / np.tanh(1.1) * 0.95
    return y.astype(np.float32)


def _ssml_escape(text: str) -> str:
    return (text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


# ---------------------------------------------------------------------------
# Sentence splitting + on-disk phrase cache (used by Silero)
# ---------------------------------------------------------------------------

_SENT_SPLIT = re.compile(r'(?<=[.!?…])["»)\]]*\s+')


def split_sentences(text: str, min_len: int = 24, max_len: int = 240) -> list[str]:
    """Cut a reply into speakable pieces so the first one can start playing
    while the rest are still being synthesized.

    Fragments shorter than `min_len` ("т.д.", "Ок.") are glued to a neighbour —
    a one-word clip sounds choppy — and a sentence longer than `max_len` is
    broken at the last comma / semicolon / dash that fits."""
    text = " ".join((text or "").split())
    if not text:
        return []
    parts = [p.strip() for p in _SENT_SPLIT.split(text) if p.strip()]

    pieces: list[str] = []
    for p in parts:
        while len(p) > max_len:
            cut = max(p.rfind(sep, 0, max_len) for sep in (", ", "; ", ": ", " — "))
            if cut < max_len // 2:
                cut = p.rfind(" ", 0, max_len)
            if cut <= 0:
                cut = max_len - 1
            pieces.append(p[:cut + 1].strip())
            p = p[cut + 1:].strip()
        if p:
            pieces.append(p)

    merged: list[str] = []
    for p in pieces:
        if merged and len(merged[-1]) < min_len:
            merged[-1] += " " + p
        else:
            merged.append(p)
    if len(merged) > 1 and len(merged[-1]) < min_len:
        tail = merged.pop()          # pop first: `merged[-2] += merged.pop()` stores to the wrong slot
        merged[-1] += " " + tail
    return merged


class TTSCache:
    """Synthesized phrases kept on disk as int16 .npy files.

    The assistant says the same things all the time ("Открываю Steam.",
    "Готово.", the greeting). Synthesizing them again costs a second of CPU
    each; reading them back costs a millisecond. The key includes the voice,
    the sample rate and the model tag, so changing any of them never serves
    the wrong audio. The folder is trimmed to `max_bytes`, oldest first."""

    def __init__(self, directory: Path, max_bytes: int = 300 * 1024 * 1024,
                 max_text: int = 400):
        self.dir = Path(directory)
        self.max_bytes = max_bytes
        self.max_text = max_text
        self._writes = 0
        self._lock = threading.Lock()
        try:
            self.dir.mkdir(parents=True, exist_ok=True)
            self.prune()
        except OSError:
            pass

    @staticmethod
    def key(text: str, speaker: str, rate: int, tag: str = "v5_5_ru") -> str:
        raw = f"{tag}|{speaker}|{rate}|{' '.join(text.split())}"
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()

    def get(self, key: str) -> Optional[np.ndarray]:
        path = self.dir / f"{key}.npy"
        try:
            pcm = np.load(path, allow_pickle=False)
            os.utime(path, None)                       # recently used = keep
            return pcm.astype(np.float32) / 32767.0
        except Exception:
            return None

    def put(self, key: str, audio: np.ndarray) -> None:
        if audio.size == 0:
            return
        path = self.dir / f"{key}.npy"
        tmp = self.dir / f"{key}.tmp"
        try:
            pcm = (np.clip(audio, -1.0, 1.0) * 32767.0).astype(np.int16)
            with open(tmp, "wb") as f:
                np.save(f, pcm)
            os.replace(tmp, path)
        except Exception:
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass
            return
        with self._lock:
            self._writes += 1
            due = self._writes % 25 == 0
        if due:
            self.prune()

    def prune(self) -> None:
        try:
            files = [(f.stat().st_mtime, f.stat().st_size, f) for f in self.dir.glob("*.npy")]
        except OSError:
            return
        total = sum(sz for _, sz, _ in files)
        if total <= self.max_bytes:
            return
        for _, sz, f in sorted(files, key=lambda x: x[0]):
            try:
                f.unlink()
                total -= sz
            except OSError:
                pass
            if total <= self.max_bytes * 0.8:
                break


# ---------------------------------------------------------------------------
# Engines
# ---------------------------------------------------------------------------

class SileroTTSEngine:
    """Russian Silero TTS v5.5, loaded once and synthesized locally."""

    MODEL_URL = "https://models.silero.ai/models/tts/ru/v5_5_ru.pt"
    SPEAKERS = {"aidar", "baya", "kseniya", "xenia", "eugene"}

    def __init__(self, speaker: str = "xenia", sample_rate: int = 24_000,
                 cache: bool = True):
        self.speaker = self._valid(speaker)
        self.sample_rate = sample_rate if sample_rate in (8_000, 24_000, 48_000) else 24_000
        self._ssml_ok = True
        self._model = None
        self._lock = threading.Lock()
        app_dir = (Path(sys.executable).parent if getattr(sys, "frozen", False)
                   else Path(__file__).resolve().parent.parent)
        self._cache = TTSCache(app_dir / "cache" / "tts") if cache else None
        self._load()

    def _load(self) -> None:
        import torch

        import zipfile

        def _valid(path: Path) -> bool:
            """Модель — zip-архив; битый/недокачанный файл не откроется."""
            try:
                if not path.is_file():
                    return False
                with zipfile.ZipFile(path) as zf:
                    return zf.testzip() is None
            except Exception:
                return False

        model_dir = Path(torch.hub.get_dir()) / "silero"
        model_dir.mkdir(parents=True, exist_ok=True)
        cache_path = model_dir / "v5_5_ru.pt"
        local = Path(__file__).resolve().parent.parent / "models" / "v5_5_ru.pt"

        model_path = None
        for cand in (local, cache_path):
            if cand.is_file():
                if _valid(cand):
                    model_path = cand
                    break
                print(f"[TTS] Model file is corrupted/incomplete, deleting: {cand}")
                try:
                    cand.unlink()
                except OSError as e:
                    raise RuntimeError(
                        f"Файл модели повреждён, а удалить его не удалось: {cand}\n"
                        f"Удалите его вручную и перезапустите. ({e})"
                    ) from e
        if model_path is None:
            self._download(model_dir, cache_path)
            if not _valid(cache_path):
                cache_path.unlink(missing_ok=True)
                raise RuntimeError(
                    "Модель скачалась не полностью (обрыв сети или антивирус). "
                    "Перезапустите программу — загрузка начнётся заново, "
                    "или запустите fix_silero.bat."
                )
            model_path = cache_path
        self._model = torch.package.PackageImporter(str(model_path)).load_pickle(
            "tts_models", "model"
        )
        self._model.to(torch.device("cpu"))
        # The first call into a freshly loaded model is the slowest one. Pay for
        # it here, while the app is still starting, not on the first answer.
        try:
            self._model.apply_tts(text="Привет.", speaker=self._base(self.speaker),
                                  sample_rate=self.sample_rate)
        except Exception:
            pass
        print("[TTS] Silero v5.5 Russian voice is ready.")

    def _download(self, model_dir: Path, model_path: Path) -> None:
        """Скачать модель. Проверка сертификата НЕ отключается.

        1) системное хранилище сертификатов (torch.hub);
        2) если не вышло — набор certifi через requests.
        """
        import torch

        print("[TTS] Downloading Silero TTS v5.5 Russian model (one-time)…")
        with tempfile.NamedTemporaryFile(prefix="silero-", suffix=".pt", dir=model_dir,
                                         delete=False) as tmp:
            temp_path = Path(tmp.name)
        try:
            try:
                torch.hub.download_url_to_file(self.MODEL_URL, str(temp_path), progress=True)
            except Exception as exc:
                message = str(exc).lower()
                if "certificate" not in message and "ssl" not in message:
                    raise
                print("[TTS] System certificate check failed, retrying with certifi…")
                try:
                    import requests
                    with requests.get(self.MODEL_URL, stream=True, timeout=60) as r:
                        r.raise_for_status()
                        with open(temp_path, "wb") as f:
                            for chunk in r.iter_content(chunk_size=1 << 20):
                                f.write(chunk)
                except Exception as exc2:
                    manual = model_dir / "v5_5_ru.pt"
                    raise RuntimeError(
                        "Не прошла проверка HTTPS-сертификата сайта Silero. "
                        "Скачайте файл вручную в браузере:\n"
                        f"  {self.MODEL_URL}\n"
                        "и положите его сюда (любой из вариантов):\n"
                        f"  {manual}\n"
                        f"  {Path(__file__).resolve().parent.parent / 'models' / 'v5_5_ru.pt'}\n"
                        "Проверка сертификата не отключалась."
                    ) from exc2
            temp_path.replace(model_path)
        finally:
            temp_path.unlink(missing_ok=True)

    def synthesize(self, text: str) -> np.ndarray:
        """Return mono float32 samples at the configured sample rate."""
        text = (text or "").strip()
        if not text:
            return np.empty(0, dtype=np.float32)

        with self._lock:
            speaker = self.speaker          # key and synthesis must use the same voice
        preset = VOICE_PRESETS.get(speaker)
        cache_key = None
        if self._cache is not None and len(text) <= self._cache.max_text:
            tag = f"v5_5_ru+{_FX_VERSION}" if preset else "v5_5_ru"
            cache_key = TTSCache.key(text, speaker, self.sample_rate, tag)
            hit = self._cache.get(cache_key)
            if hit is not None:
                return hit

        samples = None
        with self._lock:
            if preset and self._ssml_ok and preset.get("pitch"):
                try:
                    ssml = (f'<speak><prosody pitch="{preset["pitch"]}" '
                            f'rate="{preset.get("rate", "medium")}">'
                            f'{_ssml_escape(text)}</prosody></speak>')
                    samples = self._model.apply_tts(
                        ssml_text=ssml, speaker=self._base(speaker),
                        sample_rate=self.sample_rate)
                except Exception as exc:
                    self._ssml_ok = False
                    print(f"[TTS] SSML pitch not supported by this build ({exc}); "
                          f"using the plain voice.")
            if samples is None:
                samples = self._model.apply_tts(
                    text=text,
                    speaker=self._base(speaker),
                    sample_rate=self.sample_rate,
                )
        audio = _to_numpy(samples).reshape(-1)
        audio = np.clip(audio, -1.0, 1.0).astype(np.float32, copy=False)
        if preset and preset.get("fx"):
            audio = _ai_colour(audio, self.sample_rate)
        if cache_key is not None:
            self._cache.put(cache_key, audio)
        return audio

    def set_speaker(self, speaker: str) -> None:
        """Change voice safely between synthesis calls."""
        if speaker in self.SPEAKERS or speaker in VOICE_PRESETS:
            with self._lock:
                self.speaker = speaker

    @classmethod
    def _valid(cls, speaker: str) -> str:
        return speaker if (speaker in cls.SPEAKERS or speaker in VOICE_PRESETS) else "xenia"

    @staticmethod
    def _base(speaker: str) -> str:
        """The Silero speaker that actually produces the sound."""
        return VOICE_PRESETS.get(speaker, {}).get("base", speaker)


class EdgeTTSEngine:
    """Microsoft EdgeTTS – free, requires internet."""

    def __init__(self, voice: str = "en-US-GuyNeural"):
        self.voice = voice

    def speak(self, text: str) -> None:
        loop = asyncio.new_event_loop()
        try:
            audio_bytes = loop.run_until_complete(self._synth(text))
        finally:
            loop.close()
        if audio_bytes:
            _play_audio_bytes(audio_bytes)

    async def _synth(self, text: str) -> bytes:
        import edge_tts
        comm = edge_tts.Communicate(text, self.voice)
        buf  = bytearray()
        async for chunk in comm.stream():
            if chunk["type"] == "audio":
                buf.extend(chunk["data"])
        return bytes(buf)


# ---------------------------------------------------------------------------
# Kokoro import helper — auto-upgrades on version-mismatch errors
# ---------------------------------------------------------------------------

# Errors that indicate the installed kokoro uses old transformers classes
# (AlbertModel, AutoModel) that are no longer exported at the top level.
_KOKORO_COMPAT_ERRORS = ("AlbertModel", "AutoModel", "cannot import name")


def _import_kokoro_pipeline():
    """Import KPipeline, auto-upgrading kokoro if a version mismatch is found.

    Old kokoro (<0.9) imports AlbertModel / AutoModel from transformers.
    Newer transformers versions no longer export these at the top level,
    causing an ImportError.  kokoro>=0.9 removed these dependencies.

    When the error is detected we:
      1. Upgrade kokoro to >=0.9 via pip (silent, background)
      2. Flush stale kokoro entries from sys.modules
      3. Re-import — this time it should succeed
    """
    import sys

    def _try_import():
        from kokoro import KPipeline  # noqa: PLC0415
        return KPipeline

    try:
        return _try_import()
    except Exception as first_err:
        err_msg = str(first_err)
        if not any(marker in err_msg for marker in _KOKORO_COMPAT_ERRORS):
            # Unrelated error (kokoro not installed, etc.)
            raise RuntimeError(
                f"Kokoro import failed: {first_err}\n"
                "Run: pip install kokoro>=0.9 soundfile"
            ) from first_err

        # ── Version mismatch: upgrade kokoro silently and retry ──────────
        print("[TTS] Kokoro/transformers version mismatch detected — upgrading kokoro…")
        import subprocess
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "kokoro>=0.9",
             "--upgrade", "--quiet", "--disable-pip-version-check"],
            capture_output=True,
        )
        if result.returncode != 0:
            stderr = result.stderr.decode(errors="replace").strip()
            raise RuntimeError(
                f"Kokoro auto-upgrade failed: {stderr[:200]}\n"
                "Run manually: pip install kokoro>=0.9 soundfile"
            ) from first_err

        # Flush any stale kokoro submodules from the import cache
        stale = [k for k in sys.modules if k == "kokoro" or k.startswith("kokoro.")]
        for key in stale:
            del sys.modules[key]

        print("[TTS] Kokoro upgraded — retrying import…")
        try:
            return _try_import()
        except Exception as retry_err:
            raise RuntimeError(
                f"Kokoro still broken after upgrade: {retry_err}\n"
                "Run manually: pip install --upgrade kokoro transformers"
            ) from retry_err


# Kokoro voice prefix → KPipeline lang_code mapping
_KOKORO_LANG_CODES = {
    "a": "a",   # American English  (af_*, am_*)
    "b": "b",   # British English   (bf_*, bm_*)
    "j": "j",   # Japanese          (jf_*, jm_*)
    "z": "z",   # Mandarin Chinese  (zf_*, zm_*)
    "s": "s",   # Spanish           (sf_*, sm_*)
    "f": "f",   # French            (ff_*, fm_*)
    "h": "h",   # Hindi             (hf_*, hm_*)
    "i": "i",   # Italian           (if_*, im_*)
    "p": "p",   # Brazilian Portuguese
    "r": "r",   # Russian           (rf_*, rm_*)
    "e": "e",   # German            (ef_*, em_*)
}


class KokoroTTSEngine:
    """Fully offline Kokoro neural TTS.

    Model (~330 MB) is downloaded from HuggingFace on first use,
    then cached locally — subsequent starts load from disk.

    Warmup strategy: _init() runs synchronously in the background
    _do_tts() thread (not the UI thread).  After the pipeline loads,
    a dummy inference compiles the PyTorch JIT graph immediately so
    the first real speak() call has zero compilation overhead.
    """

    def __init__(self, voice: str = "af_heart", speed: float = 1.0):
        self.voice     = voice
        self.speed     = speed
        self._pipeline = None
        self._lock     = threading.Lock()
        self._init()   # blocking, but called from background thread

    @property
    def _lang_code(self) -> str:
        prefix = self.voice[0].lower() if self.voice else "a"
        return _KOKORO_LANG_CODES.get(prefix, "a")

    def _init(self) -> None:
        if self._pipeline is not None:
            return

        lang = self._lang_code

        # Prefer GPU — Kokoro on CUDA is ~10x faster than CPU.
        try:
            import torch
            device = "cuda" if torch.cuda.is_available() else "cpu"
            if device == "cpu":
                import os as _os
                n_threads = max(1, min(4, (_os.cpu_count() or 4) // 2))
                try:
                    torch.set_num_threads(n_threads)
                    torch.set_num_interop_threads(2)
                except RuntimeError:
                    pass
                print(
                    f"[TTS] Kokoro on CPU — for faster speech install CUDA PyTorch:\n"
                    "      pip install torch --index-url https://download.pytorch.org/whl/cu118"
                )
        except Exception:
            device = "cpu"

        print(f"[TTS] Kokoro — loading (lang='{lang}', device='{device}')…")

        KPipeline = _import_kokoro_pipeline()

        def _create_pipeline():
            try:
                return KPipeline(lang_code=lang, device=device)
            except TypeError:
                return KPipeline(lang_code=lang)   # older build — no device param

        try:
            self._pipeline = _create_pipeline()
        except Exception as _first_err:
            # Offline flag set but model not cached yet → clear flags and download once.
            # Keywords cover multiple huggingface_hub error message variants across versions.
            _e = str(_first_err).lower()
            _offline_keywords = (
                "offline", "not found", "cache", "localentry",
                "does not exist", "outgoing", "local_files_only",
            )
            if any(k in _e for k in _offline_keywords):
                print("[TTS] Kokoro model not in local cache — downloading (one-time, internet required)…")
                os.environ.pop("HF_HUB_OFFLINE",      None)
                os.environ.pop("TRANSFORMERS_OFFLINE", None)
                os.environ.pop("HF_DATASETS_OFFLINE",  None)
                try:
                    self._pipeline = _create_pipeline()
                except Exception as _dl_err:
                    raise RuntimeError(
                        f"Kokoro model download failed.\n"
                        f"Internet access is required the first time to download the voice model (~330 MB).\n"
                        f"After the first download it runs fully offline.\n"
                        f"Tip: Switch to EdgeTTS (free, no download) in the Configure panel if offline.\n"
                        f"Details: {_dl_err}"
                    ) from _dl_err
            else:
                raise

        print("[TTS] Kokoro compiling (first-time only)…")
        # Warmup: compiles PyTorch JIT graph so first real speak() call is instant.
        try:
            for _ in self._pipeline("hello", voice=self.voice, speed=self.speed):
                pass
            print("[TTS] Kokoro ready.")
        except Exception as e:
            print(f"[TTS] Kokoro warmup warning: {e}")

    def speak(self, text: str) -> None:
        with self._lock:
            if self._pipeline is None:
                self._init()

        # ── Concurrent synthesise + playback ────────────────────────────────
        # Kokoro generates audio chunks lazily.  Without threading, we:
        #   synthesise chunk N → play N → synthesise N+1 → play N+1 …
        # With a producer/consumer pair, chunk N+1 synthesises WHILE chunk N
        # plays, cutting perceived latency by the playback duration of all but
        # the last chunk (typically 1-3 s on multi-sentence responses).
        audio_q: "_queue.Queue[np.ndarray | None]" = _queue.Queue(maxsize=4)
        synth_error: list[Exception] = []

        def _synth():
            try:
                for _, _, audio in self._pipeline(text, voice=self.voice, speed=self.speed):
                    if audio is not None:
                        arr = _to_numpy(audio)
                        arr = _compress_silence(arr)
                        if arr.size > 0:
                            audio_q.put(arr)          # blocks if player is slow (backpressure)
            except Exception as exc:
                synth_error.append(exc)
            finally:
                audio_q.put(None)                     # sentinel → player exits

        synth_thread = threading.Thread(target=_synth, daemon=True)
        synth_thread.start()

        # Player runs in this thread so sd.wait() doesn't block the synth thread.
        while True:
            arr = audio_q.get()
            if arr is None:
                break
            _play_np(arr, 24000)

        synth_thread.join()

        if synth_error:
            raise synth_error[0]


class ElevenLabsTTSEngine:
    """ElevenLabs cloud TTS – API key required."""

    def __init__(self, api_key: str, voice_id: str = "pNInz6obpgDQGcFmaJgB"):
        self.api_key  = api_key
        self.voice_id = voice_id

    def speak(self, text: str) -> None:
        import requests
        headers = {
            "xi-api-key":   self.api_key,
            "Content-Type": "application/json",
        }
        payload = {
            "text":     text,
            "model_id": "eleven_multilingual_v2",
            "voice_settings": {"stability": 0.5, "similarity_boost": 0.75},
        }
        resp = requests.post(
            f"https://api.elevenlabs.io/v1/text-to-speech/{self.voice_id}",
            json=payload, headers=headers, timeout=30,
        )
        resp.raise_for_status()
        _play_audio_bytes(resp.content)


# ---------------------------------------------------------------------------
# Thread-safe player wrapper
# ---------------------------------------------------------------------------

class TTSPlayer:
    """
    Wraps any *Engine. Exposes a blocking speak() method
    meant to be called from a dedicated background thread.
    """

    def __init__(self, engine):
        self._engine  = engine
        self._playing = False
        self._lock    = threading.Lock()

    @property
    def is_playing(self) -> bool:
        return self._playing

    def speak(
        self,
        text:     str,
        on_start: Optional[Callable] = None,
        on_done:  Optional[Callable] = None,
    ) -> None:
        """Synthesise and play text. BLOCKING – call from a dedicated thread."""
        try:
            with self._lock:
                self._playing = True
            if on_start:
                on_start()
            self._engine.speak(text)
        except Exception as e:
            print(f"[TTS] Error: {e}")
        finally:
            with self._lock:
                self._playing = False
            if on_done:
                on_done()

    def stop(self) -> None:
        sd.stop()
        with self._lock:
            self._playing = False


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def create_tts_player(config: dict) -> TTSPlayer:
    engine_name = config.get("tts_engine", "silero").lower()
    if engine_name == "silero":
        voice = config.get("tts_voice", "xenia")
        engine = SileroTTSEngine(speaker=voice)
    elif engine_name == "kokoro":
        voice  = config.get("tts_voice", "af_heart")
        speed  = float(config.get("tts_speed", 1.0))
        engine = KokoroTTSEngine(voice=voice, speed=speed)
    elif engine_name == "elevenlabs":
        api_key  = config.get("elevenlabs_api_key", "")
        voice_id = config.get("tts_voice", "pNInz6obpgDQGcFmaJgB")
        engine   = ElevenLabsTTSEngine(api_key=api_key, voice_id=voice_id)
    else:   # edgetts (default)
        voice  = config.get("tts_voice", "en-US-GuyNeural")
        engine = EdgeTTSEngine(voice=voice)
    return TTSPlayer(engine)


# ---------------------------------------------------------------------------
# Piper — small offline voices, no PyTorch
# ---------------------------------------------------------------------------
#
# Piper runs on onnxruntime, which the app already needs for Whisper and wake
# word, so using it removes torch (the biggest single download) altogether.
# Voices are plain files in <app>/models/piper/; the installer fetches them and
# the engine fetches a missing one on first use.
#
# Character presets work as with Silero: a base voice plus a pitch factor and the
# studio colouring. Pitch is lowered by speaking faster and then playing the clip
# back slower, so the tempo stays the same and only the pitch drops.

PIPER_VOICES = {"dmitri": "medium", "denis": "medium", "irina": "medium"}   # male, male, female
PIPER_PRESETS: dict[str, dict] = {
    "jarvis": {"base": "dmitri", "pitch": 0.96, "fx": True},
    "deep":   {"base": "denis",  "pitch": 0.90, "fx": True},
}
_PIPER_URL = ("https://huggingface.co/rhasspy/piper-voices/resolve/main/"
              "ru/ru_RU/{n}/{q}/ru_RU-{n}-{q}.onnx")


def _app_dir() -> Path:
    return (Path(sys.executable).parent if getattr(sys, "frozen", False)
            else Path(__file__).resolve().parent.parent)


def piper_available() -> bool:
    if "piper" in sys.modules:
        return True
    import importlib.util
    try:
        return importlib.util.find_spec("piper") is not None
    except Exception:
        return False


def piper_voice_paths(name: str) -> tuple[Path, Path]:
    q = PIPER_VOICES[name]
    d = _app_dir() / "models" / "piper"
    return d / f"ru_RU-{name}-{q}.onnx", d / f"ru_RU-{name}-{q}.onnx.json"


def download_piper_voice(name: str, log=print) -> None:
    """Fetch the two files of a voice if they are not on disk yet."""
    import ssl
    import urllib.request
    onnx, cfg = piper_voice_paths(name)
    try:
        import certifi
        ctx = ssl.create_default_context(cafile=certifi.where())
    except Exception:
        ctx = ssl.create_default_context()
    base = _PIPER_URL.format(n=name, q=PIPER_VOICES[name])
    onnx.parent.mkdir(parents=True, exist_ok=True)
    for url, dst in ((base, onnx), (base + ".json", cfg)):
        if dst.exists() and dst.stat().st_size > 0:
            continue
        log(f"[TTS] downloading {dst.name} …")
        tmp = dst.with_name(dst.name + ".part")
        with urllib.request.urlopen(url, context=ctx, timeout=60) as r, open(tmp, "wb") as f:
            shutil.copyfileobj(r, f)
        os.replace(tmp, dst)


def _resample(audio: np.ndarray, sr_from: int, sr_to: int, pitch: float = 1.0) -> np.ndarray:
    """Linear resample to `sr_to`. pitch < 1 stretches the clip, which lowers it."""
    if audio.size == 0:
        return audio
    n_out = max(1, int(round(audio.size * (sr_to / sr_from) / pitch)))
    if n_out == audio.size:
        return audio
    xs = np.linspace(0.0, audio.size - 1, n_out)
    return np.interp(xs, np.arange(audio.size), audio).astype(np.float32)


class PiperTTSEngine:
    """Same interface as SileroTTSEngine: synthesize(text) -> float32 mono."""

    def __init__(self, speaker: str = "jarvis", sample_rate: int = 24_000,
                 cache: bool = True):
        self.sample_rate = sample_rate if sample_rate in (8_000, 24_000, 48_000) else 24_000
        self.speaker = self._valid(speaker)
        self._voices: dict = {}
        self._lock = threading.Lock()
        self._cache = TTSCache(_app_dir() / "cache" / "tts") if cache else None
        voice = self._load(self._base(self.speaker))       # fail early, not on the first reply
        try:                                               # first call is the slow one: pay now
            self._raw(voice, "Привет.", 1.0)
        except Exception:
            pass
        print("[TTS] Piper Russian voice is ready.")

    # names ------------------------------------------------------------------
    @staticmethod
    def _valid(speaker: str) -> str:
        return speaker if (speaker in PIPER_VOICES or speaker in PIPER_PRESETS) else "jarvis"

    @staticmethod
    def _base(speaker: str) -> str:
        return PIPER_PRESETS.get(speaker, {}).get("base", speaker)

    def set_speaker(self, speaker: str) -> None:
        if speaker in PIPER_VOICES or speaker in PIPER_PRESETS:
            with self._lock:
                self.speaker = speaker

    # loading / synthesis -------------------------------------------------------
    def _load(self, base: str):
        if base in self._voices:
            return self._voices[base]
        from piper import PiperVoice
        onnx, cfg = piper_voice_paths(base)
        if not (onnx.exists() and cfg.exists()):
            download_piper_voice(base)
        voice = PiperVoice.load(str(onnx), config_path=str(cfg))
        self._voices[base] = voice
        return voice

    @staticmethod
    def _raw(voice, text: str, length_scale: float) -> tuple[np.ndarray, int]:
        """One utterance as float32 at the voice's own rate. Handles both the
        piper-tts 1.3+ API and the older 1.2 one."""
        sr = int(voice.config.sample_rate)
        try:
            from piper import SynthesisConfig                      # 1.3+
        except ImportError:
            raw = b"".join(voice.synthesize_stream_raw(text, length_scale=length_scale))
            pcm = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
            return pcm, sr
        cfg = SynthesisConfig(length_scale=length_scale)
        parts = [np.asarray(c.audio_float_array, dtype=np.float32)
                 for c in voice.synthesize(text, syn_config=cfg)]
        return (np.concatenate(parts) if parts else np.empty(0, np.float32)), sr

    def synthesize(self, text: str) -> np.ndarray:
        text = (text or "").strip()
        if not text:
            return np.empty(0, dtype=np.float32)
        with self._lock:
            speaker = self.speaker
        preset = PIPER_PRESETS.get(speaker)
        pitch = float(preset["pitch"]) if preset else 1.0

        key = None
        if self._cache is not None and len(text) <= self._cache.max_text:
            key = TTSCache.key(text, speaker, self.sample_rate, f"piper1+{_FX_VERSION}")
            hit = self._cache.get(key)
            if hit is not None:
                return hit

        with self._lock:
            voice = self._load(self._base(speaker))
            pcm, sr = self._raw(voice, text, length_scale=pitch)   # faster now, stretched below
        audio = _resample(pcm, sr, self.sample_rate, pitch)
        audio = np.clip(audio, -1.0, 1.0).astype(np.float32, copy=False)
        if preset and preset.get("fx"):
            audio = _ai_colour(audio, self.sample_rate)
        if key is not None:
            self._cache.put(key, audio)
        return audio


# ---------------------------------------------------------------------------
# Windows built-in voice (SAPI) — works offline, nothing to install
# ---------------------------------------------------------------------------

def _run_powershell(script: str, env_extra: dict | None = None, timeout: float = 30.0) -> str:
    import subprocess
    env = dict(os.environ)
    env.update(env_extra or {})
    flags = 0x08000000 if sys.platform == "win32" else 0          # CREATE_NO_WINDOW
    out = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                          "-Command", script], capture_output=True, timeout=timeout, env=env,
                         creationflags=flags)
    if out.returncode != 0:
        raise RuntimeError((out.stderr or b"").decode("utf-8", "replace").strip()[:200] or "PowerShell failed")
    return (out.stdout or b"").decode("utf-8", "replace")


_SAPI_VOICES: list[str] | None = None


def sapi_voices(runner=None) -> list[str]:
    """Names of the installed Windows voices (Russian ones first)."""
    global _SAPI_VOICES
    if _SAPI_VOICES is not None and runner is None:
        return _SAPI_VOICES
    if sys.platform != "win32" and runner is None:
        return []
    run = runner or _run_powershell
    try:
        raw = run("Add-Type -AssemblyName System.Speech; "
                  "(New-Object System.Speech.Synthesis.SpeechSynthesizer).GetInstalledVoices() | "
                  "ForEach-Object { $_.VoiceInfo.Name + '|' + $_.VoiceInfo.Culture.Name }")
    except Exception:
        return []
    voices = []
    for line in raw.splitlines():
        name, _, culture = line.strip().partition("|")
        if name:
            voices.append((0 if culture.lower().startswith("ru") else 1, name))
    result = [n for _, n in sorted(voices)]
    if runner is None:
        _SAPI_VOICES = result
    return result


def read_wav_mono(data: bytes) -> tuple[np.ndarray, int]:
    """WAV bytes (8/16/32-bit PCM, any channels) -> float32 mono and its sample rate."""
    import io
    import wave
    with wave.open(io.BytesIO(data), "rb") as w:
        ch, width, sr, n = w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()
        raw = w.readframes(n)
    if width == 2:
        pcm = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
    elif width == 1:
        pcm = (np.frombuffer(raw, dtype=np.uint8).astype(np.float32) - 128.0) / 128.0
    elif width == 4:
        pcm = np.frombuffer(raw, dtype="<i4").astype(np.float32) / 2147483648.0
    else:
        raise ValueError(f"unsupported WAV sample width: {width}")
    if ch > 1:
        pcm = pcm[: (pcm.size // ch) * ch].reshape(-1, ch).mean(axis=1)
    return pcm, sr


class SapiTTSEngine:
    """Windows' own voices through System.Speech. One PowerShell call per sentence
    (about half a second), so repeated phrases lean on the cache."""

    def __init__(self, speaker: str = "", sample_rate: int = 24_000, cache: bool = True, runner=None):
        if sys.platform != "win32" and runner is None:
            raise RuntimeError("the Windows voice exists only on Windows")
        self.sample_rate = sample_rate if sample_rate in (8_000, 24_000, 48_000) else 24_000
        self._run = runner or _run_powershell
        self._lock = threading.Lock()
        self._cache = TTSCache(_app_dir() / "cache" / "tts") if cache else None
        self.speaker = ""
        self.set_speaker(speaker)

    def set_speaker(self, _name: str = "") -> None:
        try:
            from memory.config_manager import get_ui_setting
            v = str(get_ui_setting("tts_voice_windows", "") or "")
        except Exception:
            v = ""
        with self._lock:
            self.speaker = v

    def synthesize(self, text: str) -> np.ndarray:
        text = (text or "").strip()
        if not text:
            return np.empty(0, dtype=np.float32)
        with self._lock:
            voice = self.speaker
        key = None
        if self._cache is not None and len(text) <= self._cache.max_text:
            key = TTSCache.key(text, voice or "default", self.sample_rate, "sapi1")
            hit = self._cache.get(key)
            if hit is not None:
                return hit
        import tempfile
        fd, out_path = tempfile.mkstemp(suffix=".wav")
        os.close(fd)
        try:
            script = ("Add-Type -AssemblyName System.Speech; "
                      "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
                      "if ($env:AIA_VOICE) { try { $s.SelectVoice($env:AIA_VOICE) } catch {} }; "
                      "$s.SetOutputToWaveFile($env:AIA_OUT); $s.Speak($env:AIA_TEXT); $s.Dispose()")
            self._run(script, {"AIA_VOICE": voice, "AIA_OUT": out_path, "AIA_TEXT": text})
            data = Path(out_path).read_bytes()
        finally:
            try:
                os.unlink(out_path)
            except OSError:
                pass
        pcm, sr = read_wav_mono(data)
        audio = np.clip(_resample(pcm, sr, self.sample_rate), -1.0, 1.0).astype(np.float32, copy=False)
        if key is not None:
            self._cache.put(key, audio)
        return audio


# ---------------------------------------------------------------------------
# OpenAI speech (needs the user's own OpenAI key and internet)
# ---------------------------------------------------------------------------
OPENAI_VOICES = ["onyx", "echo", "ash", "alloy", "sage", "fable", "coral", "nova", "shimmer", "ballad", "verse"]


class OpenAITTSEngine:
    """POST /v1/audio/speech with response_format=pcm: raw 24 kHz 16-bit mono, which is
    exactly what the playback pipeline wants."""
    URL = "https://api.openai.com/v1/audio/speech"
    MODEL = "gpt-4o-mini-tts"

    def __init__(self, speaker: str = "", sample_rate: int = 24_000, cache: bool = True, opener=None):
        self.sample_rate = sample_rate if sample_rate in (8_000, 24_000, 48_000) else 24_000
        self._opener = opener
        self._lock = threading.Lock()
        self._cache = TTSCache(_app_dir() / "cache" / "tts") if cache else None
        self.speaker = "onyx"
        self.set_speaker(speaker)
        if not self._key():
            raise RuntimeError("OpenAI API key is not set (Settings → Voice → OpenAI)")

    @staticmethod
    def _key() -> str:
        try:
            from memory.config_manager import get_ui_setting
            return str(get_ui_setting("openai_api_key", "") or "").strip()
        except Exception:
            return ""

    def set_speaker(self, _name: str = "") -> None:
        try:
            from memory.config_manager import get_ui_setting
            v = str(get_ui_setting("tts_voice_openai", "onyx") or "onyx")
        except Exception:
            v = "onyx"
        with self._lock:
            self.speaker = v if v in OPENAI_VOICES else "onyx"

    def _request(self, text: str, voice: str) -> bytes:
        import json as _json
        import ssl
        import urllib.error
        import urllib.request
        body = _json.dumps({"model": self.MODEL, "input": text, "voice": voice,
                            "response_format": "pcm"}).encode("utf-8")
        if self._opener is not None:
            return self._opener(self.URL, body, self._key())
        try:
            import certifi
            ctx = ssl.create_default_context(cafile=certifi.where())
        except Exception:
            ctx = ssl.create_default_context()
        req = urllib.request.Request(self.URL, data=body, method="POST", headers={
            "Authorization": f"Bearer {self._key()}", "Content-Type": "application/json", "model": "s2.1-pro-free"})
        try:
            with urllib.request.urlopen(req, context=ctx, timeout=45) as r:
                return r.read()
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:160]
            raise RuntimeError(f"OpenAI answered {exc.code}: {detail}") from None

    def synthesize(self, text: str) -> np.ndarray:
        text = (text or "").strip()
        if not text:
            return np.empty(0, dtype=np.float32)
        with self._lock:
            voice = self.speaker
        key = None
        if self._cache is not None and len(text) <= self._cache.max_text:
            key = TTSCache.key(text, voice, self.sample_rate, "openai1")
            hit = self._cache.get(key)
            if hit is not None:
                return hit
        raw = self._request(text, voice)
        if len(raw) < 2:
            raise RuntimeError("OpenAI returned no audio")
        pcm = np.frombuffer(raw[: len(raw) // 2 * 2], dtype="<i2").astype(np.float32) / 32768.0
        audio = _resample(pcm, 24_000, self.sample_rate)
        audio = np.clip(audio, -1.0, 1.0).astype(np.float32, copy=False)
        if key is not None:
            self._cache.put(key, audio)
        return audio


# ---------------------------------------------------------------------------
# Fish Audio (realistic voices and your own cloned ones; needs a Fish Audio key)
# ---------------------------------------------------------------------------

class FishAudioTTSEngine:
    """POST https://api.fish.audio/v1/tts, WAV back. The voice is chosen by the ID of a voice
    model from fish.audio (empty = their default voice). Written from the public API
    description: if a request is refused, the error text shows what Fish answered."""
    URL = "https://api.fish.audio/v1/tts"

    def __init__(self, speaker: str = "", sample_rate: int = 24_000, cache: bool = True, opener=None):
        self.sample_rate = sample_rate if sample_rate in (8_000, 24_000, 48_000) else 24_000
        self._opener = opener
        self._lock = threading.Lock()
        self._cache = TTSCache(_app_dir() / "cache" / "tts") if cache else None
        self.speaker = ""
        self.set_speaker(speaker)
        if not self._key():
            raise RuntimeError("Fish Audio API key is not set (Settings → Voice → Fish Audio)")

    @staticmethod
    def _key() -> str:
        try:
            from memory.config_manager import get_ui_setting
            return str(get_ui_setting("fish_api_key", "") or "").strip()
        except Exception:
            return ""

    def set_speaker(self, _name: str = "") -> None:
        try:
            from memory.config_manager import get_ui_setting
            ref = str(get_ui_setting("fish_reference_id", "") or "").strip()
        except Exception:
            ref = ""
        with self._lock:
            self.speaker = ref

    def _request(self, text: str, ref: str) -> bytes:
        import json as _json
        import ssl
        import urllib.error
        import urllib.request
        payload = {"text": text, "format": "wav", "normalize": True, "latency": "low", "chunk_length": 100}
        if ref:
            payload["reference_id"] = ref
        body = _json.dumps(payload).encode("utf-8")
        if self._opener is not None:
            return self._opener(self.URL, body, self._key())
        try:
            import certifi
            ctx = ssl.create_default_context(cafile=certifi.where())
        except Exception:
            ctx = ssl.create_default_context()
        req = urllib.request.Request(self.URL, data=body, method="POST", headers={
            "Authorization": f"Bearer {self._key()}", "Content-Type": "application/json", "model": "s2.1-pro-free"})
        try:
            with urllib.request.urlopen(req, context=ctx, timeout=45) as r:
                return r.read()
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:160]
            raise RuntimeError(f"Fish Audio answered {exc.code}: {detail}") from None

    def synthesize(self, text: str) -> np.ndarray:
        text = (text or "").strip()
        if not text:
            return np.empty(0, dtype=np.float32)
        with self._lock:
            ref = self.speaker
        key = None
        if self._cache is not None and len(text) <= self._cache.max_text:
            key = TTSCache.key(text, ref or "default", self.sample_rate, "fish1")
            hit = self._cache.get(key)
            if hit is not None:
                return hit
        raw = self._request(text, ref)
        try:
            pcm, sr = read_wav_mono(raw)
        except Exception as exc:
            raise RuntimeError(f"Fish Audio returned something that is not WAV audio: {exc}") from None
        audio = np.clip(_resample(pcm, sr, self.sample_rate), -1.0, 1.0).astype(np.float32, copy=False)
        if key is not None:
            self._cache.put(key, audio)
        return audio


# ---------------------------------------------------------------------------
# Which engine?  "auto": Piper if installed, else Silero.  The user can also pick
# "windows" or "openai" explicitly (Settings → Voice).
# ---------------------------------------------------------------------------

ENGINES = {
    "windows": ("Голос Windows", "встроенный, работает без интернета"),
    "piper":   ("Piper",         "офлайн, русские нейросетевые голоса"),
    "openai":  ("OpenAI",        "естественные голоса, нужен свой ключ"),
    "fish":    ("Fish Audio",    "реалистичные и ваши собственные голоса"),
    "silero":  ("Silero",        "офлайн, запасной вариант (нужен PyTorch)"),
}


def _pref() -> str:
    try:
        from memory.config_manager import get_ui_setting
        return str(get_ui_setting("tts_engine", "auto") or "auto").lower()
    except Exception:
        return "auto"


def detect_engine() -> str:
    pref = _pref()
    if pref in ENGINES:
        return pref
    return "piper" if piper_available() else "silero"


def available_voices() -> list[str]:
    eng = detect_engine()
    if eng == "windows":
        return sapi_voices()
    if eng == "openai":
        return list(OPENAI_VOICES)
    if eng == "fish":
        return []                                     # the voice is an ID typed in the settings
    if eng == "piper":
        return ["jarvis", "deep", "dmitri", "denis", "irina"]
    return ["jarvis", "deep", "aidar", "eugene", "xenia", "baya", "kseniya"]


def voice_setting_key(engine: str) -> str | None:
    """Piper and Silero keep the voice in the main config; Windows and OpenAI have their own."""
    return {"windows": "tts_voice_windows", "openai": "tts_voice_openai", "fish": "fish_reference_id"}.get(engine)


def create_tts_engine(voice: str, sample_rate: int = 24_000):
    """Build the voice engine. With 'auto' a Piper failure falls back to Silero."""
    pref = _pref()
    engine = detect_engine()
    if engine == "windows":
        return SapiTTSEngine(voice, sample_rate)
    if engine == "openai":
        return OpenAITTSEngine(voice, sample_rate)
    if engine == "fish":
        return FishAudioTTSEngine(voice, sample_rate)
    problems: list[str] = []
    if engine == "piper":
        try:
            return PiperTTSEngine(voice, sample_rate)
        except Exception as exc:
            problems.append(f"Piper: {exc}")
            if pref == "piper":
                raise
    try:
        return SileroTTSEngine(voice, sample_rate)
    except Exception as exc:
        problems.append(f"Silero: {exc}")
    raise RuntimeError("No working voice engine. " + " | ".join(problems) +
                       "  Fix: pip install -r requirements-voice.txt")
