"""The share card: a picture of your week (or month, or season) to post in Discord."""

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

import goals

PERIODS = (("week", "This week"), ("last7", "Last 7 days"), ("month", "This month"), ("season", "This season"))
MAX_BARS = 16


@dataclass
class CardData:
    period: str
    title: str
    range_text: str
    name: str
    chests: int = 0
    matches: int = 0
    best: int = 0
    average: float = 0.0
    opened: int = 0
    broken: int = 0
    treasures: int = 0
    streak: int = 0
    bars: list[tuple[str, int]] = field(default_factory=list)  # (label, chests), oldest first
    unit: str = "day"  # what one bar stands for: "day" or "week"


def _span(period: str, today: date, season_start: str) -> tuple[date, date]:
    """First and last day (inclusive) a period covers, never going past today for the data."""
    if period == "week":
        monday = today - timedelta(days=today.weekday())
        return monday, monday + timedelta(days=6)
    if period == "last7":
        return today - timedelta(days=6), today
    if period == "month":
        return today.replace(day=1), today
    try:
        return date.fromisoformat(season_start), today
    except ValueError:
        return today.replace(day=1), today


def _range_text(first: date, last: date) -> str:
    def short(day: date) -> str:
        return f"{day:%b} {day.day}"

    if first.year == last.year:
        return f"{short(first)} - {short(last)}, {last.year}"
    return f"{short(first)}, {first.year} - {short(last)}, {last.year}"


def collect(history: list[dict], period: str, today: date, season_start: str = "", name: str = "",
            daily_goal: int = 0, today_count: int = 0) -> CardData:
    first, last = _span(period, today, season_start)
    chosen, per_day = [], {}
    for match in history:
        try:
            day = datetime.fromisoformat(match["start"]).date()
        except (KeyError, ValueError):
            continue
        if first <= day <= last:
            chosen.append(match)
            per_day[day] = per_day.get(day, 0) + int(match["chests"])
    chests = sum(int(m["chests"]) for m in chosen)
    title = dict(PERIODS).get(period, "My chests")
    card = CardData(
        period, title, _range_text(first, last), name.strip(),
        chests=chests, matches=len(chosen), best=max((int(m["chests"]) for m in chosen), default=0),
        average=chests / len(chosen) if chosen else 0.0,
        broken=sum(int(m.get("broken") or 0) for m in chosen),
        treasures=sum(len(m.get("treasures") or []) for m in chosen),
    )
    card.opened = chests - card.broken
    if daily_goal:
        card.streak = goals.streak(goals.per_day(history), daily_goal, today, today_count)

    if period == "season" and (last - first).days >= 14:
        # a long span is shown by week, newest weeks last, so the chart doesn't get crowded
        starts = []
        day = first - timedelta(days=first.weekday())
        while day <= last:
            starts.append(day)
            day += timedelta(days=7)
        card.unit = "week"
        for start in starts[-MAX_BARS:]:
            total = sum(n for d, n in per_day.items() if start <= d < start + timedelta(days=7))
            card.bars.append((f"{start:%b} {start.day}", total))
    else:
        day = first
        while day <= last and len(card.bars) < 31:
            label = f"{day:%a}"[:2] if period in ("week", "last7") else str(day.day)
            card.bars.append((label, per_day.get(day, 0)))
            day += timedelta(days=1)
    return card
