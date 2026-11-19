import io
import wave

import pytest

from chest_tracker.counting import chime
from chest_tracker.counting.chime import Chime, clamp_volume, make_chime


def read(data: bytes):
    with wave.open(io.BytesIO(data)) as w:
        frames = w.readframes(w.getnframes())
        return w, frames


def test_the_chime_is_a_valid_short_sound():
    data = make_chime(0.6)
    with wave.open(io.BytesIO(data)) as w:
        assert w.getnchannels() == 1 and w.getsampwidth() == 2
        assert w.getframerate() == chime.SAMPLE_RATE
        assert 0.2 < w.getnframes() / w.getframerate() < 0.8


def peak(data: bytes) -> int:
    with wave.open(io.BytesIO(data)) as w:
        raw = w.readframes(w.getnframes())
    samples = memoryview(raw).cast("h")
    return max(abs(x) for x in samples)


def test_louder_volume_means_a_bigger_wave_and_it_never_clips():
    quiet, loud = peak(make_chime(0.2)), peak(make_chime(1.0))
    assert quiet < loud < 32767


def test_the_chime_starts_and_ends_quietly_so_it_does_not_click():
    with wave.open(io.BytesIO(make_chime(1.0))) as w:
        samples = memoryview(w.readframes(w.getnframes())).cast("h")
    assert abs(samples[0]) < 500
    assert abs(samples[-1]) < 500


@pytest.mark.parametrize("value,expected", [
    (0.5, 0.5), (5, 1.0), (-1, 0.1), ("0.3", 0.3), ("loud", 0.6), (None, 0.6), (float("nan"), 0.6),
])
def test_volume_is_always_usable(value, expected):
    assert clamp_volume(value) == expected


def test_playing_builds_the_sound_once_per_volume():
    played = []
    c = Chime(player=played.append)
    assert c.play(0.5) and c.play(0.5)
    assert played[0] is played[1]
    c.play(0.9)
    assert played[2] is not played[0]


def test_a_failing_player_is_reported_not_raised():
    def broken(data):
        raise RuntimeError("no device")

    assert Chime(player=broken).play(0.5) is False


def test_the_windows_player_never_makes_the_caller_wait(monkeypatch):
    import threading
    import time

    started, release = threading.Event(), threading.Event()

    def slow_play(data):
        started.set()
        release.wait(2)

    monkeypatch.setattr(chime, "_play_blocking", slow_play)
    before = time.monotonic()
    chime._windows_player(b"sound")
    assert time.monotonic() - before < 0.5  # the sound is still "playing" and we already moved on
    assert started.wait(1)
    release.set()


def test_the_blocking_call_is_made_from_memory_without_the_background_flag(monkeypatch):
    import sys
    import types

    calls = []
    fake = types.SimpleNamespace(
        SND_MEMORY=4, SND_ASYNC=1, SND_NODEFAULT=2,
        PlaySound=lambda data, flags: calls.append((data, flags)),
    )
    monkeypatch.setitem(sys.modules, "winsound", fake)
    chime._play_blocking(b"abc")
    assert calls == [(b"abc", 4 | 2)]
    assert not calls[0][1] & fake.SND_ASYNC  # Windows refuses memory + background together


def test_a_sound_problem_is_logged_once_and_never_raised(monkeypatch, caplog):
    import sys
    import types

    def broken(data, flags):
        raise RuntimeError("no device")

    monkeypatch.setitem(sys.modules, "winsound", types.SimpleNamespace(
        SND_MEMORY=4, SND_ASYNC=1, SND_NODEFAULT=2, PlaySound=broken))
    monkeypatch.setattr(chime, "_warned", False)
    with caplog.at_level("WARNING", logger="chest-tracker"):
        chime._play_blocking(b"x")
        chime._play_blocking(b"x")
    assert len([r for r in caplog.records if "chime" in r.getMessage()]) == 1
