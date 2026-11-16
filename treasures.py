"""Treasure hunt numbers from the match history and the hunt's data (see content.py)."""

import math
from dataclasses import dataclass
from datetime import datetime, timezone

from content import KIND_NAMES, Content, Odds, Prize, Week


@dataclass
class Find:
    name: str
    kind: str | None
    prize_id: str | None
    when: datetime | None  # UTC
    match_start: datetime  # UTC


@dataclass
class Chance:
    odds: Odds
    chests: int
    at_least_once: float  # 0..1
    expected: float
    never_log: float  # ln(chance of never), for when "at least once" rounds to 1


def _utc(local_iso: str) -> datetime:
    """A match start as stored (plain local time) as a UTC moment."""
    return datetime.fromisoformat(local_iso).astimezone(timezone.utc)


def finds(history: list[dict]) -> list[Find]:
    """Every treasure found in the history, newest first."""
    out = []
    for m in history:
        for t in m.get("treasures", []):
            at = t.get("at")
            out.append(Find(t["name"], t.get("kind"), t.get("prize_id"),
                            datetime.fromtimestamp(at, timezone.utc) if at else None, _utc(m["start"])))
    return sorted(out, key=lambda f: f.when or f.match_start, reverse=True)


def counted_chests(history: list[dict], start: datetime, end: datetime | None = None) -> tuple[list[datetime], int]:
    """Chests in a period: those with a recorded time, and how many more have only a match to go by."""
    times, plain = [], 0
    for m in history:
        recorded = m.get("chest_times")
        if recorded:
            moments = [datetime.fromtimestamp(t, timezone.utc) for t in recorded]
            times += [t for t in moments if t >= start and (end is None or t < end)]
        else:
            began = _utc(m["start"])
            if began >= start and (end is None or began < end):
                plain += m["chests"]
    return times, plain


def chance(content: Content, odds: Odds, times: list[datetime], plain: int) -> Chance:
    """Chance of finding the prize at least once, with Treasure Hour boosts applied to each timed chest."""
    p = 1.0 / odds.one_in
    never = max(0, plain) * math.log1p(-p)
    expected = max(0, plain) * p
    for t in times:
        q = min(0.999, p * content.boost(odds.kind, t))
        never += math.log1p(-q)
        expected += q
    return Chance(odds, len(times) + max(0, plain), -math.expm1(never), expected, never)


def chances(content: Content, history: list[dict], now: datetime) -> list[Chance]:
    """One row per kind of prize. Weekly prizes only count the shown week's chests, the others the whole hunt."""
    start = content.hunt_start()
    if start is None:
        return []
    week = content.shown_week(now)
    out = []
    for odds in content.odds:
        if odds.weekly and week:
            times, plain = counted_chests(history, week.start, week.end)
        else:
            times, plain = counted_chests(history, start)
        out.append(chance(content, odds, times, plain))
    return out


def matches_prize(find: Find, prize: Prize) -> bool:
    if find.prize_id and any(find.prize_id.lower() == i.lower() for i in prize.prize_ids):
        return True
    return find.name.strip().lower() == prize.name.strip().lower()


def collection(content: Content, all_finds: list[Find], week: Week | None) -> list[tuple[Prize, int]]:
    """The shown week's prizes (and Pirate Shop Access) with how many times each was found."""
    prizes = list(week.prizes) if week else []
    if content.pirate_shop:
        prizes.append(content.pirate_shop)
    return [(p, sum(1 for f in all_finds if matches_prize(f, p))) for p in prizes]


def kind_name(kind: str) -> str:
    return KIND_NAMES.get(kind, kind)


def percent(value: float) -> str:
    """A chance as text: 'under 0.01%', '12.5%', or '99.99%' (never a misleading 100%)."""
    if value <= 0:
        return "0%"
    if value < 0.0001:
        return "under 0.01%"
    if value >= 0.99995:
        return "over 99.99%"
    return f"{value * 100:.2f}%" if value < 0.1 else f"{value * 100:.1f}%"
