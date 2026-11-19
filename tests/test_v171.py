import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from chest_tracker.data import backup
from chest_tracker.data import treasures
from chest_tracker.data.marks import TreasureMarks
from test_content import BUNDLED
from chest_tracker.data.content import parse
from test_ui import app, window  # noqa: F401  (the fixtures)


def test_marks_persist_and_toggle(tmp_path):
    m = TreasureMarks(tmp_path / "m.json")
    m.set("w2-car", True)
    assert TreasureMarks(tmp_path / "m.json").is_marked("w2-car")
    m.set("w2-car", False)
    assert not TreasureMarks(tmp_path / "m.json").is_marked("w2-car")


def test_damaged_marks_file_is_ignored(tmp_path):
    (tmp_path / "m.json").write_text("{nope")
    assert TreasureMarks(tmp_path / "m.json").found == {}


def test_total_counts_marked_prizes_without_double_counting():
    c = parse(BUNDLED)
    find = treasures.Find("x", "outfit", "DelilahPrize:dpid_item14", None, None)
    assert treasures.total_found(c, [find], set()) == 1
    assert treasures.total_found(c, [find], {"w2-outfit"}) == 1  # already found by replay
    assert treasures.total_found(c, [find], {"w2-car"}) == 2
    assert treasures.total_found(c, [], {"w2-car"}) == 1


def test_past_weeks_are_listed_newest_first():
    c = parse(BUNDLED)
    weeks = treasures.started_weeks(c, datetime(2026, 11, 20, tzinfo=timezone.utc))
    nums = [w.number for w in weeks]
    assert nums == sorted(nums, reverse=True) and len(nums) >= 2


def test_backup_includes_marks(tmp_path):
    assert "treasure_marks.json" in backup.FILES


def test_ticking_a_prize_on_the_page(window):
    page = window.treasures_page
    page.refresh()
    assert page.week_box.count() >= 1
    box = page.week.itemAt(0).widget()
    box.setChecked(True)
    assert len(window.treasure_marks.found) == 1


def test_an_ampersand_in_a_prize_name_is_shown_as_is(window):
    page = window.treasures_page
    page.refresh()
    kinds = [page.week.itemAt(i).widget().text() for i in range(page.week.count())]
    assert not any("_" in t for t in kinds)
    assert any("Vehicle && decal" in t for t in kinds) or not any("decal" in t for t in kinds)


def share(window):
    window.settings.set(webhook_url="https://discord.com/api/webhooks/1/x", player_name="Sam")


def test_an_import_is_sent_to_the_group(window):
    from chest_tracker.data import importer
    share(window)
    window.sender.wake.clear()
    window.apply_import(importer.ImportOffer("ChestCounter", "Sam", 60, [], 0))
    assert window.sender.pending == 60


def test_the_group_gap_is_the_difference_to_the_leaderboard(window):
    share(window)
    window.set_total(1000)
    window.sender.pending = 0  # it was delivered
    window.leaderboard_seen = ([("Sam", 400), ("Alex", 300)], 700)
    assert window.group_gap() == 600
    window.group.update_sync()
    assert not window.group.sync_row.isHidden()
    assert window.sync_group_total() == 600
    assert window.sender.pending == 600


def test_no_gap_is_offered_while_a_post_is_still_on_its_way(window):
    share(window)
    window.set_total(1000)
    window.leaderboard_seen = ([("Sam", 400)], 400)
    assert window.group_gap() is None  # the 1,000 hasn't been delivered yet, so syncing would count it twice


def test_no_gap_when_you_are_not_on_the_board(window):
    share(window)
    window.leaderboard_seen = ([("Alex", 300)], 300)
    assert window.group_gap() is None
    window.leaderboard_seen = None
    assert window.group_gap() is None
