import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import backup
import treasures
from marks import TreasureMarks
from test_content import BUNDLED
from content import parse
from test_ui import *  # noqa: F401,F403  (window fixture)


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
