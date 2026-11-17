import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import report
import startup
import timefmt
from replays import clean_kinds, parse_scan

TODAY = date(2026, 11, 15)


def m(start, chests, **extra):
    return dict({"start": start, "end": start, "chests": chests}, **extra)


def test_the_report_adds_up_the_history():
    data = report.build([m("2026-11-14T21:00:00", 20, kinds={"Chest": 18, "Rare chest": 2}),
                         m("2026-11-14T22:00:00", 10), m("2026-11-10T20:00:00", 6)], 500, 12, TODAY)
    assert (data.match_count, data.chests_in_matches, data.best, data.total, data.session) == (3, 36, 20, 500, 12)
    assert data.average == 12
    assert dict(data.days)[date(2026, 11, 14)] == 30 and dict(data.days)[date(2026, 11, 10)] == 6
    assert len(data.days) == report.DAYS_SHOWN and data.days[-1][0] == TODAY
    assert data.kinds[0] == ("Chest", 18) and data.kinds[-1][0] == report.UNSORTED
    assert dict(data.kinds)[report.UNSORTED] == 16
    assert data.latest[0]["start"].startswith("2026-11-14T22")


def test_an_empty_report_is_fine():
    data = report.build([], 0, 0, TODAY)
    assert data.average == 0 and data.best == 0 and data.kinds == [] and data.latest == []
    assert "Nothing yet" in report.render_html(data)


def test_the_web_page_stands_alone_and_escapes_names():
    data = report.build([m("2026-11-14T21:00:00", 3, kinds={"<b>x</b>": 3})], 3, 0, TODAY)
    page = report.render_html(data, "24", datetime(2026, 11, 15, 12, 0))
    assert "&lt;b&gt;x&lt;/b&gt;" in page and "<b>x</b>" not in page
    assert "<script" not in page and "http" not in page
    assert "Nov 14, 21:00: 3 chests" in page


def test_match_lines_show_broken_chests_and_the_clock():
    line = report.match_line(m("2026-11-14T21:32:00", 22, broken=3), "12")
    assert line == "Nov 14, 9:32 PM: 22 chests (3 broken)"
    assert report.match_line(m("2026-11-14T09:05:00", 1), "24") == "Nov 14, 09:05: 1 chest"


def test_clock_formats():
    t = datetime(2026, 11, 14, 0, 5)
    assert timefmt.format_time(t, "24") == "00:05" and timefmt.format_time(t, "12") == "12:05 AM"


def test_kinds_from_the_scanner_are_cleaned():
    assert clean_kinds({"Chest": 3, "": 2, "Bad": "x", "Zero": 0, "Rare chest": "4"}) == {"Chest": 3, "Rare chest": 4}
    assert clean_kinds(None) == {} and clean_kinds([1]) == {}
    entry = {"Status": "ok", "StartUtc": "2026-11-14T21:32:16Z", "DurationSeconds": 600, "Chests": 5,
             "Kinds": {"Chest": 5}}
    assert parse_scan(entry).kinds == {"Chest": 5}


def test_start_with_windows_is_off_where_it_cannot_work(tmp_path):
    if sys.platform == "win32":
        return
    assert not startup.supported(tmp_path / "x.exe") and not startup.is_enabled()
    assert startup.set_enabled(True, tmp_path / "x.exe") is False
    assert startup.command(Path("C:/A/Chest-Tracker.exe")) == '"C:/A/Chest-Tracker.exe" --minimized'


def test_match_details_list_types_and_treasures():
    match = m("2026-11-14T21:00:00", 12, source="replay", opened=10, broken=2, kinds={"Chest": 9, "Rare chest": 3},
              treasures=[{"name": "Solid Gold X"}])
    match["end"] = "2026-11-14T21:18:00"
    text = report.match_details(match, "24")
    assert "21:00" in text and "18 minutes" in text and "counted from the replay" in text
    assert "10 opened, 2 broken" in text and "Chest: 9" in text and "Solid Gold X" in text
    assert report.match_line(match, "24").endswith("12 chests (2 broken), 1 treasure")
    plain = report.match_details(m("2026-11-14T21:00:00", 1), "24")
    assert "counted from the screen" in plain and "opened" not in plain and "minutes" not in plain
