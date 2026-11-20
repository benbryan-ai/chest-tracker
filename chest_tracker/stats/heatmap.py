"""The chest map: where you searched chests, taken from the replay (positions are in centimetres)."""

from datetime import datetime

from chest_tracker.stats import boards
PERIODS = (("all", "All matches"), ("season", "This season"), ("week", "This week"), ("last", "Last match"),
           ("match", "A single match..."))
MIN_SPAN = 150_000  # never zoom in closer than 1.5 km across, so a few chests don't fill the whole map
STEP = 50_000  # the map's size is rounded up to this, so the grid lines land on round numbers


def spots(history: list[dict], period: str, now: datetime, season_start: str = "", match: str = "") -> list[tuple[int, int]]:
    """The positions of every chest searched in the period's matches that were read from a replay."""
    chosen = history
    if period == "match":
        chosen = [m for m in history if m.get("start") == match]
    elif period == "last":
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


# --- Placing the dots on a map picture --------------------------------------------------------------------------
# A picture is addressed in fractions of its own width. A point lands at ((dx + x_km * scale), (dy + y_km * scale)),
# where dx/dy say where the world origin sits and scale is how much of the picture's width a kilometre covers.

DEFAULT_SCALE = 0.2
MIN_SCALE, MAX_SCALE = 0.02, 2.0
WHEEL_STEP = 1.02  # one scroll notch changes the size by 2%
FINE_WHEEL_STEP = 1.005  # holding Shift
BUTTON_STEP = 1.01  # the + and - buttons


def width_km(scale: float) -> float:
    """How many kilometres the picture's full width shows."""
    return 1 / scale


def scale_for_width(km: float) -> float:
    return min(MAX_SCALE, max(MIN_SCALE, 1 / km)) if km > 0 else DEFAULT_SCALE


def wheel_factor(delta: int, fine: bool = False) -> float:
    """The size change for a scroll of `delta` (120 per notch; positive makes the dots larger)."""
    return (FINE_WHEEL_STEP if fine else WHEEL_STEP) ** (delta / 120)


def place(point: tuple[int, int], scale: float, dx: float, dy: float) -> tuple[float, float]:
    return dx + point[0] / 100_000 * scale, dy + point[1] / 100_000 * scale


# The placement that lines the replay positions up with the full-island picture most people use (the whole island
# in a 1470 x 992 picture). It was checked against real replays: the searches landed on the right towns and biomes.
REFERENCE_ASPECT = 992 / 1470
REFERENCE_PLACEMENT = (500 / 1470, 552 / 1470, 440 / 1470)


def fit_to_picture(points: list[tuple[int, int]], aspect: float) -> tuple[float, float, float]:
    """A starting placement. A picture shaped like the reference island picture gets the known alignment; any other
    picture gets the dots' centre in the middle, covering about 40% of its width, to be dragged into place.
    aspect is height / width of the picture. Returns (scale, dx, dy)."""
    if abs(aspect - REFERENCE_ASPECT) < 0.02:
        return REFERENCE_PLACEMENT
    if not points:
        return DEFAULT_SCALE, 0.5, 0.5 * aspect
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    span_km = max(max(xs) - min(xs), max(ys) - min(ys), MIN_SPAN) / 100_000
    scale = min(MAX_SCALE, max(MIN_SCALE, 0.4 / span_km))
    centre_x = (min(xs) + max(xs)) / 2 / 100_000
    centre_y = (min(ys) + max(ys)) / 2 / 100_000
    return scale, 0.5 - centre_x * scale, 0.5 * aspect - centre_y * scale


def zoom_about(scale: float, dx: float, dy: float, at: tuple[float, float], factor: float) -> tuple[float, float, float]:
    """Change the scale while keeping the spot under `at` (picture fractions) where it is."""
    new_scale = min(MAX_SCALE, max(MIN_SCALE, scale * factor))
    ratio = new_scale / scale
    return new_scale, at[0] - (at[0] - dx) * ratio, at[1] - (at[1] - dy) * ratio


def choices(history: list[dict], limit: int = 40) -> list[tuple[str, str]]:
    """The recent matches that have positions, newest first, as (start, description) for a match picker."""
    found = []
    for record in reversed(history):
        if record.get("chest_spots") and record.get("start"):
            try:
                when = datetime.fromisoformat(record["start"])
            except ValueError:
                continue
            count = len([s for s in record["chest_spots"] if s])
            found.append((record["start"], f"{when:%b} {when.day}, {when:%I:%M %p}".replace(" 0", " ") + f" - {count} chests"))
            if len(found) >= limit:
                break
    return found


# Town names with where they sit on the reference island picture (pixels in the 1470 x 992 picture). The map's
# positions are the same in every season's picture only while the island stays the same; they're approximate, so
# a result reads "near <town>".
TOWN_PIXELS = (
    ("Friendship Villa", 480, 175), ("Buggy's Beachhead", 700, 270), ("Lil' Uzi's Stronghold", 930, 240),
    ("The Chest", 400, 305), ("Lantern Landing", 575, 440), ("Arlong Park", 370, 505),
    ("Cursed Cavern", 815, 520), ("The S.S. Rocky", 1000, 570), ("Loguetown", 655, 705),
    ("Windmill Village", 440, 765), ("Busy Bay", 985, 790), ("Plunder Port", 785, 870),
)
NEAR_TOWN = 30_000  # further than 300 m from every town counts as "elsewhere"


def _pixel_to_world(px: float, py: float) -> tuple[float, float]:
    scale, dx, dy = REFERENCE_PLACEMENT
    return ((px / 1470 - dx) / scale * 100_000, (py / 1470 - dy) / scale * 100_000)


def top_areas(points: list[tuple[int, int]], limit: int = 5) -> list[tuple[str, int]]:
    """Where the searches were, as (name, count) with the busiest first. Uses the island's known coordinates,
    so give it the points as the replay recorded them, before any turning or mirroring."""
    towns = [(name, *_pixel_to_world(px, py)) for name, px, py in TOWN_PIXELS]
    counts: dict[str, int] = {}
    for x, y in points:
        name, distance = min(((t[0], ((x - t[1]) ** 2 + (y - t[2]) ** 2) ** 0.5) for t in towns), key=lambda pair: pair[1])
        key = f"Near {name}" if distance <= NEAR_TOWN else "Elsewhere"
        counts[key] = counts.get(key, 0) + 1
    return sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:limit]
