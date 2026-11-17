"""Counts a finished match's chests from Fortnite's replay file, using the bundled chest-scan program.

The screen count can't see chests that are broken rather than opened. The replay records every
chest the player searched, so once the match is over the app asks chest-scan to read it and uses
that number instead. If anything goes wrong, the screen count stands.
"""

import json
import logging
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

log = logging.getLogger("chest-tracker")

SCANNER_NAME = "chest-scan.exe" if os.name == "nt" else "chest-scan"
SLACK = timedelta(seconds=90)  # clocks and the first-chest time are only roughly aligned
POLL_SECONDS = 6.0
GIVE_UP_AFTER = 240.0  # Fortnite can take a while to finish writing the replay
SCAN_TIMEOUT = 120


@dataclass
class ReplayCount:
    file: str
    chests: int
    opened: int
    broken: int
    start: datetime  # local time, no timezone
    end: datetime
    note: str = ""
    kinds: dict = field(default_factory=dict)  # "Chest": 12, "Buried chest": 2 ...
    treasures: list = field(default_factory=list)  # {"name", "kind", "golden", "at"}
    chest_times: list = field(default_factory=list)  # when each chest was searched, Unix seconds (UTC)


def default_replay_folder() -> Path:
    base = os.environ.get("LOCALAPPDATA")
    root = Path(base) if base else Path.home() / "AppData" / "Local"
    return root / "FortniteGame" / "Saved" / "Demos"


def find_scanner() -> Path | None:
    """The chest-scan program that ships with the app (or sits next to it), if there is one."""
    override = os.environ.get("CHEST_TRACKER_SCANNER")
    folders = [Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))]
    if getattr(sys, "frozen", False):
        folders.append(Path(sys.executable).resolve().parent)
    candidates = ([Path(override)] if override else []) + [f / SCANNER_NAME for f in folders]
    return next((c for c in candidates if c.is_file()), None)


def _local(moment: datetime) -> datetime:
    """A moment as plain local time, the way the match log stores it."""
    if moment.tzinfo is None:
        return moment
    return moment.astimezone().replace(tzinfo=None)


def _utc_to_local(text: str) -> datetime:
    """A .NET round-trip time such as 2026-11-14T21:32:16.1234567Z, as plain local time."""
    text = re.sub(r"(\.\d{6})\d+", r"\1", text.strip().replace("Z", "+00:00"))
    moment = datetime.fromisoformat(text)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return _local(moment)


def clean_kinds(raw) -> dict:
    """A {name: count} table of chest types, keeping only sensible entries."""
    if not isinstance(raw, dict):
        return {}
    kinds = {}
    for name, number in raw.items():
        try:
            if str(name) and int(number) > 0:
                kinds[str(name)[:60]] = int(number)
        except (TypeError, ValueError):
            continue
    return kinds


MAX_TIMES = 600


def clean_times(raw) -> list:
    if not isinstance(raw, list):
        return []
    return [t for t in raw[:MAX_TIMES] if isinstance(t, int) and not isinstance(t, bool) and 0 < t < 4_000_000_000]


def clean_treasures(raw) -> list:
    """Treasure finds as {"name", "kind", "golden", "at"}; anything malformed is dropped."""
    found = []
    for t in raw[:50] if isinstance(raw, list) else []:
        if not isinstance(t, dict) or not isinstance(t.get("Name"), str) or not t["Name"].strip():
            continue
        at = t.get("At")
        kind = t.get("Kind")
        found.append({
            "name": t["Name"].strip()[:120], "kind": kind if isinstance(kind, str) and len(kind) <= 20 else None,
            "prize_id": t["PrizeId"][:80] if isinstance(t.get("PrizeId"), str) else None,
            "golden": t.get("Golden") is True,
            "at": at if isinstance(at, int) and not isinstance(at, bool) and 0 < at < 4_000_000_000 else None,
        })
    return found


def parse_scan(entry: dict) -> ReplayCount | None:
    """One finished replay from chest-scan's JSON, or None if it isn't a readable finished match."""
    if not isinstance(entry, dict) or entry.get("Status") != "ok":
        return None
    try:
        start = _utc_to_local(str(entry["StartUtc"]))
        seconds = int(entry.get("DurationSeconds") or 0)
        chests = int(entry["Chests"])
        opened = int(entry.get("Opened", chests))
        broken = int(entry.get("Broken", 0))
    except (KeyError, TypeError, ValueError):
        return None
    if chests < 0 or seconds <= 0:
        return None
    note = str(entry.get("WhyNot") or "") if entry.get("CountsAsMatch") is False else ""
    return ReplayCount(str(entry.get("File", "")), chests, opened, broken, start, start + timedelta(seconds=seconds), note,
                       clean_kinds(entry.get("Kinds")), clean_treasures(entry.get("Treasures")),
                       clean_times(entry.get("ChestTimes")))


def run_scan(scanner: Path, files: list[Path], timeout: float = SCAN_TIMEOUT) -> list[ReplayCount]:
    """Ask chest-scan to read these replays. Returns the ones that were readable and finished."""
    if not files:
        return []
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        done = subprocess.run(
            [str(scanner), "--json", "--timeout", str(int(timeout)), *map(str, files)],
            capture_output=True, timeout=timeout + 30, creationflags=flags,
        )
        entries = json.loads(done.stdout.decode("utf-8-sig"))
    except (OSError, subprocess.SubprocessError, ValueError, UnicodeDecodeError) as error:
        log.warning("The replay scanner failed: %s", error)
        return []
    if not isinstance(entries, list):
        return []
    return [r for r in (parse_scan(e) for e in entries) if r is not None]


def recent_replays(folder: Path, since: datetime) -> list[Path]:
    """Replay files written to since `since` (local time), newest last."""
    try:
        found = [p for p in folder.glob("*.replay") if datetime.fromtimestamp(p.stat().st_mtime) >= since]
    except OSError:
        return []
    return sorted(found, key=lambda p: p.stat().st_mtime)


def pick_replay(counts: list[ReplayCount], first_chest: datetime) -> ReplayCount | None:
    """The replay that was recording when the match's first chest was searched."""
    holding = [c for c in counts if c.start - SLACK <= first_chest <= c.end + SLACK]
    return max(holding, key=lambda c: c.start) if holding else None


@dataclass
class Miss:
    """Why no replay count came back: "folder" (not found), "none" (nothing saved for the match), "unreadable"."""

    reason: str


MISS_TEXT = {
    "folder": "Fortnite's replay folder wasn't found. Check the folder in Settings.",
    "none": "No replay was saved for that match. Is Record Replays turned on in Fortnite's settings?",
    "unreadable": "A replay was found but couldn't be read. A Fortnite update may have changed the replay format.",
}


def diagnose(first_chest: datetime, folder: Path) -> Miss:
    """After giving up: was the folder missing, was nothing saved, or was a saved replay unreadable?"""
    if not folder.is_dir():
        return Miss("folder")
    return Miss("unreadable" if recent_replays(folder, first_chest - SLACK) else "none")


def count_match(
    first_chest: datetime,
    folder: Path,
    scanner: Path,
    stop: Callable[[], bool] = lambda: False,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
    scan: Callable[[Path, list[Path]], list[ReplayCount]] = run_scan,
) -> ReplayCount | None:
    """Wait for the replay of the match that began at `first_chest` and read it. None if it never shows up."""
    deadline = clock() + GIVE_UP_AFTER
    while not stop():
        files = recent_replays(folder, first_chest - SLACK)
        found = pick_replay(scan(scanner, files), first_chest) if files else None
        if found is not None:
            return found
        if clock() >= deadline:
            return None
        sleep(POLL_SECONDS)
    return None
