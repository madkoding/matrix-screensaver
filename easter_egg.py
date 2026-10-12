"""Timing for the occasional typed message ("Wake up, Neo...").

Renderer-agnostic: `update(t)` returns what to draw right now, or None.
"""
import random

from settings import PHRASES

FIRST_DELAY = (12.0, 25.0)   # seconds before the first message
GAP = (45.0, 90.0)           # seconds between messages
TYPE_SPEED = 0.11            # seconds per character
HOLD = 2.8                   # seconds the finished message stays
FADE = 1.2                   # seconds to fade out


class EasterEgg:
    def __init__(self, enabled=True, rng=None):
        self.enabled = enabled and bool(PHRASES)
        self.rng = rng or random.Random()
        self.next_start = self.rng.uniform(*FIRST_DELAY)
        self.phrase = ""
        self.start = None

    def update(self, t):
        """-> (text, chars_shown, alpha, cursor_on) or None."""
        if not self.enabled:
            return None
        if self.start is None:
            if t < self.next_start:
                return None
            self.start = t
            self.phrase = self.rng.choice(PHRASES)
        age = t - self.start
        type_time = len(self.phrase) * TYPE_SPEED
        if age < type_time:
            shown, alpha = int(age / TYPE_SPEED) + 1, 1.0
        elif age < type_time + HOLD:
            shown, alpha = len(self.phrase), 1.0
        elif age < type_time + HOLD + FADE:
            shown = len(self.phrase)
            alpha = 1.0 - (age - type_time - HOLD) / FADE
        else:
            self.start = None
            self.next_start = t + self.rng.uniform(*GAP)
            return None
        cursor = int(age * 2.2) % 2 == 0
        return self.phrase, min(shown, len(self.phrase)), alpha, cursor
