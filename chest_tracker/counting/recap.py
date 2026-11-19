"""Spots Fortnite's end-of-match screen by its two buttons, RETURN TO LOBBY and PLAY AGAIN.

That screen only appears when the whole team is out or you leave, so it marks the end of a
match. The buttons look the same whatever the result, and their words are dark on a bright
button, so the match holds up against the changing background. The XP animation before it
and the spectating screen have no such buttons and are ignored.
"""

import sys
from pathlib import Path

import cv2
import numpy as np
from chest_tracker.system.paths import resource_folder

REFERENCE_HEIGHT = 1200  # the screen height the bundled button images were taken at
BUTTON_SPACING = 84  # at the reference height, RETURN TO LOBBY sits this far above PLAY AGAIN
MIN_SCORE = 0.8
SCALE_STEPS = (0.92, 1.0, 1.08)  # a little slack around the expected size


def _assets() -> Path:
    return resource_folder() / "assets"


class RecapDetector:
    def __init__(self, play_again: np.ndarray, return_to_lobby: np.ndarray):
        self.play_again = play_again
        self.return_to_lobby = return_to_lobby

    @classmethod
    def load_bundled(cls) -> "RecapDetector | None":
        play = cv2.imread(str(_assets() / "recap_play_again.png"), cv2.IMREAD_GRAYSCALE)
        back = cv2.imread(str(_assets() / "recap_return.png"), cv2.IMREAD_GRAYSCALE)
        if play is None or back is None:
            return None
        return cls(play, back)

    @staticmethod
    def _best(view: np.ndarray, template: np.ndarray, scale: float):
        size = (max(8, round(template.shape[1] * scale)), max(4, round(template.shape[0] * scale)))
        resized = cv2.resize(template, size, interpolation=cv2.INTER_AREA)
        if resized.shape[0] >= view.shape[0] or resized.shape[1] >= view.shape[1]:
            return 0.0, (0, 0)
        result = np.nan_to_num(cv2.matchTemplate(view, resized, cv2.TM_CCOEFF_NORMED), nan=-1.0)
        _, score, _, loc = cv2.minMaxLoc(result)
        return float(score), loc

    def is_recap(self, gray: np.ndarray) -> bool:
        """True if a full-screen grayscale frame shows the end-of-match buttons."""
        height, width = gray.shape[:2]
        left = width // 2  # the buttons are on the right-hand half
        view = gray[:, left:]
        base = height / REFERENCE_HEIGHT
        for step in SCALE_STEPS:
            scale = base * step
            play_score, play_at = self._best(view, self.play_again, scale)
            if play_score < MIN_SCORE:
                continue
            back_score, back_at = self._best(view, self.return_to_lobby, scale)
            if back_score < MIN_SCORE:
                continue
            # The two buttons are stacked, one above the other, at a fixed distance.
            gap = play_at[1] - back_at[1]
            if abs(gap - BUTTON_SPACING * scale) <= 14 * scale:
                return True
        return False
