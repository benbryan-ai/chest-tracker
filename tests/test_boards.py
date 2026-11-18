import sys
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import boards
import protocol
from bot import ingest
from store import Store
from test_ui import app, window  # noqa: F401  (the fixtures)


def test_a_match_stats_line_round_trips():
    line = protocol.format_match_stats(1731900000, 17, 15, 2, 1)
    assert "<t:1731900000:f>" in line
    assert protocol.parse_match_stats(line) == (1731900000, 17, 15, 2, 1)
    assert protocol.parse_match_stats(protocol.format_match_stats(1731900000, 1, 1, 0, 0)) == (1731900000, 1, 1, 0, 0)


def test_bad_stats_lines_are_ignored():
    for text in ("hello", protocol.format_match_stats(1731900000, 0, 0, 0, 0),
                 protocol.format_match_stats(1731900000, 5, 9, 0, 0),
                 protocol.format_match_stats(1731900000, 9999, 9999, 0, 0)):
        assert protocol.parse_match_stats(text) is None
    assert protocol.parse_delta(protocol.format_match_stats(1731900000, 5, 5, 0, 0)) is None  # older bots skip it


def message(content, name="Sam", webhook=True, when=1731990000):
    return SimpleNamespace(content=content, webhook_id=1 if webhook else None, id=when,
                           author=SimpleNamespace(name=name), created_at=datetime.fromtimestamp(when))


def test_the_bot_stores_match_stats_and_replaces_a_corrected_match(tmp_path):
    store = Store(tmp_path / "c.db")
    assert ingest(store, message(protocol.format_match_stats(1731900000, 10, 10, 0, 0)))
    assert ingest(store, message(protocol.format_match_stats(1731900000, 12, 9, 3, 1), when=1731990100))
    rows = store.player_stats(0)
    assert len(rows) == 1 and rows[0]["matches"] == 1 and rows[0]["chests"] == 12 and rows[0]["broken"] == 3


def test_stats_from_people_not_posting_through_a_webhook_are_ignored(tmp_path):
    store = Store(tmp_path / "c.db")
    assert not ingest(store, message(protocol.format_match_stats(1731900000, 10, 10, 0, 0), webhook=False))
    assert store.player_stats(0) == []


def test_a_match_in_the_far_future_is_ignored(tmp_path):
    store = Store(tmp_path / "c.db")
    assert not ingest(store, message(protocol.format_match_stats(1731900000 + 10**7, 10, 10, 0, 0)))


def seeded(tmp_path):
    store = Store(tmp_path / "c.db")
    store.record_match("Sam", 1000, 10, 9, 1, 0)
    store.record_match("Sam", 5000, 20, 20, 0, 2)
    store.record_match("Sam", 9000, 15, 12, 3, 0)
    store.record_match("Alex", 6000, 30, 25, 5, 1)
    store.add_manual("Sam", 1000, 100)
    return store


def test_periods_only_count_matches_inside_them(tmp_path):
    store = seeded(tmp_path)
    recent = {r["name"]: r for r in store.player_stats(5000)}
    assert recent["Sam"]["matches"] == 2 and recent["Sam"]["chests"] == 35 and recent["Sam"]["best"] == 20
    assert recent["Alex"]["chests"] == 30


def test_all_time_chests_use_the_running_total(tmp_path):
    store = seeded(tmp_path)
    everyone = {r["name"]: r for r in store.player_stats(None)}
    assert everyone["Sam"]["chests"] == 1000  # the total, with its corrections, not the sum of matches
    assert everyone["Sam"]["matches"] == 3 and everyone["Sam"]["best"] == 20


def test_ranking_by_category(tmp_path):
    rows = [r for r in seeded(tmp_path).player_stats(0)]
    assert [r["name"] for r in boards.rank(rows, "chests")] == ["Sam", "Alex"]  # Sam 45, Alex 30
    assert [r["name"] for r in boards.rank(rows, "best")] == ["Alex", "Sam"]
    assert [r["name"] for r in boards.rank(rows, "broken")] == ["Alex", "Sam"]
    assert [r["name"] for r in boards.rank(rows, "treasures")] == ["Sam", "Alex"]
    assert [r["name"] for r in boards.rank(rows, "average")] == ["Sam"]  # Alex has played too few matches
    assert boards.shown(rows[0] if rows[0]["name"] == "Sam" else rows[1], "average") == "15.0"


def test_period_start_values():
    now = datetime(2026, 11, 18, 15, 30)  # a Wednesday
    assert datetime.fromtimestamp(boards.period_start("week", now)) == datetime(2026, 11, 16)
    assert datetime.fromtimestamp(boards.period_start("season", now, "2026-11-01")) == datetime(2026, 11, 1)
    assert boards.period_start("season", now, "nonsense") is None
    assert boards.period_start("all", now) is None


def test_the_command_text(tmp_path):
    rows = seeded(tmp_path).player_stats(0)
    text = boards.format_board(rows, "week", "chests")
    assert "this week" in text and "**1.** Sam: 45" in text
    assert "Nothing counted yet" in boards.format_board([], "all", "average")


def test_the_page_ranks_the_chosen_period_and_category(window):
    page = window.group
    page.board_data = {
        "week": [{"name": "Sam", "chests": 30, "matches": 3, "best": 14, "opened": 28, "broken": 2, "treasures": 1},
                 {"name": "Alex", "chests": 20, "matches": 2, "best": 12, "opened": 20, "broken": 0, "treasures": 0}],
        "season": [], "all": [],
    }
    page.show_board(page.board_data, 50)
    assert page.board.count() == 2 and page.board.itemAt(0).widget().name == "Sam"
    page.category_box.setCurrentIndex(page.category_box.findData("best"))
    page.render()
    assert page.board.itemAt(0).widget().text == "14"
    page.period_box.setCurrentIndex(page.period_box.findData("season"))
    page.render()
    assert page.board.count() == 1  # the "nothing here yet" note
    assert window.nav.button(2).text() == "Leaderboards"


def test_a_finished_match_is_shared_with_the_bot(window):
    window.settings.set(webhook_url="https://discord.com/api/webhooks/1/x", player_name="Sam")
    window.stats_poster.wake.clear()
    window.stats_poster.queue = []
    window.matches.history.append({"start": "2026-11-18T20:00:00", "end": "2026-11-18T20:20:00", "chests": 12,
                                   "opened": 10, "broken": 2, "treasures": [{"name": "x"}]})
    window._share_match(window.matches.history[-1])
    text = window.stats_poster.queue[-1]["text"]
    assert protocol.parse_match_stats(text)[1:] == (12, 10, 2, 1)


def test_nothing_is_shared_without_a_webhook_and_name(window):
    window.stats_poster.queue = []
    window._share_match({"start": "2026-11-18T20:00:00", "end": "x", "chests": 12, "opened": 12, "broken": 0})
    assert window.stats_poster.queue == []


def test_sharing_history_only_sends_this_season_and_is_capped(window):
    window.settings.set(webhook_url="https://discord.com/api/webhooks/1/x", player_name="Sam", season_start="2026-11-01")
    window.stats_poster.queue = []
    window.matches.history = [
        {"start": "2026-10-20T20:00:00", "end": "x", "chests": 9, "opened": 9, "broken": 0},
        {"start": "2026-11-05T20:00:00", "end": "x", "chests": 11, "opened": 11, "broken": 0},
    ]
    assert window.share_match_history() == 1
    assert len(window.stats_poster.queue) == 1
