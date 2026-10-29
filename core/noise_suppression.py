"""Streaming DeepFilterNet adapter for the 16 kHz mono microphone path.

The neural runtime runs in a worker thread, never inside PortAudio's callback.
DeepFilterNet itself runs at 48 kHz; this adapter upsamples and downsamples each
continuous microphone stream while keeping the filter state alive between chunks.
"""
from __future__ import annotations

import numpy as np


class DeepFilterNoiseSuppressor:
    def __init__(self) -> None:
        from deepfilternet_rs import DeepFilterNetRealtime

        self._processor = DeepFilterNetRealtime(
            model_path=None,
            atten_lim=30.0,
            log_level="error",
            compensate_delay=False,
            post_filter_beta=0.0,
        )
        self.sample_rate = int(self._processor.sample_rate)
        self._previous = None

    def process_pcm16(self, pcm: np.ndarray) -> np.ndarray:
        """Filter a mono 16 kHz int16 chunk and return same-length int16 PCM."""
        x = np.asarray(pcm, dtype=np.int16).reshape(-1)
        if not x.size:
            return x
        f = x.astype(np.float32) / 32768.0

        # 16 kHz -> 48 kHz, carrying the previous sample across chunk edges.
        if self.sample_rate == 48000:
            if self._previous is None:
                self._previous = float(f[0])
            prev = np.concatenate((np.asarray([self._previous], np.float32), f[:-1]))
            up = np.empty((f.size, 3), dtype=np.float32)
            up[:, 0] = prev + (f - prev) / 3.0
            up[:, 1] = prev + (f - prev) * (2.0 / 3.0)
            up[:, 2] = f
            self._previous = float(f[-1])
            enhanced = self._processor.process_chunk(up.reshape(-1))
            enhanced = np.asarray(enhanced, dtype=np.float32).reshape(-1)
            usable = (enhanced.size // 3) * 3
            if usable:
                # A 3-tap box low-pass before decimation attenuates out-of-band
                # energy and yields exactly one 16 kHz sample per source sample.
                down = enhanced[:usable].reshape(-1, 3).mean(axis=1)
            else:
                down = np.empty(0, dtype=np.float32)
        else:
            raise RuntimeError(f"Unsupported DeepFilterNet sample rate: {self.sample_rate}")

        if down.size != x.size:
            # Preserve frame timing if a runtime version buffers an initial delay.
            aligned = np.zeros(x.size, dtype=np.float32)
            count = min(x.size, down.size)
            aligned[:count] = down[:count]
            down = aligned
        return np.clip(np.rint(down * 32767.0), -32768, 32767).astype(np.int16)

    def close(self) -> None:
        processor = getattr(self, "_processor", None)
        if processor is not None:
            try:
                processor.close()
            except Exception:
                pass
            self._processor = None
