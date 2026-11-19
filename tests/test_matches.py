import csv
import sys
from datetime import datetime, timedelta
from pathlib import Path

import cv2
import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from chest_tracker.data.matches import MatchLog
from chest_tracker.counting.recap import RecapDetector

NOW = datetime(2026, 11, 14, 15, 0, 0)


def test_a_match_counts_up_and_down_and_never_below_zero(tmp_path):
    log = MatchLog(tmp_path / "m.json")
    log.add(1)
    log.add(1)
    log.add(-1)
    assert log.current == 1
    log.add(-1)
    log.add(-1)
    assert log.current == 0


def test_finishing_saves_the_match_and_starts_the_next(tmp_path):
    log = MatchLog(tmp_path / "m.json")
    for _ in range(7):
        log.add(1)
    record = log.finish()
    assert record["chests"] == 7 and log.current == 0
    assert [m["chests"] for m in log.history] == [7]


def test_a_match_with_no_chests_is_not_saved(tmp_path):
    log = MatchLog(tmp_path / "m.json")
    assert log.finish() is None
    log.add(1)
    log.add(-1)
    assert log.finish() is None
    assert log.history == [] and log.stats() is None


def test_average_median_and_best_ignore_empty_matches(tmp_path):
    log = MatchLog(tmp_path / "m.json")
    for chests in (4, 0, 10, 7, 0, 1):
        for _ in range(chests):
            log.add(1)
        log.finish()
    stats = log.stats()
    assert stats.matches == 4
    assert stats.average == pytest.approx(5.5)
    assert stats.median == 5.5
    assert stats.best == 10


def test_a_single_chest_match_counts(tmp_path):
    log = MatchLog(tmp_path / "m.json")
    log.add(1)
    log.finish()
    assert log.stats().matches == 1


def test_history_and_the_open_match_survive_a_restart(tmp_path):
    log = MatchLog(tmp_path / "m.json")
    for _ in range(3):
        log.add(1)
    log.finish()
    log.add(1, now=NOW)
    again = MatchLog(tmp_path / "m.json", now=NOW + timedelta(minutes=5))
    assert again.current == 1
    assert [m["chests"] for m in again.history] == [3]


def test_a_match_left_open_for_hours_is_closed_on_start(tmp_path):
    log = MatchLog(tmp_path / "m.json")
    log.add(1, now=NOW)
    log.add(1, now=NOW)
    later = MatchLog(tmp_path / "m.json", now=NOW + timedelta(hours=3))
    assert later.current == 0
    assert [m["chests"] for m in later.history] == [2]


def test_a_damaged_file_starts_fresh(tmp_path):
    path = tmp_path / "m.json"
    path.write_text("{ not json", encoding="utf-8")
    assert MatchLog(path).current == 0
    path.write_text('{"history": [{"start": 1}], "current": "x"}', encoding="utf-8")
    log = MatchLog(path)
    assert log.history == [] and log.current == 0


def test_export_writes_a_csv_that_spreadsheets_open(tmp_path):
    log = MatchLog(tmp_path / "m.json")
    for chests in (3, 5):
        for _ in range(chests):
            log.add(1)
        log.finish()
    out = tmp_path / "out.csv"
    assert log.export_csv(out) == 2
    rows = list(csv.reader(out.open(encoding="utf-8-sig")))
    assert rows[0] == ["match", "start", "end", "chests", "opened", "broken", "counted from"]
    assert [r[3] for r in rows[1:]] == ["3", "5"]


# --- the end-of-match screen ---

def fake_recap_screen(width=1920, height=1200, with_buttons=True, offset=0):
    detector = RecapDetector.load_bundled()
    screen = np.random.default_rng(3).integers(30, 120, (height, width), dtype=np.uint8)
    screen = cv2.GaussianBlur(screen, (0, 0), 6)
    if with_buttons:
        s = height / 1200
        for template, y in ((detector.return_to_lobby, 486 + offset), (detector.play_again, 570 + offset)):
            size = (round(template.shape[1] * s), round(template.shape[0] * s))
            piece = cv2.resize(template, size, interpolation=cv2.INTER_AREA)
            x = round(1452 * s)
            screen[round(y * s) : round(y * s) + piece.shape[0], x : x + piece.shape[1]] = piece
    return detector, screen


@pytest.mark.parametrize("height", [1200, 1080, 900, 1440])
def test_the_end_screen_is_recognised_at_other_resolutions(height):
    detector, screen = fake_recap_screen(int(1920 * height / 1200), height)
    assert detector.is_recap(screen)


def test_the_end_screen_is_recognised_wherever_the_buttons_sit_vertically():
    for offset in (-40, 0, 24):
        detector, screen = fake_recap_screen(offset=offset)
        assert detector.is_recap(screen)


def test_a_normal_game_frame_is_not_the_end_screen():
    detector, screen = fake_recap_screen(with_buttons=False)
    assert not detector.is_recap(screen)
    assert not detector.is_recap(np.zeros((1200, 1920), np.uint8))


def test_one_button_alone_is_not_the_end_screen():
    detector, screen = fake_recap_screen()
    screen[480:520, 1400:1720] = 70  # wipe out RETURN TO LOBBY
    assert not detector.is_recap(screen)


def test_a_replay_count_replaces_the_screen_count(tmp_path):
    log = MatchLog(tmp_path / "m.json")
    for _ in range(3):
        log.add(1)
    record = log.finish()
    assert log.apply_replay(record, 5, 3, 2) == 2
    assert log.history[-1]["chests"] == 5
    assert (log.history[-1]["opened"], log.history[-1]["broken"], log.history[-1]["source"]) == (3, 2, "replay")
    again = MatchLog(tmp_path / "m.json")  # and it survives a restart
    assert again.history[-1]["broken"] == 2


def test_a_replay_with_no_chests_removes_the_match(tmp_path):
    log = MatchLog(tmp_path / "m.json")
    log.add(1)
    record = log.finish()
    assert log.apply_replay(record, 0, 0, 0) == -1
    assert log.history == []


def test_a_replay_count_for_an_unknown_match_changes_nothing(tmp_path):
    log = MatchLog(tmp_path / "m.json")
    assert log.apply_replay({"start": "x", "end": "y", "chests": 2}, 9, 9, 0) == 0
