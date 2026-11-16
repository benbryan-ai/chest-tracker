import json
import os
import stat
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import replays
from replays import ReplayCount, parse_scan, pick_replay

T0 = datetime(2026, 11, 14, 21, 0, 0)


def entry(**changes):
    base = {"File": "a.replay", "Status": "ok", "StartUtc": "2026-11-14T21:00:00.0000000+00:00",
            "DurationSeconds": 900, "Chests": 12, "Opened": 9, "Broken": 3}
    base.update(changes)
    return base


def count(start, minutes=15, chests=10):
    return ReplayCount("r", chests, chests, 0, start, start + timedelta(minutes=minutes))


def test_a_finished_replay_is_read():
    c = parse_scan(entry())
    assert (c.chests, c.opened, c.broken) == (12, 9, 3)
    assert c.end - c.start == timedelta(seconds=900)


def test_unfinished_or_broken_scans_are_ignored():
    for bad in (entry(Status="live"), entry(Status="incomplete"), entry(Status="error"),
                entry(StartUtc=None), entry(Chests="x"), entry(DurationSeconds=0), "nope", None):
        assert parse_scan(bad) is None


def test_an_unusual_map_is_noted_but_still_counted():
    c = parse_scan(entry(CountsAsMatch=False, WhyNot="not on the season map"))
    assert c.chests == 12 and "season map" in c.note


def test_the_replay_holding_the_first_chest_is_chosen():
    early, late = count(T0 - timedelta(hours=1)), count(T0 - timedelta(minutes=2))
    assert pick_replay([early, late], T0) is late
    assert pick_replay([early], T0) is None
    assert pick_replay([], T0) is None


def test_a_first_chest_just_outside_the_replay_still_matches():
    assert pick_replay([count(T0 + timedelta(seconds=30))], T0) is not None


def test_it_waits_for_the_replay_to_finish(tmp_path):
    (tmp_path / "x.replay").write_bytes(b"1")
    answers = [[], [], [count(T0)]]
    sleeps = []
    result = replays.count_match(T0, tmp_path, Path("scan"), sleep=sleeps.append, clock=lambda: 0.0,
                                 scan=lambda exe, files: answers.pop(0))
    assert result is not None and len(sleeps) == 2


def test_it_gives_up_when_no_replay_appears(tmp_path):
    (tmp_path / "x.replay").write_bytes(b"1")
    ticks = iter(range(0, 10000, 100))
    result = replays.count_match(T0, tmp_path, Path("scan"), sleep=lambda s: None,
                                 clock=lambda: float(next(ticks)), scan=lambda exe, files: [])
    assert result is None


def test_no_replay_folder_means_no_count(tmp_path):
    ticks = iter(range(0, 10000, 100))
    assert replays.count_match(T0, tmp_path / "missing", Path("scan"), sleep=lambda s: None,
                               clock=lambda: float(next(ticks))) is None


def test_it_stops_when_asked(tmp_path):
    assert replays.count_match(T0, tmp_path, Path("scan"), stop=lambda: True) is None


def test_a_scanner_that_prints_json_is_read(tmp_path):
    if os.name == "nt":
        return
    script = tmp_path / "fake-scan"
    script.write_text("#!/bin/sh\necho '%s'\n" % json.dumps([entry(), entry(Status="live")]))
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    found = replays.run_scan(script, [tmp_path / "a.replay"])
    assert [c.chests for c in found] == [12]


def test_a_scanner_that_fails_gives_nothing(tmp_path):
    assert replays.run_scan(tmp_path / "does-not-exist", [tmp_path / "a.replay"]) == []
    if os.name != "nt":
        script = tmp_path / "bad-scan"
        script.write_text("#!/bin/sh\necho 'not json'\n")
        script.chmod(script.stat().st_mode | stat.S_IEXEC)
        assert replays.run_scan(script, [tmp_path / "a.replay"]) == []


def test_the_scanner_is_found_by_override(tmp_path, monkeypatch):
    exe = tmp_path / replays.SCANNER_NAME
    exe.write_bytes(b"x")
    monkeypatch.setenv("CHEST_TRACKER_SCANNER", str(exe))
    assert replays.find_scanner() == exe
    monkeypatch.setenv("CHEST_TRACKER_SCANNER", str(tmp_path / "nope"))
    assert replays.find_scanner() is None or replays.find_scanner() != exe
