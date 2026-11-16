"""The treasure hunt data (weeks and prizes, odds, Treasure Hours), kept up to date without a new app version.

The file is ChestCounter's content.json (MIT, by LED-N). A copy ships with the app. The app asks GitHub for a
newer one now and then; a download is used only if it passes a strict check and has a higher revision than what
the app already has, so a broken file can't replace a good one.
"""

import json
import logging
import os
import sys
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import requests

log = logging.getLogger("chest-tracker")

URL = "https://raw.githubusercontent.com/LED-N/Fortnite-ChestCounter/main/content/content.json"
SCHEMA = 1
MAX_BYTES = 300_000
KINDS = ("outfit", "pirate-shop", "car", "pickaxe", "jam", "loading", "gizmo")
PRIZE_KINDS = ("outfit", "pirate-shop", "car", "pickaxe", "jam", "loading")
KIND_NAMES = {
    "outfit": "Gold outfit", "pirate-shop": "Pirate Shop Access", "car": "Vehicle & decal",
    "pickaxe": "Pickaxe or back bling", "jam": "Jam track", "loading": "Loading screen", "gizmo": "Gizmo (any)",
}


@dataclass(frozen=True)
class Prize:
    id: str
    kind: str
    name: str
    prize_ids: tuple[str, ...]


@dataclass(frozen=True)
class Week:
    number: int
    start: datetime
    end: datetime
    title: str
    prizes: tuple[Prize, ...]


@dataclass(frozen=True)
class Odds:
    kind: str
    one_in: int
    weekly: bool


@dataclass(frozen=True)
class Hour:
    start: datetime
    end: datetime
    boosts: dict
    confirmed: bool


@dataclass
class Content:
    revision: int
    updated: str
    odds: list[Odds] = field(default_factory=list)
    pirate_shop: Prize | None = None
    weeks: list[Week] = field(default_factory=list)
    hours: list[Hour] = field(default_factory=list)
    odds_source: str = ""
    hours_source: str = ""

    def find_prize(self, prize_id: str) -> Prize | None:
        wanted = prize_id.lower()
        every = [p for w in self.weeks for p in w.prizes] + ([self.pirate_shop] if self.pirate_shop else [])
        return next((p for p in every if any(i.lower() == wanted for i in p.prize_ids)), None)

    def week_at(self, moment: datetime) -> Week | None:
        return next((w for w in self.weeks if w.start <= moment < w.end), None)

    def shown_week(self, moment: datetime) -> Week | None:
        """The current week, or the last one once the hunt is over."""
        current = self.week_at(moment)
        if current:
            return current
        past = [w for w in self.weeks if w.end <= moment]
        return past[-1] if past else None

    def hunt_start(self) -> datetime | None:
        return self.weeks[0].start if self.weeks else None

    def boost(self, kind: str, moment: datetime) -> float:
        for h in self.hours:
            if h.start <= moment < h.end:
                value = h.boosts.get(kind, 1)
                return value if value > 0 else 1
        return 1


class Invalid(ValueError):
    pass


def _text(value, limit: int, what: str, required: bool = True) -> str:
    if value is None and not required:
        return ""
    if not isinstance(value, str) or (required and not value.strip()) or len(value) > limit:
        raise Invalid(what)
    return value.strip()


def _date(value, what: str) -> datetime:
    try:
        moment = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as error:
        raise Invalid(what) from error
    if moment.tzinfo is None:
        raise Invalid(what)
    return moment.astimezone(timezone.utc)


def _list(value, limit: int, what: str) -> list:
    if not isinstance(value, list) or len(value) > limit:
        raise Invalid(what)
    return value


def _prize(raw, where: str) -> Prize:
    if not isinstance(raw, dict) or raw.get("kind") not in PRIZE_KINDS:
        raise Invalid(where)
    ids = tuple(_text(i, 80, where) for i in _list(raw.get("prizeIds", []), 10, where))
    return Prize(_text(raw.get("id"), 60, where), raw["kind"], _text(raw.get("name"), 120, where), ids)


def parse(data) -> Content:
    """The checked content, or Invalid. Anything odd rejects the whole file."""
    if not isinstance(data, dict) or data.get("schema") != SCHEMA:
        raise Invalid("schema")
    revision = data.get("revision")
    if not isinstance(revision, int) or isinstance(revision, bool) or revision < 1:
        raise Invalid("revision")
    content = Content(revision=revision, updated=_text(data.get("updated"), 40, "updated", required=False))
    seen: set[str] = set()
    for raw in _list(data.get("odds", []), 20, "odds"):
        if not isinstance(raw, dict) or raw.get("kind") not in KINDS:
            raise Invalid("odds kind")
        one_in = raw.get("oneIn")
        if not isinstance(one_in, int) or isinstance(one_in, bool) or not 2 <= one_in <= 100_000_000:
            raise Invalid("odds oneIn")
        content.odds.append(Odds(raw["kind"], one_in, bool(raw.get("weekly"))))
    if data.get("pirateShop") is not None:
        content.pirate_shop = _prize(data["pirateShop"], "pirateShop")
    for raw in _list(data.get("weeks", []), 60, "weeks"):
        if not isinstance(raw, dict) or not isinstance(raw.get("number"), int):
            raise Invalid("week")
        start, end = _date(raw.get("start"), "week start"), _date(raw.get("end"), "week end")
        if end <= start:
            raise Invalid("week dates")
        prizes = tuple(_prize(p, "prize") for p in _list(raw.get("prizes", []), 20, "prizes"))
        for p in prizes:
            if p.id in seen:
                raise Invalid("duplicate prize id")
            seen.add(p.id)
        content.weeks.append(Week(raw["number"], start, end, _text(raw.get("title"), 120, "title", required=False), prizes))
    for raw in _list(data.get("treasureHours", []), 200, "treasureHours"):
        if not isinstance(raw, dict) or not isinstance(raw.get("boosts"), dict):
            raise Invalid("hour")
        start, end = _date(raw.get("start"), "hour start"), _date(raw.get("end"), "hour end")
        if end <= start or (end - start).total_seconds() > 24 * 3600:
            raise Invalid("hour length")
        boosts = {}
        for kind, factor in raw["boosts"].items():
            if kind not in KINDS or not isinstance(factor, (int, float)) or isinstance(factor, bool) or not 1 <= factor <= 100:
                raise Invalid("boost")
            boosts[kind] = float(factor)
        content.hours.append(Hour(start, end, boosts, raw.get("confirmed") is True))
    sources = data.get("sources") if isinstance(data.get("sources"), dict) else {}
    for key, attr in (("odds", "odds_source"), ("treasureHours", "hours_source")):
        link = sources.get(key)
        if isinstance(link, str) and link.startswith("https://") and len(link) <= 300:
            setattr(content, attr, link)
    content.weeks.sort(key=lambda w: w.start)
    return content


def _read(path: Path) -> Content | None:
    try:
        return parse(json.loads(path.read_text(encoding="utf-8-sig")))
    except (OSError, ValueError):
        return None


def bundled_path() -> Path:
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent)) / "assets" / "content.json"


class ContentStore:
    """The newest valid content: the bundled copy, or a downloaded one with a higher revision."""

    def __init__(self, folder: Path, get: Callable = requests.get, url: str = URL):
        self.cache = folder / "content.json"
        self.get, self.url = get, url
        self.content = _read(bundled_path()) or Content(revision=0, updated="")
        cached = _read(self.cache)
        if cached and cached.revision > self.content.revision:
            self.content = cached

    def refresh(self) -> bool:
        """Download and adopt a newer file. True if the content changed. Never raises."""
        try:
            response = self.get(self.url, timeout=10, headers={"Accept": "application/json"})
            if response.status_code != 200 or len(response.content) > MAX_BYTES:
                return False
            fresh = parse(json.loads(response.content.decode("utf-8-sig")))
        except (requests.RequestException, ValueError, UnicodeDecodeError, OSError) as error:
            log.info("Treasure data not refreshed: %s", error)
            return False
        if fresh.revision <= self.content.revision:
            return False
        try:
            handle, name = tempfile.mkstemp(dir=self.cache.parent, suffix=".part")
            with os.fdopen(handle, "wb") as out:
                out.write(response.content)
            os.replace(name, self.cache)
        except OSError:
            log.info("Treasure data could not be saved; using it for now")
        self.content = fresh
        log.info("Treasure data updated to revision %d", fresh.revision)
        return True
