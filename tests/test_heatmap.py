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


def test_placement_helpers():
    scale, dx, dy = heatmap.fit_to_picture([(0, 0), (200000, 100000)], 0.7)
    u, v = heatmap.place((100000, 50000), scale, dx, dy)
    assert abs(u - 0.5) < 1e-9 and abs(v - 0.35) < 1e-9  # the dots' centre sits in the middle of the picture
    new_scale, ndx, ndy = heatmap.zoom_about(scale, dx, dy, (0.3, 0.2), 2.0)
    assert new_scale == scale * 2
    before = heatmap.place((50000, 20000), scale, dx, dy)
    after = heatmap.place((50000, 20000), new_scale, ndx, ndy)
    assert (after[0] - 0.3) == (before[0] - 0.3) * 2 or abs((after[0] - 0.3) - (before[0] - 0.3) * 2) < 1e-9
    assert heatmap.zoom_about(heatmap.MAX_SCALE, 0, 0, (0, 0), 5)[0] == heatmap.MAX_SCALE


def test_map_picture_is_copied_and_remembered(window, tmp_path):
    from pathlib import Path

    from PySide6.QtGui import QImage

    image = QImage(300, 200, QImage.Format.Format_RGB32)
    image.fill(0x336699)
    source = tmp_path / "somewhere" / "island.png"
    source.parent.mkdir()
    assert image.save(str(source))
    window.matches.history.append({"start": "2026-11-18T10:00:00", "end": "2026-11-18T10:20:00",
                                   "chests": 2, "chest_spots": [[0, 0], [100000, 50000]]})
    page = window.map_page
    page.refresh()
    assert page.set_picture_file(source)
    saved = Path(window.settings["map_image"])
    assert saved.is_file() and saved.parent == window.settings.path.parent
    assert page.view.picture is not None
    assert page.reset.isEnabled()
    page.view.set_placement(0.3, 0.4, 0.2)
    page.view.placed.emit(0.3, 0.4, 0.2)
    assert window.settings["map_scale"] == 0.3
    page.grab()


def test_reference_picture_gets_the_known_placement():
    assert heatmap.fit_to_picture([(1, 2)], 992 / 1470) == heatmap.REFERENCE_PLACEMENT
    assert heatmap.fit_to_picture([(1, 2)], 0.5) != heatmap.REFERENCE_PLACEMENT
    # the ring of searches at the north-east of the island lands in the picture's top right
    u, v = heatmap.place((90000, -60000), *heatmap.REFERENCE_PLACEMENT)
    assert 0.65 < u < 0.75 and 0.08 < v < 0.12
