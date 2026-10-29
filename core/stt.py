"""
Speech-to-Text engines for AI Companion.

Whisper  – offline transcription via faster-whisper (VAD-buffered)
Vosk     – offline streaming transcription (lighter)
GigaAM   – offline Russian ASR via the Sber GigaAM-v3 model
"""
import json
import os
from pathlib import Path
import sys
import threading
import numpy as np


class WhisperSTT:
    """Offline transcription using faster-whisper."""

    def __init__(self, model_name: str = "base", language: str | None = None):
        import os
        from faster_whisper import WhisperModel
        print(f"[STT] Loading Whisper '{model_name}'…")
        # Portable builds include the default model so first use never waits
        # for a network download. In source checkouts, keep the Hugging Face
        # cache behavior as a fallback.
        bundled_model = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1])) / "models" / f"whisper-{model_name}"
        model_source = str(bundled_model) if bundled_model.is_dir() else model_name
        try:
            import torch
            device  = "cuda" if torch.cuda.is_available() else "cpu"
            compute = "float16" if device == "cuda" else "int8"
        except Exception:
            device, compute = "cpu", "int8"

        try:
            self._model = WhisperModel(model_source, device=device, compute_type=compute)
        except Exception as _first_err:
            # Offline flag set but model not cached yet → clear flags and download once.
            # Keywords cover multiple huggingface_hub error message variants across versions.
            _e = str(_first_err).lower()
            _offline_keywords = (
                "offline", "not found", "cache", "localentry",
                "does not exist", "outgoing", "local_files_only",
            )
            if any(k in _e for k in _offline_keywords):
                print(f"[STT] Whisper '{model_name}' not in local cache — downloading (one-time, internet required)…")
                os.environ.pop("HF_HUB_OFFLINE",      None)
                os.environ.pop("TRANSFORMERS_OFFLINE", None)
                os.environ.pop("HF_DATASETS_OFFLINE",  None)
                try:
                    self._model = WhisperModel(model_source, device=device, compute_type=compute)
                except Exception as _dl_err:
                    raise RuntimeError(
                        f"Whisper '{model_name}' model download failed.\n"
                        f"Internet access is required the first time to download the speech model (~75–290 MB).\n"
                        f"After the first download it runs fully offline.\n"
                        f"Details: {_dl_err}"
                    ) from _dl_err
            else:
                raise

        self._language = None if (not language or language.strip().lower() == "auto") else language.strip().lower()
        print(f"[STT] Whisper '{model_name}' ready ({device})")

    def transcribe(self, audio: np.ndarray) -> str:
        """Transcribe a float32 mono 16 kHz numpy array. Returns transcript string."""
        try:
            segments, _ = self._model.transcribe(
                audio,
                language=self._language,
                beam_size=5,                       # more reliable Russian recognition
                best_of=1,
                condition_on_previous_text=False,  # no hallucinations, faster
                vad_filter=True,
                vad_parameters={"min_silence_duration_ms": 300},
            )
            return " ".join(s.text for s in segments).strip()
        except Exception as e:
            print(f"[STT] Transcription error: {e}")
            raise


class VoskSTT:
    """Streaming transcription using Vosk."""

    def __init__(self, model_path: str | None = None, language: str = "en-us"):
        from vosk import Model, KaldiRecognizer
        print("[STT] Loading Vosk model…")
        if model_path:
            model = Model(model_path)
        else:
            lang  = language.strip().lower() if language and language.strip().lower() != "auto" else "en-us"
            model = Model(lang=lang)
        self._rec = KaldiRecognizer(model, 16000)
        print("[STT] Vosk ready.")

    def process_chunk(self, audio_bytes: bytes) -> tuple[str, bool]:
        """Feed raw int16 LE PCM bytes. Returns (text, is_final)."""
        if self._rec.AcceptWaveform(audio_bytes):
            result = json.loads(self._rec.Result())
            return result.get("text", ""), True
        partial = json.loads(self._rec.PartialResult())
        return partial.get("partial", ""), False


class GroqWhisperSTT:
    """Fast Russian speech recognition via Groq's Whisper large-v3-turbo API."""

    URL = "https://api.groq.com/openai/v1/audio/transcriptions"

    def __init__(self, api_key: str | None = None):
        from memory.config_manager import get_ui_setting
        self._api_key = (api_key or get_ui_setting("groq_api_key", "") or "").strip()
        if not self._api_key:
            raise RuntimeError("Groq API key is not configured")

    def transcribe(self, audio: np.ndarray) -> str:
        import io
        import wave
        import requests

        pcm = np.clip(np.asarray(audio, dtype=np.float32), -1.0, 1.0)
        pcm = (pcm * 32767).astype("<i2")
        wav = io.BytesIO()
        with wave.open(wav, "wb") as out:
            out.setnchannels(1)
            out.setsampwidth(2)
            out.setframerate(16000)
            out.writeframes(pcm.tobytes())
        response = requests.post(
            self.URL,
            headers={"Authorization": f"Bearer {self._api_key}"},
            data={"model": "whisper-large-v3-turbo", "language": "ru", "response_format": "json"},
            files={"file": ("speech.wav", wav.getvalue(), "audio/wav")},
            timeout=40,
        )
        response.raise_for_status()
        return str(response.json().get("text", "")).strip()


class GigaAMSTT:
    """Offline Russian transcription using the official GigaAM-v3 e2e RNNT."""

    SAMPLE_RATE = 16_000
    MAX_SECONDS = 24

    def __init__(self):
        import os
        import tempfile
        # Keep checkpoints outside the one-file EXE so they survive app updates
        # and do not inflate every executable by hundreds of megabytes.
        local_app_data = os.environ.get("LOCALAPPDATA")
        cache_root = (Path(local_app_data) / "AI Assistant" / "models" / "gigaam"
                      if local_app_data else Path.home() / ".cache" / "gigaam")
        cache_root.mkdir(parents=True, exist_ok=True)
        print("[STT] Loading GigaAM-v3 e2e RNNT (first run downloads the model)…")
        try:
            import gigaam
        except Exception as exc:
            raise RuntimeError(
                "GigaAM runtime is not installed in this build. "
                "Choose Groq or Gemini in Settings → Speech Recognition."
            ) from exc

        self._model = gigaam.load_model(
            "v3_e2e_rnnt", device="cpu", download_root=str(cache_root)
        )
        self._temp_dir = Path(tempfile.gettempdir()) / "AICompanion-GigaAM"
        self._temp_dir.mkdir(parents=True, exist_ok=True)
        print(f"[STT] GigaAM ready; model cache: {cache_root}")

    def transcribe(self, audio: np.ndarray) -> str:
        """Transcribe float32 mono 16 kHz audio; split only if it exceeds model limit."""
        import wave

        pcm = np.clip(np.asarray(audio, dtype=np.float32), -1.0, 1.0)
        if pcm.size == 0:
            return ""
        max_samples = self.SAMPLE_RATE * self.MAX_SECONDS
        texts = []
        # GigaAM's short-form API rejects clips above 25 seconds. Keep a one
        # second margin and transcribe pieces sequentially for unusual long turns.
        for start in range(0, len(pcm), max_samples):
            part = (pcm[start:start + max_samples] * 32767).astype("<i2")
            wav_path = self._temp_dir / f"utterance-{os.getpid()}-{threading.get_ident()}.wav"
            try:
                with wave.open(str(wav_path), "wb") as out:
                    out.setnchannels(1)
                    out.setsampwidth(2)
                    out.setframerate(self.SAMPLE_RATE)
                    out.writeframes(part.tobytes())
                result = self._model.transcribe(str(wav_path))
                text = getattr(result, "text", result)
                if str(text).strip():
                    texts.append(str(text).strip())
            finally:
                try:
                    wav_path.unlink(missing_ok=True)
                except OSError:
                    pass
        return " ".join(texts)
