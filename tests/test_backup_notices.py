import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import backup
import notices
from adjustments import Adjustments
from matches import MatchLog
from settings import Stats

NOW = datetime(2026, 11, 16, 12, 0, tzinfo=timezone.utc)


def make_data(folder, total=250, matches=2):
    stats = Stats(folder)
    stats.adjust_total(total)
    log = MatchLog(folder / "matches.json")
    for i in range(matches):
        log.add(3)
        log.finish()
    Adjustments(folder / "adjustments.json").add(100, "hand", "Total set to 250")


def test_a_backup_round_trips(tmp_path):
    src, dst = tmp_path / "a", tmp_path / "b"
    src.mkdir(), dst.mkdir()
    make_data(src)
    file = backup.write(src, tmp_path / "x" / "b.json")
    stats, matches, adjustments, _ = backup.load(backup.read(file))
    assert stats.total == 250 and len(matches.history) == 2 and adjustments.entries[0]["chests"] == 100
    assert "250" in backup.describe(backup.read(file))


def test_settings_secrets_are_never_in_a_backup(tmp_path):
    make_data(tmp_path)
    (tmp_path / "settings.json").write_text(json.dumps({"webhook_url": "https://discord.com/api/webhooks/1/SECRET"}))
    assert "SECRET" not in json.dumps(backup.make(tmp_path))


@pytest.mark.parametrize("text", ["not json", "[]", '{"app": "other", "files": {}}',
                                  '{"app": "chest-tracker", "format": 9, "files": {"stats.json": {}}}',
                                  '{"app": "chest-tracker", "format": 1, "files": {}}',
                                  '{"app": "chest-tracker", "format": 1, "files": {"evil.json": {}}}',
                                  '{"app": "chest-tracker", "format": 1, "files": {"stats.json": []}}'])
def test_a_bad_backup_is_refused(tmp_path, text):
    path = tmp_path / "bad.json"
    path.write_text(text)
    with pytest.raises(backup.BadBackup):
        backup.read(path)
    with pytest.raises(backup.BadBackup):
        backup.read(tmp_path / "missing.json")


def test_a_backup_with_a_broken_total_is_refused(tmp_path):
    path = tmp_path / "b.json"
    path.write_text(json.dumps({"app": "chest-tracker", "format": 1, "files": {"stats.json": {"total": "lots"}}}))
    with pytest.raises(backup.BadBackup):
        backup.load(backup.read(path))


def test_the_automatic_backup_runs_once_a_day_and_keeps_a_week(tmp_path):
    assert backup.auto_backup(tmp_path, date(2026, 11, 1)) is None  # no data yet: nothing to save
    make_data(tmp_path)
    first = backup.auto_backup(tmp_path, date(2026, 11, 1))
    assert first is not None and backup.auto_backup(tmp_path, date(2026, 11, 1)) is None
    for day in range(2, 11):
        backup.auto_backup(tmp_path, date(2026, 11, day))
    names = sorted(p.name for p in backup.backups_folder(tmp_path).glob("backup-*.json"))
    assert len(names) == backup.KEEP_DAILY and names[-1] == "backup-2026-11-10.json"


def test_safety_backups_are_kept_separately(tmp_path):
    make_data(tmp_path)
    for i in range(5):
        backup.safety_backup(tmp_path, datetime(2026, 11, 16, 12, 0, i))
    assert len(list(backup.backups_folder(tmp_path).glob("before-restore-*.json"))) == backup.KEEP_SAFETY


# --- notices ---

def raw(**changes):
    base = {"id": "n1", "level": "warning", "title": "Heads up", "text": "A Fortnite update broke replays."}
    base.update(changes)
    return base


def test_notices_are_read_and_bad_entries_skipped():
    data = {"schema": 1, "notices": [raw(), raw(id=""), raw(level="alarm"), raw(text="x" * 401), "x",
                                     raw(id="n2", minVersion="banana"), raw(id="n3", **{"from": "2026-11-01"}),
                                     {"text": "no id"}]}
    assert [n.id for n in notices.parse(data)] == ["n1"]
    assert notices.parse({"schema": 2, "notices": [raw()]}) == [] and notices.parse([]) == []


def test_notices_follow_dates_and_versions():
    n = notices.parse({"schema": 1, "notices": [raw(**{"from": "2026-11-16T00:00:00Z", "to": "2026-11-20T00:00:00Z",
                                                        "minVersion": "1.5.0", "maxVersion": "1.6.0"})]})[0]
    assert n.active(NOW, "1.5.0") and n.active(NOW, "1.6.0")
    assert not n.active(NOW, "1.4.9") and not n.active(NOW, "1.6.1")
    assert not n.active(NOW - timedelta(days=1), "1.5.0") and not n.active(NOW + timedelta(days=5), "1.5.0")


def test_notice_text_is_shown_as_plain_text():
    n = notices.parse({"schema": 1, "notices": [raw(title="<b>x</b>", text="<script>alert(1)</script>")]})[0]
    assert "<script>" not in n.html() and "&lt;script&gt;" in n.html()


class Reply:
    def __init__(self, data, status=200):
        self.content = data if isinstance(data, bytes) else json.dumps(data).encode()
        self.status_code = status


def test_the_feed_updates_and_survives_failures():
    feed = notices.NoticeFeed(get=lambda *a, **k: Reply({"schema": 1, "notices": [raw()]}))
    assert feed.refresh() is True and feed.refresh() is False and len(feed.items) == 1
    assert feed.current(["n1"], NOW) == [] and len(feed.current([], NOW, "1.5.0")) == 1

    def down(*a, **k):
        raise requests.ConnectionError("offline")

    for get in (down, lambda *a, **k: Reply(b"junk"), lambda *a, **k: Reply({}, 404),
                lambda *a, **k: Reply(b"x" * (notices.MAX_BYTES + 1))):
        broken = notices.NoticeFeed(get=get)
        assert broken.refresh() is False and broken.items == []
