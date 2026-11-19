"""Treasures the player ticked off by hand, for the ones a replay didn't show."""

from datetime import date
from pathlib import Path

from chest_tracker.data.settings import _write_json, read_json


class TreasureMarks:
    def __init__(self, path: Path):
        self.path = path
        self.found: dict[str, str] = {}  # prize id -> the day it was ticked
        saved = read_json(path) or {}
        raw = saved.get("found")
        if isinstance(raw, dict):
            self.found = {str(k)[:60]: str(v)[:10] for k, v in list(raw.items())[:500] if isinstance(k, str)}

    def is_marked(self, prize_id: str) -> bool:
        return prize_id in self.found

    def set(self, prize_id: str, on: bool, today: date | None = None) -> None:
        if on:
            self.found[prize_id] = (today or date.today()).isoformat()
        else:
            self.found.pop(prize_id, None)
        _write_json(self.path, {"found": self.found})
