"""Chests per match: the running count, the saved history and the average/median/best."""

import csv
import statistics
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from settings import _write_json, read_json

MAX_HISTORY = 5000
STALE_AFTER = timedelta(hours=2)  # a match left open this long when the app starts is finished


@dataclass
class MatchStats:
    matches: int
    average: float
    median: float
    best: int


class MatchLog:
    """The match in progress, plus every finished match that had at least one chest.

    A match with no chests is never saved, so it can't pull the average down.
    """

    def __init__(self, path: Path, now: datetime | None = None):
        self.path = path
        self.current = 0
        self.started: datetime | None = None
        self.history: list[dict] = []
        saved = read_json(path) or {}
        try:
            history = saved.get("history", [])
            self.history = [
                {"start": str(m["start"]), "end": str(m["end"]), "chests": int(m["chests"])}
                for m in history
                if int(m["chests"]) >= 1
            ][-MAX_HISTORY:]
            self.current = max(0, int(saved.get("current", 0)))
            if saved.get("started"):
                self.started = datetime.fromisoformat(str(saved["started"]))
        except (KeyError, TypeError, ValueError, AttributeError):
            self.history, self.current, self.started = [], 0, None
        now = now or datetime.now()
        if self.current and (self.started is None or now - self.started > STALE_AFTER):
            self.finish(now)  # an old, forgotten match: close it rather than add to it

    def add(self, amount: int, now: datetime | None = None) -> None:
        """Change this match's count (never below zero)."""
        before = self.current
        self.current = max(0, self.current + amount)
        if before == 0 and self.current > 0:
            self.started = now or datetime.now()
        if self.current == 0:
            self.started = None
        self.save()

    def finish(self, now: datetime | None = None) -> dict | None:
        """Close the current match. Returns the saved record, or None if it had no chests."""
        record = None
        if self.current >= 1:
            end = now or datetime.now()
            record = {
                "start": (self.started or end).isoformat(timespec="seconds"),
                "end": end.isoformat(timespec="seconds"),
                "chests": self.current,
            }
            self.history = (self.history + [record])[-MAX_HISTORY:]
        self.current = 0
        self.started = None
        self.save()
        return record

    def stats(self) -> MatchStats | None:
        counts = [m["chests"] for m in self.history]
        if not counts:
            return None
        return MatchStats(len(counts), statistics.fmean(counts), statistics.median(counts), max(counts))

    def save(self) -> None:
        _write_json(self.path, {
            "current": self.current,
            "started": self.started.isoformat(timespec="seconds") if self.started else None,
            "history": self.history,
        })

    def export_csv(self, destination: Path) -> int:
        """Write the history as a spreadsheet file. Returns how many matches were written."""
        with open(destination, "w", newline="", encoding="utf-8-sig") as out:
            writer = csv.writer(out)
            writer.writerow(["match", "start", "end", "chests"])
            for number, m in enumerate(self.history, 1):
                writer.writerow([number, m["start"], m["end"], m["chests"]])
        return len(self.history)
