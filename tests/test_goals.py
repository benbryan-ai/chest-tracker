import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import goals
from test_ui import app, window  # noqa: F401  (the fixtures)


def test_goal_values_are_cleaned():
    assert [goals.clean_goal(v) for v in (50, "12", 0, -3, "x", None, 99999)] == [50, 12, 0, 0, 0, 0, 0]


def test_fraction_and_text():
    assert goals.fraction(25, 50) == 0.5 and goals.fraction(80, 50) == 1.0 and goals.fraction(5, 0) == 0.0
    assert goals.progress_text(37, 50, "today") == "37 of 50 today"
    assert goals.progress_text(52, 50, "today") == "Goal reached: 52 today"
    assert goals.progress_text(5, 0, "today") == ""


def test_crossing_happens_once():
    assert goals.crossed(49, 50, 50) and not goals.crossed(50, 51, 50) and not goals.crossed(0, 5, 0)


def history(*days):
    return [{"start": f"2026-11-{d:02d}T20:00:00", "chests": n} for d, n in days]


def test_streak_counts_consecutive_days_that_met_the_goal():
    days = goals.per_day(history((14, 60), (15, 55), (16, 20), (17, 70), (18, 10)))
    today = date(2026, 11, 18)
    assert goals.streak(days, 50, today, 10) == 1  # the 17th met it; today isn't over and the 16th broke the run
    assert goals.streak(days, 50, today, 60) == 2  # today now counts too
    assert goals.streak(days, 0, today, 99) == 0


def test_a_missed_day_ends_the_streak():
    days = goals.per_day(history((10, 60), (12, 60)))
    assert goals.streak(days, 50, date(2026, 11, 12), 60) == 1


def test_no_goal_shows_nothing(window):
    window.record_chest(1, "detected")
    assert window.tracker.day_bar.isHidden() and window.tracker.match_bar.isHidden()
    assert window.overlay.day_goal is None


def test_goals_show_progress_and_celebrate_once(window):
    window.settings.set(daily_goal=3, match_goal=2, goal_sound=False)
    window.record_chest(1, "detected")
    window._show_stats()
    assert not window.tracker.day_bar.isHidden()
    assert window.tracker.day_goal.text() == "1 of 3 today"
    assert window.tracker.match_goal.text() == "1 of 2 chests"
    assert window.overlay.day_goal == 1 / 3 and window.overlay.match_goal == 0.5
    window.record_chest(1, "detected")
    window.record_chest(1, "detected")
    window.record_chest(1, "detected")
    log = [window.tracker.activity.item(i).text() for i in range(window.tracker.activity.count())]
    assert sum("Match goal reached" in t for t in log) == 1
    assert sum("Daily goal reached" in t for t in log) == 1


def test_the_overlay_grows_for_the_goal_bars(window):
    window.overlay.set_goals(None, None)
    base = window.overlay.height()
    window.overlay.set_goals(0.5, None)
    assert window.overlay.height() > base
    window.overlay.set_goals(None, None)
    assert window.overlay.height() == base


def test_the_settings_page_saves_goals(window):
    page = window.settings_page
    page.day_goal_box.setValue(40)
    page.match_goal_box.setValue(12)
    assert window.settings["daily_goal"] == 40 and window.settings["match_goal"] == 12
    assert window.tracker.day_goal.text().endswith("of 40 today")
