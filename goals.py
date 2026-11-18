"""Daily and per-match chest goals, and the streak of days that reached the daily goal."""

from datetime import date, datetime, timedelta

MAX_GOAL = 9999


def clean_goal(value) -> int:
    """A goal from the settings file: a whole number from 1 to MAX_GOAL, or 0 for "no goal"."""
    try:
        number = int(value)
    except (TypeError, ValueError):
        return 0
    return number if 0 < number <= MAX_GOAL else 0


def fraction(count: int, goal: int) -> float:
    return 0.0 if goal <= 0 else max(0.0, min(1.0, count / goal))


def crossed(before: int, after: int, goal: int) -> bool:
    """True when a count has just reached the goal (and wasn't there before)."""
    return goal > 0 and before < goal <= after


def per_day(history: list[dict]) -> dict[date, int]:
    """Chests per day from the match log, by the day each match started."""
    days: dict[date, int] = {}
    for match in history:
        try:
            day = datetime.fromisoformat(match["start"]).date()
            days[day] = days.get(day, 0) + int(match["chests"])
        except (KeyError, TypeError, ValueError):
            continue
    return days


def streak(days: dict[date, int], goal: int, today: date, today_count: int) -> int:
    """How many days in a row reached the goal.

    Today counts once it has reached the goal; before that it doesn't break the streak,
    because the day isn't over. A missed day before today ends it.
    """
    if goal <= 0:
        return 0
    days = dict(days)
    days[today] = max(days.get(today, 0), today_count)
    run = 1 if days[today] >= goal else 0
    day = today - timedelta(days=1)
    while days.get(day, 0) >= goal:
        run += 1
        day -= timedelta(days=1)
    return run


def progress_text(count: int, goal: int, noun: str) -> str:
    """"37 of 50 today", or "Goal reached: 52 today" once it's done."""
    if goal <= 0:
        return ""
    if count >= goal:
        return f"Goal reached: {count:,} {noun}"
    return f"{count:,} of {goal:,} {noun}"
