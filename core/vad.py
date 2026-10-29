"""
core/vad.py — "is this block of microphone audio a human voice?"

WHY THIS EXISTS
    The microphone loop used to decide with one number: RMS volume >= 140.
    That opens the gate for a slammed door, a keyboard, a fan spinning up, a
    video playing in the next room — and each of those becomes an "utterance"
    that Whisper dutifully turns into words (often invented ones), which then
    reach the model and can trigger actions nobody asked for.

    Silero VAD is a tiny neural network (~2 MB, ~1 ms per 32 ms of audio on a
    CPU) trained to tell speech from everything else. Volume stays as a cheap
    pre-check, but speech has to actually *sound like speech* to open the gate.

DESIGN
    * The `silero-vad` pip package ships the model inside the wheel, so there is
      no download and no certificate problem.
    * If the package or torch is missing, or anything throws, the gate drops
      back to the old volume threshold — the app keeps working exactly as before.
    * Hysteresis: it takes probability >= START_PROB to open and it only closes
      when probability falls under STOP_PROB, so a breath between two words does
      not chop a phrase in half.
    * Called from the audio callback thread only; it keeps its own buffer.
"""
from __future__ import annotations

from collections import deque

import numpy as np

WINDOW = 512            # Silero VAD at 16 kHz takes exactly 512 samples (32 ms)
START_PROB = 0.50
STOP_PROB = 0.35
MIN_LEVEL = 60.0        # RMS floor: near-digital-silence can never open the gate


class SpeechGate:
    def __init__(self, sample_rate: int = 16000, energy_threshold: float = 140.0,
                 start_prob: float = START_PROB, stop_prob: float = STOP_PROB,
                 min_level: float = MIN_LEVEL, logger=print):
        self._sr = sample_rate
        self._energy = float(energy_threshold)
        self._start = start_prob
        self._stop = stop_prob
        self._min_level = min_level
        self._log = logger
        self._model = None
        self._webrtc = None
        self._torch = None
        self._buf = np.zeros(0, dtype=np.int16)
        self._active = False
        self._prob = 0.0
        self.backend = "energy"
        try:
            if sample_rate != 16000:
                raise ValueError("Silero VAD here expects 16 kHz")
            import torch
            from silero_vad import load_silero_vad
            self._torch = torch
            self._model = load_silero_vad()
            self.backend = "silero"
            self._log("[VAD] Silero VAD loaded.")
        except Exception as exc:
            self._model = None
            self._webrtc = None
            try:   # small, no torch: WebRTC's speech detector
                import webrtcvad
                if sample_rate not in (8000, 16000, 32000, 48000):
                    raise ValueError("unsupported sample rate")
                self._webrtc = webrtcvad.Vad(2)
                self.backend = "webrtc"
                self._wbuf = np.zeros(0, dtype=np.int16)
                self._wflags: deque = deque(maxlen=6)
                self._log("[VAD] WebRTC voice detection active.")
            except Exception as exc2:
                self._log(f"[VAD] Neural VAD unavailable ({exc}); WebRTC VAD unavailable ({exc2}) "
                          f"— using the volume threshold. Install: pip install webrtcvad-wheels")

    @property
    def probability(self) -> float:
        return self._prob

    def reset(self) -> None:
        self._buf = np.zeros(0, dtype=np.int16)
        self._active = False
        self._prob = 0.0
        self._reset_model()

    def _reset_model(self) -> None:
        try:
            if self._model is not None:
                self._model.reset_states()
        except Exception:
            pass

    def is_voice(self, frame, level: float) -> bool:
        """True while the audio looks like speech. `level` is the block's RMS."""
        if self._model is None:
            if self._webrtc is not None:
                try:
                    return self._webrtc_voice(frame, level)
                except Exception as exc:
                    self._log(f"[VAD] WebRTC VAD failed ({exc}) — falling back to volume threshold.")
                    self._webrtc = None
                    self.backend = "energy"
            return level >= self._energy
        try:
            return self._silero(frame, level)
        except Exception as exc:
            self._log(f"[VAD] Silero VAD failed ({exc}) — falling back to volume threshold.")
            self._model = None
            self.backend = "energy"
            return level >= self._energy

    def _webrtc_voice(self, frame, level: float) -> bool:
        """30 ms frames; opens when 3 of the last 6 sound like speech, closes
        when none of them do."""
        x = np.asarray(frame, dtype=np.int16).reshape(-1)
        self._wbuf = np.concatenate((self._wbuf, x)) if self._wbuf.size else x
        step = self._sr * 30 // 1000
        while self._wbuf.size >= step:
            chunk, self._wbuf = self._wbuf[:step], self._wbuf[step:]
            self._wflags.append(bool(self._webrtc.is_speech(chunk.tobytes(), self._sr)))
            n = sum(self._wflags)
            if self._active:
                if n == 0:
                    self._active = False
            elif n >= 3 and level >= self._min_level:
                self._active = True
        return self._active

    def _tensor(self, window: np.ndarray):
        arr = window.astype(np.float32) / 32768.0
        try:
            return self._torch.from_numpy(arr)
        except RuntimeError:
            # torch built against numpy 1.x with numpy 2.x installed
            return self._torch.tensor(arr.tolist(), dtype=self._torch.float32)

    def _silero(self, frame, level: float) -> bool:
        x = np.asarray(frame, dtype=np.int16).reshape(-1)
        self._buf = np.concatenate((self._buf, x)) if self._buf.size else x
        while self._buf.size >= WINDOW:
            window, self._buf = self._buf[:WINDOW], self._buf[WINDOW:]
            with self._torch.inference_mode():
                self._prob = float(self._model(self._tensor(window), self._sr).item())
            if self._active:
                if self._prob < self._stop:
                    self._active = False
                    self._reset_model()
            elif self._prob >= self._start and level >= self._min_level:
                self._active = True
        return self._active
