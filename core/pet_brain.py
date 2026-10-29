"""
core/pet_brain.py — what the desktop pet DOES, with no drawing code.

The pet idles, walks back and forth, sits, and dances when the assistant talks
or music plays. This module only decides state and horizontal position; the Qt
window (ui_pet.py) draws it and handles dragging. Keeping it GUI-free makes the
behaviour testable.
"""
from __future__ import annotations

import random


class PetBrain:
    SPEED = 64.0            # px per second while walking

    def __init__(self, width_px: int = 128, rng: random.Random | None = None):
        self.rng = rng or random.Random()
        self.width = width_px
        self.left, self.right = 0.0, 1000.0          # allowed range of the pet's left edge
        self.x = 100.0
        self.dir = 1
        self.state = "idle"
        self.t = 0.0                                  # total time, drives animation frames
        self._left_in_state = 2.0
        self._level = 0.0
        self._loud_for = 0.0
        self._dance_until = 0.0

    # ── API ───────────────────────────────────────────────────────────────────
    def set_bounds(self, left: float, right: float) -> None:
        self.left, self.right = float(left), float(max(left, right - self.width))
        self.x = min(max(self.x, self.left), self.right)

    def poke(self, seconds: float = 2.5) -> None:
        """The user clicked the pet."""
        self._dance_until = self.t + seconds
        self._enter("dance", seconds)

    @property
    def frame(self) -> int:
        return int(self.t * 4) % 2

    @property
    def blink(self) -> bool:
        return (self.t % 3.4) < 0.14

    # ── simulation ────────────────────────────────────────────────────────────
    def step(self, dt: float, level: float = 0.0) -> None:
        self.t += dt
        self._level = max(float(level), self._level * (0.92 ** (dt * 30)))
        self._loud_for = self._loud_for + dt if self._level > 0.22 else 0.0
        if self._loud_for > 0.3 and self.state != "dance":
            self._dance_until = self.t + 1.5
            self._enter("dance", 1.5)
        if self.state == "dance":
            if self._level > 0.12:
                self._dance_until = max(self._dance_until, self.t + 0.4)
            if self.t >= self._dance_until:
                self._enter("idle", self.rng.uniform(1.0, 3.0))
            return

        self._left_in_state -= dt
        if self.state == "walk":
            self.x += self.dir * self.SPEED * dt
            if self.x <= self.left:
                self.x, self.dir = self.left, 1
            elif self.x >= self.right:
                self.x, self.dir = self.right, -1
        if self._left_in_state <= 0:
            self._next()

    # ── internals ─────────────────────────────────────────────────────────────
    def _enter(self, state: str, seconds: float) -> None:
        self.state = state
        self._left_in_state = seconds
        if state == "walk":
            self.dir = self.rng.choice((-1, 1))

    def _next(self) -> None:
        r = self.rng.random()
        if self.state == "walk":
            self._enter("sit" if r < 0.35 else "idle", self.rng.uniform(3.0, 8.0))
        elif self.state == "sit":
            self._enter("walk" if r < 0.6 else "idle", self.rng.uniform(3.0, 7.0))
        else:                                           # idle
            if r < 0.5:
                self._enter("walk", self.rng.uniform(3.0, 8.0))
            elif r < 0.75:
                self._enter("sit", self.rng.uniform(3.0, 8.0))
            else:
                self._enter("idle", self.rng.uniform(2.0, 5.0))
