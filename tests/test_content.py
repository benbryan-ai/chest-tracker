import copy
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from chest_tracker.data import content
from chest_tracker.data import treasures
from chest_tracker.data.content import ContentStore, Invalid, parse
from chest_tracker.counting.replays import clean_times, clean_treasures

BUNDLED = json.loads((Path(__file__).resolve().parent.parent / "assets" / "content.json").read_text(encoding="utf-8"))


class Reply:
    def __init__(self, data, status=200):
        self.content = json.dumps(data).encode() if not isinstance(data, bytes) else data
        self.status_code = status


def newer(revision=99, **changes):
    data = copy.deepcopy(BUNDLED)
    data["revision"] = revision
    data.update(changes)
    return data


def test_the_bundled_file_is_valid_and_complete():
    c = parse(BUNDLED)
    assert c.weeks and c.odds and c.pirate_shop and c.hours
    assert c.find_prize("DelilahPrize:dpid_item14") is not None
    assert c.find_prize("delilahprize:DPID_ITEM14") is not None  # case doesn't matter
    assert c.find_prize("nope") is None


@pytest.mark.parametrize("change", [
    {"schema": 2}, {"revision": 0}, {"revision": "3"}, {"revision": True}, {"weeks": "x"},
    {"odds": [{"kind": "mystery", "oneIn": 5, "weekly": False}]},
    {"odds": [{"kind": "car", "oneIn": 1, "weekly": False}]},
    {"treasureHours": [{"start": "2026-11-01T00:00:00Z", "end": "2026-11-03T00:00:00Z", "boosts": {"car": 2}}]},
    {"treasureHours": [{"start": "2026-11-01T00:00:00Z", "end": "2026-11-01T02:00:00Z", "boosts": {"car": 500}}]},
    {"weeks": [{"number": 1, "start": "not a date", "end": "2026-11-08T00:00:00Z", "prizes": []}]},
    {"weeks": [{"number": 1, "start": "2026-11-08T00:00:00Z", "end": "2026-11-01T00:00:00Z", "prizes": []}]},
])
def test_a_bad_file_is_rejected(change):
    with pytest.raises(Invalid):
        parse(newer(**change))


def test_duplicate_prize_ids_are_rejected():
    data = newer()
    data["weeks"][1]["prizes"][0]["id"] = data["weeks"][0]["prizes"][0]["id"]
    with pytest.raises(Invalid):
        parse(data)


def test_a_newer_download_is_adopted_and_saved(tmp_path):
    store = ContentStore(tmp_path, get=lambda *a, **k: Reply(newer(99)))
    assert store.refresh() is True and store.content.revision == 99
    assert ContentStore(tmp_path).content.revision == 99  # remembered on the next start


@pytest.mark.parametrize("reply", [Reply(newer(1)), Reply(newer(0)), Reply(b"not json"), Reply(newer(99), 404),
                                   Reply(newer(99, schema=7)), Reply(b"x" * (content.MAX_BYTES + 1))])
def test_anything_unusable_keeps_what_we_have(tmp_path, reply):
    store = ContentStore(tmp_path, get=lambda *a, **k: reply)
    before = store.content.revision
    assert store.refresh() is False and store.content.revision == before
    assert not (tmp_path / "content.json").exists()


def test_no_connection_is_not_an_error(tmp_path):
    def down(*a, **k):
        raise requests.ConnectionError("offline")

    assert ContentStore(tmp_path, get=down).refresh() is False


def test_a_damaged_cache_is_ignored(tmp_path):
    (tmp_path / "content.json").write_text("{broken")
    assert ContentStore(tmp_path).content.revision == parse(BUNDLED).revision


def test_a_cache_older_than_the_bundle_is_ignored(tmp_path):
    (tmp_path / "content.json").write_text(json.dumps(newer(1)))
    assert ContentStore(tmp_path).content.revision == parse(BUNDLED).revision


def test_boosts_apply_only_inside_treasure_hours():
    c = parse(BUNDLED)
    inside = datetime(2026, 11, 14, 20, 0, tzinfo=timezone.utc)
    assert c.boost("outfit", inside) == 7.5 and c.boost("jam", inside) == 1
    assert c.boost("outfit", datetime(2026, 11, 14, 12, 0, tzinfo=timezone.utc)) == 1


def test_chances_grow_with_chests_and_boosts():
    c = parse(BUNDLED)
    odds = next(o for o in c.odds if o.kind == "outfit")
    t = datetime(2026, 11, 14, 20, 0, tzinfo=timezone.utc)
    plain = treasures.chance(c, odds, [], 100)
    boosted = treasures.chance(c, odds, [t] * 100, 0)
    assert 0 < plain.at_least_once < boosted.at_least_once
    assert abs(plain.expected - 100 / odds.one_in) < 1e-12 and treasures.chance(c, odds, [], 0).at_least_once == 0


def test_percent_never_claims_a_certainty():
    assert treasures.percent(0) == "0%" and treasures.percent(0.00001) == "under 0.01%"
    assert treasures.percent(1.0) == "over 99.99%" and treasures.percent(0.5) == "50.0%"


def test_scanner_treasures_and_times_are_cleaned():
    raw = [{"Name": " Gold ", "Kind": "outfit", "PrizeId": "p", "Golden": True, "At": 1700000000},
           {"Name": "", "At": 1}, {"nope": 1}, "x", {"Name": "B", "At": "late", "Kind": 5}]
    got = clean_treasures(raw)
    assert got[0] == {"name": "Gold", "kind": "outfit", "prize_id": "p", "golden": True, "at": 1700000000}
    assert got[1]["at"] is None and got[1]["kind"] is None and len(got) == 2
    assert clean_times([1700000000, "x", -5, True, 1700000001]) == [1700000000, 1700000001]
    assert clean_treasures(None) == [] and clean_times("x") == []


def test_finds_and_the_weeks_collection():
    c = parse(BUNDLED)
    history = [{"start": "2026-11-14T15:00:00", "end": "2026-11-14T15:20:00", "chests": 1,
                "treasures": [{"name": "whatever", "kind": "outfit", "prize_id": "DelilahPrize:dpid_item14", "golden": True,
                               "at": 1763150000}]}]
    found = treasures.finds(history)
    assert len(found) == 1
    week = c.week_at(datetime(2026, 11, 10, tzinfo=timezone.utc))
    got = dict((p.id, n) for p, n in treasures.collection(c, found, week))
    assert got["w2-outfit"] == 1 and got["w2-car"] == 0
