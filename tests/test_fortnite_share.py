import sys
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from chest_tracker.stats import boards
from chest_tracker.group import protocol
from chest_tracker.group.bot import ingest
from chest_tracker.group.store import Store
from test_ui import app, window  # noqa: F401  (the fixtures)

ROW = {"wins": 120, "kills": 3400, "matches": 900, "kd": 4.376, "minutesPlayed": 14500}


def test_a_fortnite_line_round_trips():
    line = protocol.format_fortnite_stats("lifetime", ROW)
    assert line.endswith("4.38 K/D · 14500 minutes")
    assert protocol.parse_fortnite_stats(line) == ("lifetime", 120, 3400, 900, 4.38, 14500)
    assert protocol.parse_delta(line) is None and protocol.parse_match_stats(line) is None


def test_missing_numbers_become_zero_and_bad_lines_are_ignored():
    line = protocol.format_fortnite_stats("season", {"wins": 2})
    assert protocol.parse_fortnite_stats(line) is None  # more wins than matches
    assert protocol.parse_fortnite_stats("Fortnite lifetime: lots") is None
    assert protocol.parse_fortnite_stats(protocol.format_fortnite_stats("year", ROW)) is None


def message(content, name="Sam", webhook=True):
    return SimpleNamespace(content=content, webhook_id=1 if webhook else None, id=1,
                           author=SimpleNamespace(name=name), created_at=datetime.now())


def test_the_bot_keeps_the_latest_numbers_per_window(tmp_path):
    store = Store(tmp_path / "c.db")
    assert ingest(store, message(protocol.format_fortnite_stats("lifetime", ROW)))
    assert ingest(store, message(protocol.format_fortnite_stats("lifetime", dict(ROW, wins=125))))
    assert ingest(store, message(protocol.format_fortnite_stats("season", dict(ROW, wins=7, matches=60))))
    assert not ingest(store, message(protocol.format_fortnite_stats("lifetime", ROW), webhook=False))
    life = store.fortnite_stats("lifetime")
    assert len(life) == 1 and life[0]["wins"] == 125 and round(life[0]["winrate"], 1) == 13.9
    assert store.fortnite_stats("season")[0]["wins"] == 7
    store.reset_player("sam")
    assert store.fortnite_stats("lifetime") == []


def rows():
    return [
        {"name": "Sam", "wins": 120, "kills": 3400, "matches": 900, "kd": 4.38, "winrate": 13.3, "minutes": 1},
        {"name": "Alex", "wins": 200, "kills": 2000, "matches": 1500, "kd": 1.9, "winrate": 13.3, "minutes": 1},
        {"name": "New", "wins": 1, "kills": 30, "matches": 4, "kd": 9.0, "winrate": 25.0, "minutes": 1},
    ]


def test_ranking_fortnite_categories():
    assert [r["name"] for r in boards.rank(rows(), "fn_wins")] == ["Alex", "Sam", "New"]
    assert [r["name"] for r in boards.rank(rows(), "fn_kd")] == ["Sam", "Alex"]  # 4 matches isn't enough to rank
    assert boards.shown(rows()[0], "fn_kd") == "4.38" and boards.shown(rows()[0], "fn_winrate") == "13.3%"


def test_fortnite_stats_have_no_weekly_board():
    data = {"lifetime": rows(), "season": rows()[:1]}
    assert boards.rows_for("fn_wins", "week", [], data) == []
    assert boards.rows_for("fn_wins", "all", [], data) == rows()
    assert boards.rows_for("fn_wins", "season", [], data) == rows()[:1]
    assert boards.rows_for("chests", "week", [{"name": "x"}], data) == [{"name": "x"}]
    assert "this season and all time" in boards.format_board([], "week", "fn_wins")


def test_the_page_shows_fortnite_categories(window):
    page = window.group
    page.show_board({"week": [], "season": [], "all": []}, 0, {"lifetime": rows(), "season": []})
    page.period_box.setCurrentIndex(page.period_box.findData("all"))
    page.category_box.setCurrentIndex(page.category_box.findData("fn_wins"))
    page.render()
    assert page.board.count() == 3 and page.board.itemAt(0).widget().name == "Alex"
    page.period_box.setCurrentIndex(page.period_box.findData("week"))
    page.render()
    assert page.board.count() == 1  # the explanation


def test_sharing_stats_only_posts_changes(window):
    window.settings.set(share_fortnite=True, webhook_url="https://discord.com/api/webhooks/1/x", player_name="Sam")
    window.stats_poster.queue = []
    lines = {"lifetime": protocol.format_fortnite_stats("lifetime", ROW),
             "season": protocol.format_fortnite_stats("season", dict(ROW, wins=3, matches=40))}
    window._post_fortnite_lines(lines)
    assert len(window.stats_poster.queue) == 2
    window._post_fortnite_lines(lines)
    assert len(window.stats_poster.queue) == 2  # nothing changed
    lines["season"] = protocol.format_fortnite_stats("season", dict(ROW, wins=4, matches=45))
    window._post_fortnite_lines(lines)
    assert len(window.stats_poster.queue) == 3


def test_nothing_is_looked_up_unless_sharing_is_on(window, monkeypatch):
    called = []
    monkeypatch.setattr("chest_tracker.gui.ui.fetch_stats", lambda *a: called.append(a))
    window.settings.set(fortnite_api_key="k", fortnite_account_name="Sam",
                        webhook_url="https://discord.com/api/webhooks/1/x", player_name="Sam")
    window.share_fortnite_stats()
    assert called == []


def test_the_checkbox_saves_the_choice(window):
    window.fortnite_stats.share.setChecked(True)
    assert window.settings["share_fortnite"] is True
