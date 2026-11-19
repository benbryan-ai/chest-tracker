"""Makes the README screenshots from sample data. Run: python tools/make_screenshots.py OUTPUT_FOLDER

Nothing here touches your real data: the window runs on a temporary folder with made-up matches.
"""

import os
import shutil
import sys
import tempfile
from datetime import date, datetime, timedelta
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_SCALE_FACTOR", "2")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

if sys.platform != "win32":  # the Windows-only calls aren't needed to draw the window
    sys.path.insert(0, str(ROOT / "tests"))
    import conftest  # noqa: F401

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from chest_tracker.gui import ui
WIDTH, HEIGHT = 1200, 760


def sample_matches(content) -> list[dict]:
    now = datetime.now().replace(microsecond=0)
    counts = [14, 9, 17, 11, 6, 15, 12, 19, 8, 13, 16, 10, 21, 7, 14, 12, 18, 9, 15, 11]
    prizes = list(content.weeks[1].prizes[:3])
    history = []
    for index, chests in enumerate(counts):
        end = now - timedelta(days=index // 3, hours=(index % 3) * 3 + 1)
        start = end - timedelta(minutes=18 + index % 6)
        opened = chests - index % 3
        record = {
            "start": start.isoformat(), "end": end.isoformat(), "chests": chests, "source": "replay",
            "opened": opened, "broken": chests - opened,
            "kinds": {"Chest": chests - 3, "Buried chest": 2, "Rare chest": 1},
            "chest_times": [int((start + timedelta(minutes=2 + k)).timestamp()) for k in range(chests)],
        }
        record["chest_spots"] = sample_spots(index, chests)
        if index in (1, 4, 9) and prizes:
            prize = prizes[index % len(prizes)]
            record["treasures"] = [{
                "name": prize.name, "kind": prize.kind, "prize_id": (prize.prize_ids or [None])[0], "golden": True,
                "at": int((start + timedelta(minutes=9)).timestamp()),
            }]
        history.append(record)
    return list(reversed(history))


def sample_spots(seed: int, count: int) -> list[list[int]]:
    """Made-up landing areas, so the sample map has some hot spots."""
    import random
    rng = random.Random(seed)
    towns = [(-150000, -100000), (120000, -60000), (40000, 140000), (-60000, 90000)]
    spots = []
    for _ in range(count):
        cx, cy = rng.choice(towns)
        spots.append([int(rng.gauss(cx, 18000)), int(rng.gauss(cy, 18000))])
    return spots


def content_week_prize(win) -> str:
    """A prize from week 2 that the sample replays didn't find, shown as ticked by hand."""
    return win.content_store.content.weeks[1].prizes[4].id


def main(out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    app = QApplication.instance() or QApplication([])
    folder = Path(tempfile.mkdtemp())
    (folder / "templates").mkdir()
    shutil.copy(ROOT / "assets" / "prompt_word.png", folder / "templates" / "search.png")
    import json

    (folder / "settings.json").write_text(json.dumps({
        "player_name": "Alex", "webhook_url": "https://discord.com/api/webhooks/1/x", "remove_key": "F10",
        "replay_folder": "C:/Users/Alex/AppData/Local/FortniteGame/Saved/Demos",
        "daily_goal": 50, "match_goal": 15,
    }))
    win = ui.MainWindow(folder, QIcon(str(ROOT / "assets" / "icon.png")))
    win.content_store.get = lambda *a, **k: (_ for _ in ()).throw(OSError("offline"))
    win.stats.today, win.stats.session = 37, 12
    win.stats.adjust_total(1284)
    win.matches.history = sample_matches(win.content_store.content)
    for page in (win.tracker, win.setup, win.group, win.report, win.treasures_page, win.settings_page):
        for name in ("refresh",):
            if hasattr(page, name):
                getattr(page, name)()
    win.tracker.show_stats(win.stats)
    win.tracker.show_matches(win.matches)
    win.tracker.log("Chest opened", ui.GOLD)
    win.tracker.log("Search cancelled, not counted")
    win.tracker.log("Chest opened", ui.GOLD)
    win.set_state("watching")
    win._refresh_total()
    win.treasure_marks.set(content_week_prize(win), True)
    week = [
        {"name": "Alex", "chests": 142, "matches": 9, "best": 24, "opened": 131, "broken": 11, "treasures": 3},
        {"name": "Sam", "chests": 128, "matches": 8, "best": 21, "opened": 122, "broken": 6, "treasures": 2},
        {"name": "Jordan", "chests": 97, "matches": 7, "best": 19, "opened": 90, "broken": 7, "treasures": 1},
        {"name": "Riley", "chests": 64, "matches": 5, "best": 16, "opened": 63, "broken": 1, "treasures": 0},
    ]
    win.group.show_board({"week": week, "season": week, "all": week}, 3887)
    win.group.category_box.setCurrentIndex(win.group.category_box.findData("chests"))
    win.resize(WIDTH, HEIGHT)
    win.show()
    shots = (("tracker", 0), ("setup", 1), ("leaderboards", 2), ("report", 4), ("treasures", 6), ("settings", 5), ("map", 7))
    for name, index in shots:
        win.go_to(index)
        win._page_shown(index)
        if name == "treasures":
            win.treasures_page.week_box.setCurrentIndex(1)  # week 2, which has prizes and sample finds
            win.treasures_page.refresh()
        for _ in range(5):
            app.processEvents()
        win.setFocus()
        win.grab().save(str(out / f"{name}.png"))
    from chest_tracker.stats import sharecard
    from chest_tracker.gui import sharecard_render
    card = sharecard.collect(win.matches.history, "last7", date.today(), "2026-11-01", "Alex", 30, win.stats.today)
    sharecard_render.render(card).save(str(out / "card.png"))
    win._shut_down()
    shutil.rmtree(folder, ignore_errors=True)


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "docs" / "images")
