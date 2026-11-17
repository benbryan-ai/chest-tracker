"""Backing up and restoring the app's own data: the lifetime total, the match history and the change list.

Settings are left out on purpose: they hold the Discord webhook addresses and bot details, which shouldn't end up
in a file that gets shared. A restore is checked by loading it the way the app loads its own files, and the
current data is saved first so a restore can itself be undone.
"""

import json
import tempfile
from datetime import date, datetime
from pathlib import Path

from adjustments import Adjustments
from marks import TreasureMarks
from matches import MatchLog
from settings import Stats, _write_json, read_json
from version import VERSION

FILES = ("stats.json", "matches.json", "adjustments.json", "treasure_marks.json")
MAX_BYTES = 40_000_000
KEEP_DAILY = 7
KEEP_SAFETY = 3
FORMAT = 1


class BadBackup(ValueError):
    pass


def make(folder: Path, now: datetime | None = None) -> dict:
    files = {}
    for name in FILES:
        value = read_json(folder / name)
        if value is not None:
            files[name] = value
    return {"app": "chest-tracker", "format": FORMAT, "version": VERSION,
            "created": (now or datetime.now()).isoformat(timespec="seconds"), "files": files}


def write(folder: Path, path: Path, now: datetime | None = None) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".part")
    temp.write_text(json.dumps(make(folder, now), indent=1), encoding="utf-8")
    temp.replace(path)
    return path


def read(path: Path) -> dict:
    """The backup's contents, or BadBackup saying what's wrong."""
    try:
        if path.stat().st_size > MAX_BYTES:
            raise BadBackup("That file is too big to be a backup.")
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as error:
        raise BadBackup("That file couldn't be read as a backup.") from error
    if not isinstance(data, dict) or data.get("app") != "chest-tracker" or not isinstance(data.get("files"), dict):
        raise BadBackup("That isn't a Chest Tracker backup.")
    if data.get("format") != FORMAT:
        raise BadBackup("That backup is from a different version of the app and can't be used.")
    if not data["files"] or any(k not in FILES or not isinstance(v, dict) for k, v in data["files"].items()):
        raise BadBackup("That backup is empty or damaged.")
    return data


def load(data: dict) -> tuple[Stats, MatchLog, Adjustments, TreasureMarks]:
    """The data objects as the app would load them from this backup (nothing touches the real files)."""
    with tempfile.TemporaryDirectory() as temp:
        folder = Path(temp)
        for name, value in data["files"].items():
            _write_json(folder / name, value)
        stats, matches, adjustments = Stats(folder), MatchLog(folder / "matches.json"), Adjustments(folder / "adjustments.json")
        marks = TreasureMarks(folder / "treasure_marks.json")
    if "stats.json" in data["files"] and not isinstance(data["files"]["stats.json"].get("total"), int):
        raise BadBackup("That backup's total is missing or damaged.")
    return stats, matches, adjustments, marks


def describe(data: dict) -> str:
    stats, matches, _, _ = load(data)
    when = str(data.get("created", "")).replace("T", " ")
    return f"Made {when}: total {stats.total:,} chests, {len(matches.history):,} matches."


def _prune(folder: Path, pattern: str, keep: int) -> None:
    for old in sorted(folder.glob(pattern))[:-keep]:
        try:
            old.unlink()
        except OSError:
            pass


def backups_folder(folder: Path) -> Path:
    return folder / "backups"


def has_data(folder: Path) -> bool:
    stats = read_json(folder / "stats.json") or {}
    matches = read_json(folder / "matches.json") or {}
    return bool(stats.get("total")) or bool(matches.get("history"))


def auto_backup(folder: Path, today: date | None = None) -> Path | None:
    """One backup a day, keeping the last week. Does nothing when there's no data or today's already exists."""
    target = backups_folder(folder) / f"backup-{(today or date.today()).isoformat()}.json"
    if target.exists() or not has_data(folder):
        return None
    try:
        write(folder, target)
    except OSError:
        return None
    _prune(backups_folder(folder), "backup-*.json", KEEP_DAILY)
    return target


def safety_backup(folder: Path, now: datetime | None = None) -> Path | None:
    """A copy of the current data, made right before a restore replaces it."""
    moment = now or datetime.now()
    target = backups_folder(folder) / f"before-restore-{moment:%Y-%m-%d-%H%M%S}.json"
    try:
        write(folder, target, moment)
    except OSError:
        return None
    _prune(backups_folder(folder), "before-restore-*.json", KEEP_SAFETY)
    return target
