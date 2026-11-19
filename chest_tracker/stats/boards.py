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
    ("fn_wins", "Fortnite wins"),
    ("fn_kills", "Fortnite eliminations"),
    ("fn_kd", "Fortnite K/D"),
    ("fn_winrate", "Fortnite win rate"),
)
MIN_MATCHES_FOR_AVERAGE = 3
MIN_FORTNITE_MATCHES = 10  # a K/D or win rate from a handful of games isn't worth ranking
FORTNITE_WINDOWS = {"season": "season", "all": "lifetime"}  # Fortnite's own stats have no "this week"


def is_fortnite(category: str) -> bool:
    return category.startswith("fn_")


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
    if category == "average":
        return average(row)
    if is_fortnite(category):
        return float(row.get(category[3:], 0))
    return float(row.get(category, 0))


def shown(row: dict, category: str) -> str:
    number = value(row, category)
    if category == "fn_kd":
        return f"{number:.2f}"
    if category == "fn_winrate":
        return f"{number:.1f}%"
    return f"{number:.1f}" if category == "average" else f"{int(number):,}"


def rank(rows: list[dict], category: str) -> list[dict]:
    """The players who have something in this category, best first (ties by name)."""
    chosen = []
    for row in rows:
        if category == "average" and row["matches"] < MIN_MATCHES_FOR_AVERAGE:
            continue
        if category in ("fn_kd", "fn_winrate") and row["matches"] < MIN_FORTNITE_MATCHES:
            continue
        if value(row, category) > 0:
            chosen.append(row)
    return sorted(chosen, key=lambda r: (-value(r, category), r["name"].lower()))


def label(options: tuple, key: str) -> str:
    return next((text for k, text in options if k == key), key)


def rows_for(category: str, period: str, match_rows: list[dict], fortnite: dict[str, list[dict]]) -> list[dict]:
    """The players to rank: match stats for a period, or the Fortnite stats that fit it (none for "this week")."""
    if is_fortnite(category):
        return fortnite.get(FORTNITE_WINDOWS.get(period, ""), [])
    return match_rows


def format_board(rows: list[dict], period: str, category: str, limit: int = 10, escape=lambda t: t) -> str:
    """The text for the /leaderboard command."""
    ranked = rank(rows, category)[:limit]
    title = f"\U0001F3C6 **{label(CATEGORIES, category)}** · {label(PERIODS, period).lower()}"
    if not ranked:
        note = f" (needs {MIN_MATCHES_FOR_AVERAGE} matches)" if category == "average" else ""
        if is_fortnite(category) and period == "week":
            note = " (Fortnite stats cover this season and all time)"
        return f"{title}\nNothing counted yet{note}."
    lines = [f"**{n}.** {escape(r['name'])}: {shown(r, category)}" for n, r in enumerate(ranked, 1)]
    return title + "\n" + "\n".join(lines)
