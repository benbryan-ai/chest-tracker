import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import importer
from adjustments import Adjustments
from matches import MatchLog


def l_match(chests, destroyed=0, playlist="Playlist_DefaultSquad", map_="/Delilah/Maps/Delilah_Terrain",
            player="Sam", epic="abc", custom=False, start="2026-11-14T21:00:00.0000000Z"):
    return {"MatchStartUtc": start, "DurationSeconds": 900, "Playlist": playlist, "Map": map_, "PlayerName": player,
            "EpicId": epic, "IsCustomMatch": custom, "ChestsOpened": chests,
            "Chests": [{"Destroyed": i < destroyed} for i in range(chests)]}


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_l_total_follows_its_own_rules(tmp_path):
    path = write(tmp_path / "ChestCounter" / "data.json", {
        "Matches": [l_match(20, 2), l_match(10, start="2026-11-14T22:00:00Z"),
                    l_match(99, playlist="Playlist_Figment"), l_match(50, custom=True),
                    l_match(7, map_="/Other/Maps/Old")],
        "ManualChests": {"": 5, "abc": 10},
    })
    [offer] = importer.read_l(path)
    assert offer.chests == 20 + 10 + 5 + 10
    assert offer.manual == 15 and offer.skipped == 3 and offer.label == "Sam"
    assert [(m["chests"], m["broken"], m["opened"]) for m in offer.matches] == [(20, 2, 18), (10, 0, 10)]


def test_each_account_gets_its_own_offer(tmp_path):
    path = write(tmp_path / "d.json", {"Matches": [l_match(5, player="A", epic="a"), l_match(9, player="B", epic="b")]})
    assert sorted(o.chests for o in importer.read_l(path)) == [5, 9]


def test_property_names_may_be_any_case(tmp_path):
    path = write(tmp_path / "d.json", {"matches": [{k.lower(): v for k, v in l_match(8).items()}]})
    assert importer.read_l(path)[0].chests == 8


def test_d_totals_add_the_starting_number(tmp_path):
    history = write(tmp_path / "history.json", {"Matches": [
        {"MatchStartUtc": "2026-11-14T21:00:00Z", "DurationSeconds": 600, "Chests": [{"Destroyed": True}, {"Destroyed": False}]},
        {"MatchStartUtc": "2026-11-14T22:00:00Z", "Chests": [{}]},
    ]})
    settings = write(tmp_path / "settings.json", {"StartingChests": 100})
    [offer] = importer.read_d(history, settings)
    assert offer.chests == 103 and len(offer.matches) == 2 and offer.matches[0]["broken"] == 1


def test_missing_or_damaged_files_give_no_offers(tmp_path):
    assert importer.read_l(tmp_path / "none.json") == []
    bad = tmp_path / "bad.json"
    bad.write_text("{not json")
    assert importer.read_l(bad) == [] and importer.read_d(bad) == []
    assert importer.find_offers(tmp_path) == []


def test_find_offers_looks_in_both_folders(tmp_path):
    write(tmp_path / "ChestCounter" / "data.json", {"Matches": [l_match(4)]})
    write(tmp_path / "chest-tracker" / "history.json", {"Matches": [{"MatchStartUtc": "2026-11-14T21:00:00Z", "Chests": [{}] * 6}]})
    assert sorted(o.source for o in importer.find_offers(tmp_path)) == ["ChestCounter", "chest-tracker"]


def test_imported_matches_skip_duplicates_and_come_out_again(tmp_path):
    log = MatchLog(tmp_path / "m.json")
    records = [{"start": "2026-11-01T20:00:00", "end": "2026-11-01T20:20:00", "chests": 5, "opened": 5, "broken": 0}]
    assert log.add_imported("b1", records) == 1
    assert log.add_imported("b2", records) == 0
    again = MatchLog(tmp_path / "m.json")
    assert again.history[0]["batch"] == "b1" and again.history[0]["source"] == "import"
    assert again.remove_batch("b1") == 1 and again.history == []


def test_adjustments_persist_and_reject_zero(tmp_path):
    a = Adjustments(tmp_path / "a.json")
    assert a.add(0, "hand", "nothing") is None
    entry = a.add(-5, "hand", "Total set to 3")
    assert Adjustments(tmp_path / "a.json").entries[0]["chests"] == -5
    assert a.remove(entry["id"]) is not None and a.remove(entry["id"]) is None


def test_treasure_finds_and_chest_times_come_across_from_l(tmp_path):
    match = l_match(3)
    match["Chests"] = [{"Destroyed": False, "TimeSeconds": 60.0}, {"Destroyed": False, "TimeSeconds": 30.5},
                       {"Destroyed": True, "TimeSeconds": 90}]
    match["TreasureFinds"] = [
        {"PrizeId": "DelilahPrize:dpid_item14", "Item": "raw", "FromGoldenChest": True, "ObtainedAtSeconds": 45.0},
        {"Item": "Some Skin", "FromGoldenChest": False}, {"Item": ""},
    ]
    path = write(tmp_path / "d.json", {"Matches": [match]})
    lookup = lambda pid: ("Solid Gold Lil Uzi Vert", "outfit") if pid == "DelilahPrize:dpid_item14" else None
    [offer] = importer.read_l(path, lookup)
    record = offer.matches[0]
    start = int(importer._utc_to_local("2026-11-14T21:00:00.0000000Z").astimezone(__import__("datetime").timezone.utc).timestamp())
    assert record["chest_times"] == [start + 30, start + 60, start + 90]
    assert [t["name"] for t in record["treasures"]] == ["Solid Gold Lil Uzi Vert", "Some Skin"]
    assert record["treasures"][0]["kind"] == "outfit" and record["treasures"][0]["golden"] is True
    assert record["treasures"][0]["at"] == start + 45 and record["treasures"][1]["at"] is None
    plain = importer.read_l(path)[0].matches[0]["treasures"]  # no hunt data to look names up in: the raw item name stays
    assert [t["name"] for t in plain] == ["raw", "Some Skin"]
