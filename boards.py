"""The leaderboards: which periods and categories there are, and how a player's numbers are ranked."""

from datetime import date, datetime, time, timedelta

PERIODS = (("week", "This week"), ("season", "This season"), ("all", "All time"))
CATEGORIES = (
    ("chests", "Most chests"),
    ("best", "Best match"),
    ("average", "Average per match"),
    ("opened", "Chests opened"),
    ("broken", "Chests broken"),
    ("treasures", "Treasures found"),
    ("matches", "Matches played"),
)
MIN_MATCHES_FOR_AVERAGE = 3


def period_start(period: str, now: datetime, season_start: str = "") -> int | None:
    """When a period began, as a Unix time (local midnight). None means all time."""
    if period == "week":
        monday = now.date() - timedelta(days=now.weekday())
        return int(datetime.combine(monday, time.min).timestamp())
    if period == "season":
        try:
            return int(datetime.combine(date.fromisoformat(season_start), time.min).timestamp())
        except ValueError:
            return None
    return None


def average(row: dict) -> float:
    return row["chests"] / row["matches"] if row["matches"] else 0.0


def value(row: dict, category: str) -> float:
    return average(row) if category == "average" else float(row.get(category, 0))


def shown(row: dict, category: str) -> str:
    number = value(row, category)
    return f"{number:.1f}" if category == "average" else f"{int(number):,}"


def rank(rows: list[dict], category: str) -> list[dict]:
    """The players who have something in this category, best first (ties by name)."""
    chosen = []
    for row in rows:
        if category == "average" and row["matches"] < MIN_MATCHES_FOR_AVERAGE:
            continue
        if value(row, category) > 0:
            chosen.append(row)
    return sorted(chosen, key=lambda r: (-value(r, category), r["name"].lower()))


def label(options: tuple, key: str) -> str:
    return next((text for k, text in options if k == key), key)


def format_board(rows: list[dict], period: str, category: str, limit: int = 10, escape=lambda t: t) -> str:
    """The text for the /leaderboard command."""
    ranked = rank(rows, category)[:limit]
    title = f"\U0001F3C6 **{label(CATEGORIES, category)}** · {label(PERIODS, period).lower()}"
    if not ranked:
        note = f" (needs {MIN_MATCHES_FOR_AVERAGE} matches)" if category == "average" else ""
        return f"{title}\nNothing counted yet{note}."
    lines = [f"**{n}.** {escape(r['name'])}: {shown(r, category)}" for n, r in enumerate(ranked, 1)]
    return title + "\n" + "\n".join(lines)
