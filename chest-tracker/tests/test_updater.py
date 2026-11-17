import hashlib
import sys
from pathlib import Path

import pytest
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import updater
from updater import (CheckResult, Release, UpdateError, check_latest, clean_up_leftovers, download_update,
                     install_update, is_newer, parse_version, plain_notes, relaunch)

REPO = "benjamin-bryant/chest-tracker"
BODY = b"new exe bytes " * 1000
SHA = hashlib.sha256(BODY).hexdigest()


def api_json(tag="v1.2.0", digest=f"sha256:{SHA}", name="Chest-Tracker.exe", url=None, body="## v1.2.0\n- **Fast** [link](http://x)"):
    return {
        "tag_name": tag, "body": body, "html_url": f"https://github.com/{REPO}/releases/tag/{tag}",
        "assets": [{
            "name": name, "size": len(BODY), "digest": digest,
            "browser_download_url": url or f"https://github.com/{REPO}/releases/download/{tag}/{name}",
        }],
    }


class FakeResponse:
    def __init__(self, status=200, data=None, chunks=None):
        self.status_code, self._data, self.chunks = status, data, chunks or []
        self.ok = status < 400

    def json(self):
        if self._data is None:
            raise ValueError("no json")
        return self._data

    def iter_content(self, chunk_size):
        yield from self.chunks

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def getter(response):
    def get(url, **kwargs):
        if isinstance(response, Exception):
            raise response
        return response
    return get


def release(sha=SHA, size=len(BODY)):
    return Release("v1.2.0", "", f"https://github.com/{REPO}/releases/download/v1.2.0/Chest-Tracker.exe", size, sha, "page")


# --- versions ---

def test_versions_compare_numbers_not_text():
    assert is_newer("v1.10.0", "1.9.9") and is_newer("1.1.2", "1.1.1") and is_newer("2.0", "1.9.9")
    assert not is_newer("1.1.1", "1.1.1") and not is_newer("1.0.9", "1.1.0")


def test_a_beta_comes_before_its_final_release():
    assert is_newer("1.2.0", "1.2.0-beta") and not is_newer("1.2.0-beta", "1.2.0")
    assert parse_version("v1.2.0-beta") == ((1, 2, 0, 0), False)


def test_nonsense_versions_are_never_newer():
    assert parse_version("latest") is None
    assert not is_newer("latest", "1.0.0") and not is_newer("1.0.1", "garbage")


def test_release_notes_are_turned_into_plain_text():
    text = plain_notes("## v1.2\r\n- **Fast** [link](http://x)\r\n- `code`\n\n\n\nEnd")
    assert text == "v1.2\n• Fast link\n• code\n\nEnd"
    assert len(plain_notes("x" * 5000)) <= 2001


# --- checking ---

def test_a_newer_release_is_found_with_its_details():
    result = check_latest("1.1.1", REPO, get=getter(FakeResponse(data=api_json())))
    assert result.status == "newer"
    assert result.release.version == "1.2.0" and result.release.sha256 == SHA and "Fast link" in result.release.notes


def test_the_same_or_an_older_release_means_up_to_date():
    for tag in ("v1.1.1", "v1.0.0"):
        assert check_latest("1.1.1", REPO, get=getter(FakeResponse(data=api_json(tag)))).status == "current"


@pytest.mark.parametrize("response,words", [
    (requests.ConnectionError(), "reach GitHub"),
    (FakeResponse(404), "private"),
    (FakeResponse(403), "limiting"),
    (FakeResponse(500), "error"),
    (FakeResponse(200, None), "expected"),
    (FakeResponse(200, {"nope": 1}), "expected"),
])
def test_check_problems_become_plain_messages(response, words):
    result = check_latest("1.1.1", REPO, get=getter(response))
    assert result.status == "error" and words in result.message


def test_a_release_without_the_exe_is_reported_not_offered():
    data = api_json(name="other.zip")
    result = check_latest("1.1.1", REPO, get=getter(FakeResponse(data=data)))
    assert result.status == "error" and "1.2.0" in result.message


def test_a_download_link_outside_this_project_is_refused():
    data = api_json(url="https://evil.example.com/Chest-Tracker.exe")
    assert check_latest("1.1.1", REPO, get=getter(FakeResponse(data=data))).status == "error"
    data = api_json(url="https://github.com/someone-else/chest-tracker/releases/download/v1.2.0/Chest-Tracker.exe")
    assert check_latest("1.1.1", REPO, get=getter(FakeResponse(data=data))).status == "error"


def test_a_release_without_a_checksum_is_offered_but_cannot_be_installed(tmp_path):
    result = check_latest("1.1.1", REPO, get=getter(FakeResponse(data=api_json(digest=""))))
    assert result.status == "newer" and result.release.sha256 is None
    with pytest.raises(UpdateError, match="checksum"):
        download_update(result.release, tmp_path / "new.exe", fetch=lambda *a, **k: FakeResponse())


# --- downloading ---

def test_a_good_download_is_saved_and_reports_progress(tmp_path):
    seen = []
    chunks = [BODY[i:i + 4096] for i in range(0, len(BODY), 4096)]
    download_update(release(), tmp_path / "new.exe", fetch=lambda *a, **k: FakeResponse(chunks=chunks), on_progress=seen.append)
    assert (tmp_path / "new.exe").read_bytes() == BODY
    assert seen[-1] == 1.0 and not list(tmp_path.glob("*.part"))


@pytest.mark.parametrize("chunks,words", [
    ([b"tampered" * 2000], "checksum"),
    ([BODY[:100]], "cut short"),
])
def test_a_bad_download_is_thrown_away(tmp_path, chunks, words):
    rel = release(size=len(BODY) if words == "cut short" else sum(len(c) for c in chunks))
    with pytest.raises(UpdateError, match=words):
        download_update(rel, tmp_path / "new.exe", fetch=lambda *a, **k: FakeResponse(chunks=chunks))
    assert list(tmp_path.iterdir()) == []


def test_a_failed_or_oversized_download_leaves_nothing_behind(tmp_path, monkeypatch):
    with pytest.raises(UpdateError, match="404"):
        download_update(release(), tmp_path / "n.exe", fetch=lambda *a, **k: FakeResponse(404))
    monkeypatch.setattr(updater, "MAX_DOWNLOAD", 10)
    with pytest.raises(UpdateError, match="larger"):
        download_update(release(size=0), tmp_path / "n.exe", fetch=lambda *a, **k: FakeResponse(chunks=[BODY]))
    assert list(tmp_path.iterdir()) == []


def test_a_dropped_connection_is_an_update_error(tmp_path):
    def broken(*a, **k):
        raise requests.ConnectionError()
    with pytest.raises(UpdateError, match="interrupted"):
        download_update(release(), tmp_path / "n.exe", fetch=broken)


# --- installing ---

def test_install_swaps_the_exe_and_keeps_the_old_one_as_a_backup(tmp_path):
    exe, new = tmp_path / "Chest-Tracker.exe", tmp_path / "Chest-Tracker.exe.new"
    exe.write_bytes(b"old")
    new.write_bytes(b"new")
    install_update(exe, new)
    assert exe.read_bytes() == b"new" and (tmp_path / "Chest-Tracker.exe.old").read_bytes() == b"old"
    assert not new.exists()


def test_a_failed_swap_puts_the_old_exe_back(tmp_path, monkeypatch):
    exe, new = tmp_path / "Chest-Tracker.exe", tmp_path / "Chest-Tracker.exe.new"
    exe.write_bytes(b"old")
    new.write_bytes(b"new")
    real = updater.os.replace

    def flaky(src, dst):
        if Path(src) == new:
            raise PermissionError(13, "in use")
        return real(src, dst)

    monkeypatch.setattr(updater.os, "replace", flaky)
    with pytest.raises(UpdateError, match="Couldn't install"):
        install_update(exe, new)
    assert exe.read_bytes() == b"old"


def test_an_exe_that_cannot_be_renamed_is_left_alone(tmp_path, monkeypatch):
    exe, new = tmp_path / "a.exe", tmp_path / "a.exe.new"
    exe.write_bytes(b"old")
    new.write_bytes(b"new")
    monkeypatch.setattr(updater.os, "replace", lambda *a: (_ for _ in ()).throw(PermissionError(13, "locked")))
    with pytest.raises(UpdateError, match="Couldn't replace"):
        install_update(exe, new)
    assert exe.read_bytes() == b"old"


def test_leftovers_are_cleaned_up_after_an_update(tmp_path):
    exe = tmp_path / "Chest-Tracker.exe"
    exe.write_bytes(b"x")
    for suffix in (".old", ".new", ".part"):
        (tmp_path / f"Chest-Tracker.exe{suffix}").write_bytes(b"x")
    clean_up_leftovers(exe)
    assert [p.name for p in tmp_path.iterdir()] == ["Chest-Tracker.exe"]


def test_the_new_copy_is_started_with_the_settings_it_needs(tmp_path):
    started = []
    relaunch(tmp_path / "Chest-Tracker.exe", start=lambda cmd, **kw: started.append((cmd, kw)))
    command, options = started[0]
    assert command == [str(tmp_path / "Chest-Tracker.exe")]
    assert options["env"]["CHEST_TRACKER_UPDATED"] == "1" and options["env"]["PYINSTALLER_RESET_ENVIRONMENT"] == "1"


def test_running_from_source_has_no_exe_to_replace():
    assert updater.running_exe() is None
