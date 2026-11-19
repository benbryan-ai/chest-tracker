import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from chest_tracker.data import content
from chest_tracker.group import protocol
from chest_tracker.data import treasures
from chest_tracker.counting.watcher import MatchPoster

NOW = datetime(2026, 11, 14, 12, 0, tzinfo=timezone.utc)


def hunt(*hours):
    c = content.Content(revision=1, updated="")
    c.hours = [content.Hour(NOW + timedelta(minutes=a), NOW + timedelta(minutes=b), {"outfit": 7.5}, confirmed)
               for a, b, confirmed in hours]
    return c


def test_the_overlay_line_for_a_treasure_hour():
    assert treasures.hour_status(hunt((-30, 90, True)), NOW) == "TREASURE HOUR: 1h 30m left"
    assert treasures.hour_status(hunt((-10, 5, True)), NOW) == "TREASURE HOUR: 5 min left"
    assert treasures.hour_status(hunt((50, 170, True)), NOW) == "Treasure Hour in 50 min"
    assert treasures.hour_status(hunt((130, 250, False)), NOW) == "Treasure Hour in 2h 10m (expected)"


def test_no_line_when_nothing_is_close():
    assert treasures.hour_status(hunt(), NOW) == ""
    assert treasures.hour_status(hunt((7 * 60, 8 * 60, True)), NOW) == ""  # too far ahead
    assert treasures.hour_status(hunt((-300, -240, True)), NOW) == ""  # already over


def test_a_treasure_line_is_plain_and_the_bot_ignores_it():
    line = protocol.format_treasure("Solid Gold *Lil* <@everyone> `x`")
    assert line.startswith(protocol.TREASURE_PREFIX) and "@" not in line and "*" not in line and "<" not in line
    assert protocol.parse_match(line) is None and protocol.parse_delta(line) is None
    assert protocol.format_treasure("   ").endswith("something golden")
    assert len(protocol.format_treasure("x" * 500)) < 140


def test_treasure_lines_are_queued_in_order_and_survive_a_restart(tmp_path):
    path = tmp_path / "p.json"
    poster = MatchPoster("https://discord.com/api/webhooks/1/x", "Sam", path)
    poster.add(12, "SQD")
    poster.add_text(protocol.format_treasure("Gold Thing"))
    again = MatchPoster("https://discord.com/api/webhooks/1/x", "Sam", path)
    assert again.queue[0] == {"chests": 12, "party": "SQD"} and "Gold Thing" in again.queue[1]["text"]


def test_a_treasure_line_is_posted_as_is(tmp_path, monkeypatch):
    from chest_tracker.counting import watcher
    sent = []

    class Ok:
        status_code, ok = 200, True

    monkeypatch.setattr(watcher.requests, "post", lambda url, **kw: sent.append(kw["json"]) or Ok())
    poster = MatchPoster("https://discord.com/api/webhooks/1/x", "Sam", tmp_path / "p.json")
    poster.add_text(protocol.format_treasure("Gold Thing"))
    poster.send_once()
    assert sent[0]["content"].endswith("Gold Thing") and sent[0]["username"] == "Sam"
    assert sent[0]["allowed_mentions"] == {"parse": []} and poster.queue == []
