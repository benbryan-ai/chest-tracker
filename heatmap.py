"""The chest map: where you searched chests, taken from the replay (positions are in centimetres)."""

from datetime import datetime

import boards

PERIODS = (("all", "All matches"), ("season", "This season"), ("week", "This week"), ("last", "Last match"))
MIN_SPAN = 150_000  # never zoom in closer than 1.5 km across, so a few chests don't fill the whole map
STEP = 50_000  # the map's size is rounded up to this, so the grid lines land on round numbers


def spots(history: list[dict], period: str, now: datetime, season_start: str = "") -> list[tuple[int, int]]:
    """The positions of every chest searched in the period's matches that were read from a replay."""
    chosen = history
    if period == "last":
        chosen = [m for m in history if m.get("chest_spots")][-1:]
    elif period in ("week", "season"):
        since = boards.period_start(period, now, season_start)
        if since is not None:
            chosen = [m for m in history if _started(m) >= since]
    found = []
    for match in chosen:
        for spot in match.get("chest_spots") or []:
            if spot:
                found.append((int(spot[0]), int(spot[1])))
    return found


def _started(match: dict) -> float:
    try:
        return datetime.fromisoformat(match["start"]).timestamp()
    except (KeyError, ValueError):
        return 0.0


def orient(point: tuple[int, int], rotation: int, mirror: bool) -> tuple[int, int]:
    """Turn the map in quarter turns and optionally mirror it. Replays don't say which way the island map faces,
    so you can set it to match the one in the game."""
    x, y = point
    if mirror:
        x = -x
    for _ in range(rotation % 4):
        x, y = -y, x
    return x, y


def frame(points: list[tuple[int, int]]) -> tuple[int, int, int]:
    """A square that holds every point: (left, top, size), with room around the edge and round numbers."""
    if not points:
        return -MIN_SPAN // 2, -MIN_SPAN // 2, MIN_SPAN
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    span = max(max(xs) - min(xs), max(ys) - min(ys)) * 1.2
    size = max(MIN_SPAN, int(-(-span // STEP) * STEP))
    centre_x, centre_y = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
    left = int(round((centre_x - size / 2) / (STEP / 2)) * (STEP / 2))
    top = int(round((centre_y - size / 2) / (STEP / 2)) * (STEP / 2))
    return left, top, size


def grid_step(size: int) -> int:
    """Grid spacing for a map this big: 500 m up to 2 km across, 1 km after that."""
    return 50_000 if size <= 200_000 else 100_000


def km(centimetres: int) -> str:
    value = centimetres / 100_000
    return f"{value:g} km"
