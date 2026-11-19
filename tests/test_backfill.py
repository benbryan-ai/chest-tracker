import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from chest_tracker.counting import backfill
from chest_tracker.data.matches import MatchLog
from chest_tracker.counting.replays import ReplayCount

SINCE = datetime(2026, 11, 1)


def rc(start, chests=10, minutes=15):
    return ReplayCount("r", chests, chests - 1, 1, start, start + timedelta(minutes=minutes))


def rec(start, chests=5, **extra):
    return dict({"start": start.isoformat(timespec="seconds"),
                 "end": (start + timedelta(minutes=10)).isoformat(timespec="seconds"), "chests": chests}, **extra)


def test_an_unseen_match_is_added():
    plan = backfill.make_plan([rc(datetime(2026, 11, 5, 20))], [], SINCE)
    assert len(plan.new) == 1 and plan.total_change == 10 and plan.replaced == []


def test_a_counted_match_is_replaced_not_added_twice():
    history = [rec(datetime(2026, 11, 5, 20, 3), chests=6)]
    plan = backfill.make_plan([rc(datetime(2026, 11, 5, 20), chests=10)], history, SINCE)
    assert plan.new == [] and len(plan.replaced) == 1 and plan.total_change == 4


def test_counts_from_before_the_replays_stay_untouched():
    history = [rec(datetime(2026, 10, 20, 20)), rec(datetime(2026, 11, 5, 20, 3), chests=6)]
    plan = backfill.make_plan([rc(datetime(2026, 11, 5, 20))], history, SINCE)
    assert all(old["start"].startswith("2026-11-05") for item in plan.replaced for old in item["old"])


def test_replays_before_the_season_are_ignored():
    plan = backfill.make_plan([rc(datetime(2026, 10, 31, 23)), rc(datetime(2026, 11, 2, 1))], [], SINCE)
    assert plan.replays_in_season == 1 and plan.total_change == 10


def test_a_match_split_in_two_is_replaced_by_one():
    history = [rec(datetime(2026, 11, 5, 20, 2), chests=3), rec(datetime(2026, 11, 5, 20, 9), chests=4)]
    plan = backfill.make_plan([rc(datetime(2026, 11, 5, 20), chests=10)], history, SINCE)
    assert len(plan.replaced) == 1 and len(plan.replaced[0]["old"]) == 2 and plan.total_change == 3


def test_running_it_twice_changes_nothing_the_second_time(tmp_path):
    log = MatchLog(tmp_path / "m.json")
    log.history = [rec(datetime(2026, 11, 5, 20, 3), chests=6)]
    counts = [rc(datetime(2026, 11, 5, 20)), rc(datetime(2026, 11, 6, 20), chests=7)]
    plan = backfill.make_plan(counts, log.history, SINCE)
    log.apply_backfill("b1", plan.new, plan.replaced)
    again = backfill.make_plan(counts, log.history, SINCE)
    assert again.nothing_to_do and again.already == 2


def test_empty_and_zero_chest_replays_are_skipped():
    plan = backfill.make_plan([rc(datetime(2026, 11, 5, 20), chests=0)], [], SINCE)
    assert plan.replays_in_season == 0 and plan.nothing_to_do


def test_apply_and_restore_round_trip(tmp_path):
    log = MatchLog(tmp_path / "m.json")
    original = rec(datetime(2026, 11, 5, 20, 3), chests=6)
    older = rec(datetime(2026, 10, 1, 20))
    log.history = [older, original]
    counts = [rc(datetime(2026, 11, 5, 20)), rc(datetime(2026, 11, 6, 20), chests=7)]
    plan = backfill.make_plan(counts, log.history, SINCE)
    undo = log.apply_backfill("b1", plan.new, plan.replaced)
    assert [m["chests"] for m in log.history] == [5, 10, 7]
    assert MatchLog(tmp_path / "m.json").history[1]["source"] == "replay"  # saved and reloaded
    log.remove_batch("b1")
    log.restore(undo["restore"])
    assert log.history == [older, original]


def test_scanning_goes_through_the_folder_in_batches(tmp_path):
    for i in range(20):
        (tmp_path / f"{i:02}.replay").write_bytes(b"x")
    calls, progress = [], []
    found = backfill.scan_folder(Path("scan"), tmp_path, SINCE, lambda d, t: progress.append((d, t)),
                                 scan=lambda exe, files: calls.append(len(files)) or [])
    assert found == [] and sum(calls) == 20 and max(calls) <= backfill.BATCH
    assert progress[-1] == (20, 20)


def test_a_replay_counted_match_without_details_is_filled_in_not_recounted():
    r = rc(datetime(2026, 11, 5, 20), chests=10)
    r.kinds, r.chest_times = {"Chest": 10}, [1763000000]
    bare = rec(datetime(2026, 11, 5, 20, 3), chests=10, source="replay", opened=9, broken=1)
    plan = backfill.make_plan([r], [bare], SINCE)
    assert plan.refreshed == 1 and plan.total_change == 0 and len(plan.replaced) == 1 and plan.new == []
    full = dict(bare, kinds={"Chest": 10}, chest_times=[1763000000])
    again = backfill.make_plan([r], [full], SINCE)
    assert again.nothing_to_do and again.already == 1


def test_a_refresh_keeps_the_total_and_can_be_undone(tmp_path):
    log = MatchLog(tmp_path / "m.json")
    r = rc(datetime(2026, 11, 5, 20), chests=10)
    r.kinds = {"Chest": 10}
    bare = rec(datetime(2026, 11, 5, 20, 3), chests=10, source="replay", opened=9, broken=1)
    log.history = [bare]
    plan = backfill.make_plan([r], log.history, SINCE)
    undo = log.apply_backfill("b1", plan.new, plan.replaced)
    assert log.history[0]["kinds"] == {"Chest": 10} and log.history[0]["chests"] == 10
    log.remove_batch("b1")
    log.restore(undo["restore"])
    assert log.history[0].get("kinds") is None and log.history[0]["chests"] == 10
