"""Brings chest history in from other trackers that read replays: ChestCounter (L) and chest-tracker (D).

Only reads their files. What each shows as its total is what is offered here, so the numbers agree.
"""

import json
import os
import re
from dataclasses import dataclass, field
from datetime import timedelta, timezone
from pathlib import Path

from replays import _utc_to_local

SEASON_MAPS = ("/delilah/maps/delilah_terrain",)  # the map ChestCounter counts: this season's
BR_PLAYLIST = re.compile(
    r"^Playlist_(Default(Solo|Duo|Duos|Trio|Trios|Squad|Squads)|Trios|NoBuildBR_(Solo|Duo|Duos|Trio|Trios|Squad|Squads))$",
    re.IGNORECASE,
)


@dataclass
class ImportOffer:
    source: str  # "ChestCounter" or "chest-tracker"
    label: str  # who it is for, e.g. the player's name
    chests: int  # their total: matches + hand-added
    matches: list[dict] = field(default_factory=list)  # start, end, chests, opened, broken
    manual: int = 0
    skipped: int = 0  # matches of other modes they don't count either

    @property
    def note(self) -> str:
        return f"Imported from {self.source}: {self.label}"


def _field(obj, name, default=None):
    """A value from a JSON object, ignoring upper/lower case of the name."""
    if isinstance(obj, dict):
        for key, value in obj.items():
            if str(key).lower() == name.lower():
                return value
    return default


def _load(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return None


FRENCH_KINDS = {
    "Coffre": "Chest", "Coffre rare": "Rare chest", "Coffre enterré": "Buried chest",
    "Coffre d'esprit (rare)": "Sprite chest (rare)", "Coffre des affiches d'esprit": "Sprite poster chest",
    "Autre coffre": "Other chest",
}


def _kinds(entry) -> dict:
    """How many of each chest type, from the other tracker's per-chest list (French names turned to English)."""
    found: dict = {}
    chests = _field(entry, "Chests")
    for c in chests if isinstance(chests, list) else []:
        name = str(_field(c, "Kind") or "")
        if name:
            name = FRENCH_KINDS.get(name, name)
            found[name] = found.get(name, 0) + 1
    return found


def _treasures(entry, start, lookup) -> list[dict]:
    """Treasure finds from the other tracker's match, with names looked up from the hunt data when it knows the prize."""
    finds = []
    raw = _field(entry, "TreasureFinds")
    for t in raw[:50] if isinstance(raw, list) else []:
        prize_id = _field(t, "PrizeId")
        prize_id = prize_id if isinstance(prize_id, str) else None
        known = lookup(prize_id) if (lookup and prize_id) else None
        name = known[0] if known else str(_field(t, "Item") or "").strip()
        if not name:
            continue
        seconds = _field(t, "ObtainedAtSeconds")
        at = int(start.astimezone(timezone.utc).timestamp() + seconds) if isinstance(seconds, (int, float)) else None
        finds.append({"name": name[:120], "kind": known[1] if known else None, "prize_id": prize_id,
                      "golden": _field(t, "FromGoldenChest") is True, "at": at})
    return finds


def _chest_times(entry, start) -> list[int]:
    chests = _field(entry, "Chests")
    base = start.astimezone(timezone.utc).timestamp()
    return sorted(int(base + c_seconds) for c in (chests[:600] if isinstance(chests, list) else [])
                  if isinstance(c_seconds := _field(c, "TimeSeconds"), (int, float)) and not isinstance(c_seconds, bool))


def _match(entry, total: int, broken: int, lookup=None) -> dict | None:
    if total < 1:
        return None
    try:
        start = _utc_to_local(str(_field(entry, "MatchStartUtc") or _field(entry, "AnalyzedAtUtc")))
    except (TypeError, ValueError):
        return None
    seconds = _field(entry, "DurationSeconds")
    end = start + timedelta(seconds=int(seconds)) if isinstance(seconds, (int, float)) and seconds > 0 else start
    record = {
        "start": start.isoformat(timespec="seconds"), "end": end.isoformat(timespec="seconds"),
        "chests": total, "opened": max(0, total - broken), "broken": broken, "kinds": _kinds(entry),
    }
    finds = _treasures(entry, start, lookup)
    if finds:
        record["treasures"] = finds
    times = _chest_times(entry, start)
    if times:
        record["chest_times"] = times
    return record


def _broken(entry) -> int:
    chests = _field(entry, "Chests")
    return sum(1 for c in chests if isinstance(c, dict) and _field(c, "Destroyed") is True) if isinstance(chests, list) else 0


def _counts_in_l(entry) -> bool:
    """ChestCounter's rule: regular Battle Royale, not private, on this season's map."""
    if _field(entry, "IsCustomMatch") is True:
        return False
    if not BR_PLAYLIST.match(str(_field(entry, "Playlist") or "")):
        return False
    game_map = _field(entry, "Map")
    return game_map is None or str(game_map).lower() in SEASON_MAPS


def read_l(path: Path, lookup=None) -> list[ImportOffer]:
    """One offer per account in ChestCounter's data.json (usually just one)."""
    data = _load(path)
    entries = _field(data, "Matches")
    if not isinstance(entries, list):
        return []
    manual_all = _field(data, "ManualChests") or {}
    groups: dict[str, dict] = {}
    skipped = 0
    for entry in entries:
        if not _counts_in_l(entry):
            skipped += 1
            continue
        key = str(_field(entry, "EpicId") or _field(entry, "PlayerName") or "")
        group = groups.setdefault(key, {"name": "", "matches": [], "total": 0})
        group["name"] = str(_field(entry, "PlayerName") or group["name"])
        try:
            opened = int(_field(entry, "ChestsOpened") or 0)
        except (TypeError, ValueError):
            opened = 0
        group["total"] += max(0, opened)
        record = _match(entry, opened, _broken(entry), lookup)
        if record:
            group["matches"].append(record)
    offers = []
    for key, group in groups.items():
        manual = int(_field(manual_all, "") or 0) + (int(_field(manual_all, key) or 0) if key else 0)
        offers.append(ImportOffer("ChestCounter", group["name"] or "unknown account", max(0, group["total"] + manual),
                                  group["matches"], manual, skipped))
    if not offers:
        manual = int(_field(manual_all, "") or 0)
        if manual > 0:
            offers.append(ImportOffer("ChestCounter", "added by hand", manual, [], manual, skipped))
    return sorted(offers, key=lambda o: -o.chests)


def read_d(history: Path, settings: Path | None = None, lookup=None) -> list[ImportOffer]:
    """The offer from chest-tracker's history.json (+ the starting number in settings.json)."""
    data = _load(history)
    entries = _field(data, "Matches")
    if not isinstance(entries, list):
        return []
    matches, total = [], 0
    for entry in entries:
        chests = _field(entry, "Chests")
        count = len(chests) if isinstance(chests, list) else 0
        total += count
        record = _match(entry, count, _broken(entry), lookup)
        if record:
            matches.append(record)
    starting = 0
    if settings is not None:
        try:
            starting = max(0, int(_field(_load(settings), "StartingChests") or 0))
        except (TypeError, ValueError):
            starting = 0
    if not matches and not starting:
        return []
    return [ImportOffer("chest-tracker", "all matches", total + starting, matches, starting)]


def find_offers(appdata: Path | None = None, lookup=None) -> list[ImportOffer]:
    """Whatever the other trackers left on this PC."""
    base = appdata or Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")
    offers = read_l(base / "ChestCounter" / "data.json", lookup)
    offers += read_d(base / "chest-tracker" / "history.json", base / "chest-tracker" / "settings.json", lookup)
    return [o for o in offers if o.chests > 0]
