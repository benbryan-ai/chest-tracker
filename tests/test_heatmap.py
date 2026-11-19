from datetime import datetime

import heatmap
from test_ui import app, window  # noqa: F401


def test_spots_periods():
    history = [
        {"start": "2026-10-01T10:00:00", "chest_spots": [[1, 2], None, [3, 4]]},
        {"start": "2026-11-18T10:00:00", "chest_spots": [[5, 6]]},
        {"start": "2026-11-19T10:00:00"},
    ]
    now = datetime(2026, 11, 19, 12)
    assert len(heatmap.spots(history, "all", now)) == 3
    assert heatmap.spots(history, "last", now) == [(5, 6)]


def test_orient_and_frame():
    assert heatmap.orient((10, 20), 0, False) == (10, 20)
    assert heatmap.orient((10, 20), 1, False) == (-20, 10)
    assert heatmap.orient((10, 20), 0, True) == (-10, 20)
    assert heatmap.orient((10, 20), 4, False) == (10, 20)
    left, top, size = heatmap.frame([(0, 0), (400000, 100000)])
    assert size >= 480000 and size % 50000 == 0
    assert left <= 0 and left + size >= 400000
    assert heatmap.frame([])[2] == heatmap.MIN_SPAN
    assert heatmap.km(50000) == "0.5 km"


def test_map_page_renders(window):
    window.matches.history.append({"start": "2026-11-18T10:00:00", "end": "2026-11-18T10:20:00",
                                   "chests": 2, "chest_spots": [[100000, 50000], [120000, 70000]]})
    page = window.map_page
    page.refresh()
    assert "2 chests" in page.count.text()
    page.rotate()
    assert window.settings["map_rotation"] == 1
    page.grab()
