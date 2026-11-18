import sys
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import sharecard
import sharecard_render
import watcher
from test_ui import app, window  # noqa: F401  (the fixtures)

TODAY = date(2026, 11, 18)  # a Wednesday


def match(day, chests, broken=0, treasures=0):
    return {"start": f"2026-11-{day:02d}T20:00:00", "end": f"2026-11-{day:02d}T20:20:00", "chests": chests,
            "opened": chests - broken, "broken": broken, "treasures": [{"name": "t"}] * treasures}


HISTORY = [match(2, 30), match(16, 10, 1), match(16, 14, 0, 1), match(18, 20, 2, 2), match(10, 50)]


def test_the_week_covers_monday_to_sunday():
    card = sharecard.collect(HISTORY, "week", TODAY, name="Sam")
    assert (card.chests, card.matches, card.best) == (44, 3, 20)
    assert card.broken == 3 and card.opened == 41 and card.treasures == 3
    assert round(card.average, 1) == 14.7
    assert [b[0] for b in card.bars] == ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"]
    assert [b[1] for b in card.bars] == [24, 0, 20, 0, 0, 0, 0]
    assert card.range_text == "Nov 16 - Nov 22, 2026"


def test_last_seven_days_and_month_and_season():
    assert sharecard.collect(HISTORY, "last7", TODAY).chests == 44  # Nov 12 to 18; the 10th is outside
    month = sharecard.collect(HISTORY, "month", TODAY)
    assert month.chests == 124 and len(month.bars) == 18
    season = sharecard.collect(HISTORY, "season", TODAY, "2026-11-01")
    assert season.chests == 124 and season.unit == "week" and season.bars[-1][1] == 44


def test_an_empty_period_is_fine(app):
    card = sharecard.collect([], "week", TODAY)
    assert card.chests == 0 and card.average == 0.0 and card.best == 0
    assert sharecard_render.to_png(card).startswith(b"\x89PNG")


def test_the_streak_follows_the_goal():
    days = [match(14, 60), match(15, 60), match(17, 60)]
    assert sharecard.collect(days, "week", TODAY, daily_goal=50, today_count=70).streak == 2
    assert sharecard.collect(days, "week", date(2026, 11, 16), daily_goal=50, today_count=60).streak == 3
    assert sharecard.collect(days, "week", TODAY, daily_goal=0).streak == 0


def test_the_picture_has_the_expected_size(app):
    png = sharecard_render.to_png(sharecard.collect(HISTORY, "week", TODAY, name="Sam"))
    from PySide6.QtGui import QImage
    image = QImage.fromData(png)
    assert (image.width(), image.height()) == (1200, 675)


def test_posting_an_image_sends_a_file_and_reports_the_result():
    ok = MagicMock(ok=True, status_code=200)
    with patch("watcher.requests.post", return_value=ok) as post:
        done, message = watcher.post_image("https://discord.com/api/webhooks/1/x", "Sam", b"png")
    assert done and "files" in post.call_args.kwargs and post.call_args.kwargs["allow_redirects"] is False
    assert not watcher.post_image("https://example.com/nope", "Sam", b"png")[0]
    bad = MagicMock(ok=False, status_code=404)
    with patch("watcher.requests.post", return_value=bad):
        assert not watcher.post_image("https://discord.com/api/webhooks/1/x", "Sam", b"png")[0]


def test_the_dialog_makes_a_picture_and_only_posts_with_a_webhook(window):
    from ui import ShareCardDialog
    dialog = ShareCardDialog(window)
    assert dialog.png.startswith(b"\x89PNG") and not dialog.post_button.isEnabled()
    window.settings.set(webhook_url="https://discord.com/api/webhooks/1/x")
    dialog.make()
    assert dialog.post_button.isEnabled()
    dialog.period.setCurrentIndex(3)
    dialog.make()
    assert dialog.png.startswith(b"\x89PNG")
    dialog.copy()
    assert "Copied" in dialog.status.text()
    window.settings.set(match_webhook_url="https://discord.com/api/webhooks/2/y")
    assert dialog.webhook().endswith("/2/y")
