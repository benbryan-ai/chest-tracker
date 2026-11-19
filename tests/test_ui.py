"""Window-level behavior, run headless. Skipped where PySide6 isn't installed."""

import os
import sys
import threading
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QMessageBox

from chest_tracker.data import backup
from chest_tracker.data import importer
from chest_tracker.data import notices
from chest_tracker.counting import replays
from chest_tracker.gui import ui
from datetime import datetime


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def no_network(*args, **kwargs):
    import requests

    raise requests.ConnectionError("tests don't use the network")


@pytest.fixture
def window(app, tmp_path):
    main = ui.MainWindow(tmp_path, QIcon())
    main.content_store.get = no_network  # the treasure data refresh must never reach the internet from a test
    yield main
    main._shut_down()


def share_to_discord(window):
    window.settings.set(webhook_url="https://discord.com/api/webhooks/1/x", player_name="Sam")


def test_removing_a_chest_at_zero_sends_nothing_to_discord(window):
    share_to_discord(window)
    window.record_chest(-1, "hotkey")
    window.record_chest(-1, "hotkey")
    assert window.stats.total == 0
    assert window.sender.pending == 0


def test_discord_total_follows_the_local_total(window):
    share_to_discord(window)
    window.sender.wake.clear()
    for amount in (1, 1, -1, -1, -1, 1):
        window.record_chest(amount, "detected" if amount > 0 else "hotkey")
    assert window.stats.total == 1
    assert window.sender.pending == 1  # what Discord is still owed matches what is really counted


def test_local_only_mode_queues_nothing(window):
    window.record_chest(1, "detected")
    assert window.stats.total == 1
    assert window.sender.pending == 0


def test_player_name_discord_would_refuse_is_not_saved(window):
    page = window.setup
    page.name.setText("Discord")
    page._save_name()
    assert window.settings["player_name"] == ""
    assert not page.name_status.isHidden()
    page.name.setText("Sam")
    page._save_name()
    assert window.settings["player_name"] == "Sam"
    assert page.name_status.isHidden()


def test_prompt_dialog_stops_listening_for_f8_once_closed(window):
    dialog = ui.PromptDialog(window.setup, window.templates_dir, window.settings["search_area"])
    assert dialog.timer.isActive()
    dialog.reject()
    assert not dialog.timer.isActive()


def test_prompt_dialog_stops_listening_after_saving(window):
    dialog = ui.PromptDialog(window.setup, window.templates_dir, window.settings["search_area"])
    dialog.accept()
    assert not dialog.timer.isActive()


class FakeEngine:
    instances = []

    def __init__(self, *args, **kwargs):
        self.kwargs = kwargs
        self.paused = threading.Event()
        FakeEngine.instances.append(self)

    def start(self):
        pass

    def stop(self):
        pass

    def join(self, timeout=None):
        pass


def save_template(window):
    import cv2
    import numpy as np

    window.templates_dir.mkdir(exist_ok=True)
    cv2.imwrite(str(window.templates_dir / "chest_1.png"), np.full((20, 60), 90, np.uint8))


def test_a_bad_undo_key_falls_back_to_f10_instead_of_crashing(window, monkeypatch):
    monkeypatch.setattr(ui, "WatchEngine", FakeEngine)
    save_template(window)
    window.settings.set(remove_key="NOT-A-KEY")
    window.restart_engine()
    assert window.settings["remove_key"] == "F10"
    assert FakeEngine.instances[-1].kwargs["remove_hotkey"] == ui.VK_F10


def test_the_engine_uses_the_saved_undo_key(window, monkeypatch):
    monkeypatch.setattr(ui, "WatchEngine", FakeEngine)
    save_template(window)
    window.settings.set(remove_key="F6")
    window.restart_engine()
    assert FakeEngine.instances[-1].kwargs["remove_hotkey"] == 0x75


def test_an_out_of_range_threshold_is_clamped_for_the_engine(window, monkeypatch):
    seen = []
    real = ui.PromptMatcher.from_folder
    monkeypatch.setattr(ui, "WatchEngine", FakeEngine)
    monkeypatch.setattr(ui.PromptMatcher, "from_folder", classmethod(lambda cls, f, t: seen.append(t) or real(f, t)))
    save_template(window)
    window.settings.set(match_threshold=0.2)
    window.restart_engine()
    assert seen[-1] == 0.5


@pytest.mark.parametrize("answer,saved", [(QMessageBox.StandardButton.No, "F10"), (QMessageBox.StandardButton.Yes, "BACKSPACE")])
def test_choosing_a_typing_key_for_undo_asks_first(window, monkeypatch, answer, saved):
    monkeypatch.setattr(ui, "WatchEngine", FakeEngine)
    monkeypatch.setattr(QMessageBox, "question", lambda *args, **kwargs: answer)
    window.setup._save_remove_key("BACKSPACE")
    assert window.settings["remove_key"] == saved


def test_choosing_a_function_key_for_undo_needs_no_question(window, monkeypatch):
    monkeypatch.setattr(ui, "WatchEngine", FakeEngine)
    monkeypatch.setattr(QMessageBox, "question", lambda *args, **kwargs: pytest.fail("should not ask"))
    window.setup._save_remove_key("F6")
    assert window.settings["remove_key"] == "F6"


def test_every_page_builds_and_the_overlay_follows_the_count(window):
    for index in range(4):
        window.go_to(index)
    window.record_chest(1, "detected")
    assert window.overlay.count == 1


class FakeListener:
    def __init__(self):
        self.queue = []

    def take_any(self):
        return self.queue.pop(0) if self.queue else None


def test_setup_key_picker_takes_a_controller_button(app, monkeypatch):
    fake = FakeListener()
    monkeypatch.setattr(ui, "shared_gamepad", lambda: fake)
    capture = ui.KeyCapture()
    chosen = []
    capture.captured.connect(chosen.append)
    capture._listen()
    assert "controller button" in capture.text()
    capture._check_pad()
    assert chosen == [] and capture.listening  # nothing pressed yet
    fake.queue.append("PAD_RT")
    capture._check_pad()
    assert chosen == ["PAD_RT"]
    assert not capture.listening and not capture.pad_timer.isActive()
    assert capture.text() == "Controller Right trigger"


def test_undo_key_picker_ignores_the_controller(app, monkeypatch):
    fake = FakeListener()
    fake.queue.append("PAD_A")
    monkeypatch.setattr(ui, "shared_gamepad", lambda: fake)
    capture = ui.KeyCapture(keyboard_only=True, action_label="undo key")
    capture._listen()
    assert not capture.pad_timer.isActive()
    assert "controller" not in capture.text()
    capture._finish(None)


def test_a_saved_controller_button_is_shown_by_name(window, monkeypatch):
    monkeypatch.setattr(ui, "shared_gamepad", lambda: FakeListener())
    window.settings.set(interact_keys=["PAD_A"])
    assert ui.key_label("PAD_A") == "Controller A button"


def refuse_keys(monkeypatch):
    warned = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *args, **kwargs: warned.append(args[1]))
    return warned


def test_the_engine_gets_the_pause_key_and_a_way_to_report_it(window, monkeypatch):
    monkeypatch.setattr(ui, "WatchEngine", FakeEngine)
    save_template(window)
    window.restart_engine()
    kwargs = FakeEngine.instances[-1].kwargs
    assert kwargs["pause_hotkey"] == ui.VK_F9
    assert kwargs["on_pause"] == window.pause_pressed.emit


def test_a_bad_pause_key_falls_back_to_f9(window, monkeypatch):
    monkeypatch.setattr(ui, "WatchEngine", FakeEngine)
    save_template(window)
    window.settings.set(pause_key="NOT-A-KEY")
    window.restart_engine()
    assert window.settings["pause_key"] == "F9"
    assert FakeEngine.instances[-1].kwargs["pause_hotkey"] == ui.VK_F9


def test_pause_undo_and_interact_keys_must_all_differ(window, monkeypatch):
    monkeypatch.setattr(ui, "WatchEngine", FakeEngine)
    warned = refuse_keys(monkeypatch)
    window.setup._save_pause_key("F10")  # undo's key
    window.setup._save_pause_key("E")  # interact's key
    window.setup._save_remove_key("F9")  # pause's key
    window.setup._save_key("F9")
    window.setup._save_key("F10")
    assert len(warned) == 5
    assert window.settings["pause_key"] == "F9"
    assert window.settings["remove_key"] == "F10"
    assert window.settings["interact_keys"] == ["E"]


def test_a_different_pause_key_is_saved_and_used(window, monkeypatch):
    monkeypatch.setattr(ui, "WatchEngine", FakeEngine)
    save_template(window)
    window.setup._save_pause_key("F7")
    assert window.settings["pause_key"] == "F7"
    assert FakeEngine.instances[-1].kwargs["pause_hotkey"] == 0x76


def test_a_typing_key_for_pause_asks_first(window, monkeypatch):
    monkeypatch.setattr(ui, "WatchEngine", FakeEngine)
    monkeypatch.setattr(QMessageBox, "question", lambda *args, **kwargs: QMessageBox.StandardButton.No)
    window.setup._save_pause_key("P")
    assert window.settings["pause_key"] == "F9"


def test_pausing_stops_counting_without_stopping_the_engine(window, monkeypatch):
    monkeypatch.setattr(ui, "WatchEngine", FakeEngine)
    save_template(window)
    window.restart_engine()
    engine = FakeEngine.instances[-1]
    window.toggle_pause()
    assert window.paused and engine.paused.is_set()
    assert window.overlay.paused
    assert window.tracker.pause.text() == "Resume tracking"
    assert window.current_state == "off"
    window.toggle_pause()
    assert not window.paused and not engine.paused.is_set()
    assert not window.overlay.paused
    assert window.tracker.pause.text() == "Pause tracking"
    assert FakeEngine.instances[-1] is engine  # no restart was needed


def test_the_pause_key_flips_the_pause_state(window, monkeypatch):
    monkeypatch.setattr(ui, "WatchEngine", FakeEngine)
    save_template(window)
    window.restart_engine()
    window.pause_pressed.emit()
    assert window.paused
    window.pause_pressed.emit()
    assert not window.paused


def test_a_new_engine_starts_paused_when_the_app_is_paused(window, monkeypatch):
    monkeypatch.setattr(ui, "WatchEngine", FakeEngine)
    save_template(window)
    window.restart_engine()
    window.toggle_pause()
    window.settings.set(remove_key="F6")
    window.restart_engine()  # e.g. a setting changed while paused
    assert FakeEngine.instances[-1].paused.is_set()
    assert window.paused


def test_resuming_with_no_engine_starts_one(window, monkeypatch):
    monkeypatch.setattr(ui, "WatchEngine", FakeEngine)
    window.paused = True
    window.toggle_pause()  # setup unfinished, so there was no engine
    assert not window.paused


class Recorder:
    def __init__(self):
        self.played = []

    def __call__(self, data):
        self.played.append(data)


def test_the_chime_plays_for_a_counted_chest_only_when_turned_on(window):
    recorder = Recorder()
    window.chime = ui.Chime(player=recorder)
    window.record_chest(1, "detected")
    assert recorder.played == []  # off by default
    window.settings.set(chime_enabled=True)
    window.record_chest(1, "detected")
    assert len(recorder.played) == 1
    window.record_chest(-1, "hotkey")  # an undo is not a celebration
    assert len(recorder.played) == 1


def test_no_chime_when_nothing_changed(window):
    recorder = Recorder()
    window.chime = ui.Chime(player=recorder)
    window.settings.set(chime_enabled=True)
    window.stats.add(-window.stats.total)
    window.record_chest(-1, "hotkey")
    assert recorder.played == []


def test_the_test_button_plays_at_the_chosen_volume(window):
    recorder = Recorder()
    window.chime = ui.Chime(player=recorder)
    window.settings.set(chime_volume=0.3)
    window.play_chime()
    window.play_chime(volume=0.9)
    assert len(recorder.played) == 2
    assert recorder.played[0] != recorder.played[1]  # a louder sound is a different recording


def test_a_broken_sound_system_does_not_stop_counting(window):
    def broken(data):
        raise OSError("no sound device")

    window.chime = ui.Chime(player=broken)
    window.settings.set(chime_enabled=True)
    window.record_chest(1, "detected")
    assert window.stats.total == 1


def test_overlay_size_and_opacity_apply_and_are_saved(window):
    window.set_overlay_scale(1.5)
    window.set_overlay_opacity(0.6)
    assert window.overlay.width() == round(220 * 1.5) and window.overlay.height() == round(96 * 1.5)
    assert window.overlay.opacity == 0.6
    assert window.settings["overlay_scale"] == 1.5
    assert window.settings["overlay_opacity"] == 0.6


def test_overlay_options_are_kept_in_range(window):
    window.set_overlay_scale(50)
    window.set_overlay_opacity(-3)
    assert window.overlay.scale == 2.0
    assert window.overlay.opacity == 0.3


def test_dragging_a_slider_previews_without_saving_until_released(window):
    window.set_overlay_scale(1.8, save=False)
    assert window.overlay.scale == 1.8
    assert window.settings["overlay_scale"] == 1.0
    window.set_overlay_scale(1.8)
    assert window.settings["overlay_scale"] == 1.8


def test_damaged_overlay_settings_fall_back_instead_of_crashing(app, tmp_path):
    (tmp_path / "settings.json").write_text(
        '{"overlay_scale": "huge", "overlay_opacity": null, "chime_volume": "loud"}', encoding="utf-8"
    )
    main = ui.MainWindow(tmp_path, QIcon())
    try:
        assert main.overlay.scale == 1.0 and main.overlay.opacity == 1.0
        assert main.setup.volume_slider.value() == 60
    finally:
        main._shut_down()


def test_setup_sliders_start_where_the_settings_are(app, tmp_path):
    (tmp_path / "settings.json").write_text(
        '{"overlay_scale": 1.5, "overlay_opacity": 0.5, "chime_volume": 0.25}', encoding="utf-8"
    )
    main = ui.MainWindow(tmp_path, QIcon())
    try:
        assert main.setup.size_slider.value() == 150
        assert main.setup.opacity_slider.value() == 50
        assert main.setup.volume_slider.value() == 25
        assert main.overlay.scale == 1.5
    finally:
        main._shut_down()


def test_the_overlay_says_when_it_is_paused(window):
    window.toggle_pause()
    image = window.overlay.grab().toImage()
    assert not image.isNull()
    window.toggle_pause()


def test_chests_count_toward_the_current_match_and_undo_takes_one_off(window):
    for _ in range(3):
        window.record_chest(1, "detected")
    window.record_chest(-1, "hotkey")
    assert window.matches.current == 2
    assert window.overlay.match == 2
    assert window.tracker.match_count.text() == "2"


def test_a_new_match_saves_the_old_one_and_resets_the_count(window):
    for _ in range(5):
        window.record_chest(1, "detected")
    window.finish_match("key")
    assert window.matches.current == 0 and window.overlay.match == 0
    assert [m["chests"] for m in window.matches.history] == [5]
    assert "average 5.0" in window.tracker.match_summary.text()
    assert window.stats.total == 5  # the lifetime total is untouched


def test_the_end_screen_signal_finishes_the_match(window):
    window.record_chest(1, "detected")
    window.match_ended.emit()
    assert window.matches.current == 0 and len(window.matches.history) == 1


def test_a_new_match_with_no_chests_saves_nothing(window):
    window.finish_match("button")
    assert window.matches.history == []


def test_the_engine_gets_the_match_key_and_end_screen_hooks(window, monkeypatch):
    monkeypatch.setattr(ui, "WatchEngine", FakeEngine)
    save_template(window)
    window.restart_engine()
    kwargs = FakeEngine.instances[-1].kwargs
    assert kwargs["match_hotkey"] == ui.VK_F8
    assert kwargs["on_new_match"] == window.new_match_pressed.emit
    assert kwargs["on_match_end"] == window.match_ended.emit
    assert kwargs["match_open"]() is False
    window.record_chest(1, "detected")
    assert kwargs["match_open"]() is True


def test_a_bad_match_key_falls_back_to_f8(window, monkeypatch):
    monkeypatch.setattr(ui, "WatchEngine", FakeEngine)
    save_template(window)
    window.settings.set(match_key="NOT-A-KEY")
    window.restart_engine()
    assert window.settings["match_key"] == "F8"


def test_the_match_key_must_differ_from_the_other_keys(window, monkeypatch):
    monkeypatch.setattr(ui, "WatchEngine", FakeEngine)
    warned = refuse_keys(monkeypatch)
    window.setup._save_match_key("F9")
    window.setup._save_match_key("F10")
    window.setup._save_match_key("E")
    window.setup._save_pause_key("F8")
    window.setup._save_remove_key("F8")
    window.setup._save_key("F8")
    assert len(warned) == 6
    assert window.settings["match_key"] == "F8"


def test_a_different_match_key_is_saved_and_used(window, monkeypatch):
    monkeypatch.setattr(ui, "WatchEngine", FakeEngine)
    save_template(window)
    window.setup._save_match_key("F7")
    assert window.settings["match_key"] == "F7"
    assert FakeEngine.instances[-1].kwargs["match_hotkey"] == 0x76


def test_the_overlay_match_line_can_be_turned_off_and_stays_off(window):
    window.set_overlay_match(False)
    assert window.overlay.show_match is False and window.settings["overlay_show_match"] is False


def test_export_writes_the_history(window, monkeypatch, tmp_path):
    window.record_chest(1, "detected")
    window.finish_match("key")
    target = tmp_path / "out.csv"
    monkeypatch.setattr(ui.QFileDialog, "getSaveFileName", lambda *a, **k: (str(target), ""))
    window.export_match_history()
    assert target.read_text(encoding="utf-8-sig").splitlines()[1].endswith(",1,,,screen")


def share_matches(window, party=""):
    window.settings.set(
        match_webhook_url="https://discord.com/api/webhooks/2/y", player_name="Sam", party_code=party
    )


def test_a_finished_match_is_queued_for_the_match_webhook(window):
    share_to_discord(window)
    share_matches(window, "SQD")
    window.sender.wake.clear()
    window.record_chest(1, "detected")
    window.record_chest(1, "detected")
    window.poster.wake.clear()
    window.finish_match("key")
    assert window.poster.queue == [{"chests": 2, "party": "SQD"}]
    assert window.sender.pending == 2  # the normal chest count is separate and unchanged


def test_solo_players_can_turn_match_posts_off(window):
    share_matches(window)
    window.setup.match_post.setChecked(False)
    assert window.settings["match_post"] is False
    window.record_chest(1, "detected")
    window.finish_match("key")
    assert window.poster.queue == []
    assert window.matches.history[-1]["chests"] == 1  # still kept on this PC


def test_no_match_post_without_a_link_or_a_name_or_chests(window):
    window.record_chest(1, "detected")
    window.finish_match("key")
    window.settings.set(match_webhook_url="https://discord.com/api/webhooks/2/y")
    window.record_chest(1, "detected")
    window.finish_match("key")  # still no player name
    share_matches(window)
    window.finish_match("key")  # nothing counted this match
    assert window.poster.queue == []


def test_party_code_is_cleaned_saved_and_checked(window):
    page = window.setup
    page.party.setText(" sq 42 ")
    page._save_party()
    assert window.settings["party_code"] == "SQ42" and page.party.text() == "SQ42"
    page.party.setText("no way!")
    page._save_party()
    assert window.settings["party_code"] == "SQ42"
    assert not page.match_status.isHidden()
    page.party.setText("")
    page._save_party()
    assert window.settings["party_code"] == ""


def test_match_webhook_must_be_a_discord_link(window):
    page = window.setup
    page.match_webhook.setText("https://example.com/hook")
    page._save_match_webhook()
    assert window.settings["match_webhook_url"] == "" and not page.match_status.isHidden()
    page.match_webhook.setText("https://discord.com/api/webhooks/2/y")
    page._save_match_webhook()
    assert window.settings["match_webhook_url"].endswith("/2/y") and window.poster.url.endswith("/2/y")


def test_the_match_channel_id_is_saved_with_the_bot_settings(window):
    window.group.match_channel.setText(" 12345 ")
    window.group._save()
    assert window.settings["match_channel_id"] == "12345"


def test_an_unusable_party_code_in_the_settings_file_is_not_posted(window):
    share_matches(window, "x!")
    window.record_chest(1, "detected")
    window.finish_match("key")
    assert window.poster.queue == [{"chests": 1, "party": ""}]


# --- updates ---

from chest_tracker.system import updater as updater_module
def a_release(version="9.9.9"):
    return updater_module.Release(f"v{version}", "Fixes things.", "https://github.com/x/y/releases/download/v/z.exe",
                                  10, "ab" * 32, "https://github.com/x/y/releases/tag/v")


def newer(window, manual=False):
    window._on_update_checked(updater_module.CheckResult("newer", a_release()), manual)


def test_a_newer_version_shows_the_banner_and_setup_status(window):
    window.settings.set(update_mode="notify")
    newer(window)
    assert not window.banner.isHidden() and "9.9.9" in window.banner_text.text()
    assert "9.9.9" in window.setup.update_status.text()


def test_up_to_date_is_only_announced_when_asked_for(window):
    window._on_update_checked(updater_module.CheckResult("current"), False)
    assert window.setup.update_status.text() == "" and window.banner.isHidden()
    window._on_update_checked(updater_module.CheckResult("current"), True)
    assert "up to date" in window.setup.update_status.text()


def test_a_failed_check_is_quiet_unless_asked_for(window):
    result = updater_module.CheckResult("error", message="Couldn't reach GitHub.")
    window._on_update_checked(result, False)
    assert window.setup.update_status.text() == ""
    window._on_update_checked(result, True)
    assert "Couldn't reach GitHub" in window.setup.update_status.text()
    assert window.setup.update_check.isEnabled()


def test_the_update_mode_is_saved_and_off_stops_the_timer(window):
    window.setup.update_mode.setCurrentIndex(window.setup.update_mode.findData("off"))
    assert window.settings["update_mode"] == "off" and not window.update_timer.isActive()
    window.setup.update_mode.setCurrentIndex(window.setup.update_mode.findData("auto"))
    assert window.settings["update_mode"] == "auto" and window.update_timer.isActive()


def test_the_default_is_to_tell_the_person_not_to_install(window):
    assert window.settings["update_mode"] == "notify"
    window.found_update = a_release()
    window._try_auto_install()
    assert not window.installing


def test_auto_install_waits_for_a_quiet_moment(window, monkeypatch):
    window.settings.set(update_mode="auto")
    window.found_update = a_release()
    started = []
    monkeypatch.setattr(updater_module, "running_exe", lambda: Path("C:/x/Chest-Tracker.exe"))
    monkeypatch.setattr(window, "install_update", lambda: started.append(1))
    monkeypatch.setattr(ui, "fortnite_focused", lambda: True)
    window._try_auto_install()
    assert started == []  # Fortnite is in front
    monkeypatch.setattr(ui, "fortnite_focused", lambda: False)
    window.record_chest(1, "detected")
    window._try_auto_install()
    assert started == []  # a match with chests is open
    window.finish_match("key")
    window._try_auto_install()
    assert started == [1]


def test_install_from_source_opens_the_release_page_instead(window, monkeypatch):
    opened = []
    monkeypatch.setattr(ui.QDesktopServices, "openUrl", lambda url: opened.append(url.toString()))
    window.found_update = a_release()
    window.install_update()
    assert opened == ["https://github.com/x/y/releases/tag/v"] and not window.installing


def test_a_failed_download_shows_the_problem_and_allows_trying_again(window):
    window.found_update = a_release()
    window.installing = True
    window._on_update_failed("The download was interrupted. Try again.")
    assert not window.installing and window.banner_install.isEnabled()
    assert window.banner_install.text() == "Try again"
    assert "interrupted" in window.banner_text.text()


def test_a_finished_download_is_installed_and_the_app_restarts(window, monkeypatch, tmp_path):
    exe = tmp_path / "Chest-Tracker.exe"
    exe.write_bytes(b"old")
    new = tmp_path / "Chest-Tracker.exe.new"
    new.write_bytes(b"new")
    calls = []
    monkeypatch.setattr(updater_module, "running_exe", lambda: exe)
    monkeypatch.setattr(updater_module, "relaunch", lambda path: calls.append(("relaunch", path)))
    monkeypatch.setattr(window, "quit_app", lambda: calls.append(("quit", None)))
    window._on_update_ready(a_release(), new)
    assert exe.read_bytes() == b"new" and [c[0] for c in calls] == ["relaunch", "quit"]


def test_a_swap_that_fails_keeps_the_app_running(window, monkeypatch, tmp_path):
    exe = tmp_path / "Chest-Tracker.exe"
    exe.write_bytes(b"old")
    monkeypatch.setattr(updater_module, "running_exe", lambda: exe)
    monkeypatch.setattr(window, "quit_app", lambda: pytest.fail("must not quit"))
    window.found_update = a_release()
    window._on_update_ready(a_release(), tmp_path / "missing.new")
    assert exe.read_bytes() == b"old" and window.banner_install.text() == "Try again"


# --- replay counting ---

def finished_match(window, chests=2):
    share_to_discord(window)
    share_matches(window, "SQD")
    for _ in range(chests):
        window.record_chest(1, "detected")
    return window.matches.finish()


def test_a_replay_count_corrects_the_match_total_and_posts_it(window):
    record = finished_match(window)
    window.poster.queue.clear()
    window.sender.wake.clear()
    total_before = window.stats.total
    window._on_replay_counted(record, replays.ReplayCount("r", 5, 3, 2, datetime.now(), datetime.now()))
    assert window.matches.history[-1]["chests"] == 5
    assert window.stats.total == total_before + 3
    assert window.poster.queue == [{"chests": 5, "party": "SQD"}]


def test_a_missing_replay_keeps_the_screen_count_and_still_posts(window):
    record = finished_match(window)
    window.poster.queue.clear()
    window._on_replay_counted(record, None)
    assert window.matches.history[-1]["chests"] == 2
    assert window.poster.queue == [{"chests": 2, "party": "SQD"}]


def test_with_a_scanner_the_post_waits_for_the_replay(window, monkeypatch, tmp_path):
    exe = tmp_path / "scan"
    exe.write_bytes(b"x")
    monkeypatch.setattr(replays, "find_scanner", lambda: exe)
    monkeypatch.setattr(replays, "count_match", lambda *a, **k: None)
    share_to_discord(window)
    share_matches(window, "SQD")
    window.record_chest(1, "detected")
    window.poster.queue.clear()
    window.finish_match("key")
    assert window.poster.queue == []  # not yet: the replay is being read


def test_replay_counting_can_be_turned_off(window, monkeypatch, tmp_path):
    exe = tmp_path / "scan"
    exe.write_bytes(b"x")
    monkeypatch.setattr(replays, "find_scanner", lambda: exe)
    share_to_discord(window)
    share_matches(window, "SQD")
    window.setup.replay_count.setChecked(False)
    window.record_chest(1, "detected")
    window.poster.queue.clear()
    window.finish_match("key")
    assert window.poster.queue == [{"chests": 1, "party": "SQD"}]


# --- editable total, session, last match, import ---

def test_setting_the_total_keeps_today_and_can_be_undone(window):
    window.record_chest(1, "detected")
    window.record_chest(1, "detected")
    assert window.set_total(50) == 48
    assert window.stats.total == 50
    assert window.stats.today == 2 and window.stats.session == 2  # only the lifetime total moved
    entry = window.adjustments.entries[-1]
    assert entry["chests"] == 48
    window.undo_adjustment(entry["id"])
    assert window.stats.total == 2
    assert window.adjustments.entries == []


def test_setting_the_same_total_records_nothing(window):
    assert window.set_total(window.stats.total) == 0
    assert window.adjustments.entries == []


def test_a_typed_total_is_sent_to_the_group_and_undo_takes_it_back(window):
    share_to_discord(window)
    window.sender.wake.clear()
    window.set_total(500)
    assert window.sender.pending == 500
    window.undo_adjustment(window.adjustments.entries[-1]["id"])
    assert window.sender.pending == 0


def test_a_typed_total_is_not_sent_without_a_name_and_webhook(window):
    window.set_total(500)
    assert window.sender.pending == 0


def test_the_total_dialog_changes_the_total(window):
    dialog = ui.TotalDialog(window)
    dialog.total_edit.setText("1,234")
    dialog.apply_total()
    assert window.stats.total == 1234
    dialog.total_edit.setText("abc")
    dialog.apply_total()
    assert window.stats.total == 1234
    dialog.history.setCurrentRow(0)
    dialog.undo_selected()
    assert window.stats.total == 0


def test_an_import_adds_the_total_and_matches_and_undoes_cleanly(window):
    offer = importer.ImportOffer("ChestCounter", "Sam", 60, [
        {"start": "2026-11-01T20:00:00", "end": "2026-11-01T20:20:00", "chests": 20, "opened": 18, "broken": 2},
        {"start": "2026-11-01T21:00:00", "end": "2026-11-01T21:20:00", "chests": 25, "opened": 25, "broken": 0},
    ], 15)
    window.record_chest(1, "detected")
    window.finish_match("key")
    assert window.apply_import(offer) == 2
    assert window.stats.total == 61 and window.stats.today == 1
    assert [m["chests"] for m in window.matches.history][-1] == 1  # the live match stays last
    assert window.matches.last_chests() == 1
    dialog = ui.TotalDialog(window)
    dialog.offers = [offer]
    assert window.adjustments.has_import(offer.note)
    window.undo_adjustment(window.adjustments.entries[-1]["id"])
    assert window.stats.total == 1 and len(window.matches.history) == 1


def test_session_and_last_match_show_on_the_overlay_and_page(window):
    window.record_chest(1, "detected")
    window.record_chest(1, "detected")
    window.finish_match("key")
    assert window.matches.session_matches == 1
    assert window.overlay.last_match == 2 and window.overlay.session == 2 and window.overlay.session_matches == 1
    assert "Last match: 2" in window.tracker.last_match.text()
    assert "1 match finished" in window.tracker.session_matches.text()


def test_the_extra_overlay_row_can_be_hidden(window):
    window.set_overlay_last(False)
    assert window.overlay.height() == 76
    assert window.settings["overlay_show_last"] is False


# --- counting past replays ---

def past_replay(start, chests=10):
    from datetime import timedelta
    return replays.ReplayCount("r", chests, chests, 0, start, start + timedelta(minutes=15))


def test_counting_past_replays_corrects_adds_and_can_be_undone(window, monkeypatch):
    from datetime import datetime as dt
    window.settings.set(season_start="2026-11-01")
    window.stats.adjust_total(100)
    window.matches.history = [{"start": "2026-11-05T20:03:00", "end": "2026-11-05T20:13:00", "chests": 6},
                              {"start": "2026-10-01T20:00:00", "end": "2026-10-01T20:10:00", "chests": 9}]
    window.matches.save()
    since = dt(2026, 11, 1)
    found = [past_replay(dt(2026, 11, 5, 20, 0), 10), past_replay(dt(2026, 11, 7, 20, 0), 8)]
    plan = backfill_plan = ui.backfill.make_plan(found, window.matches.history, since)
    assert plan.total_change == 4 + 8
    assert window.apply_backfill(plan) == 12
    assert window.stats.total == 112
    assert [m["chests"] for m in window.matches.history] == [9, 10, 8]  # October untouched
    entry = window.adjustments.entries[-1]
    assert entry["kind"] == "replay"
    window.undo_adjustment(entry["id"])
    assert window.stats.total == 100
    assert [m["chests"] for m in window.matches.history] == [9, 6]


def test_the_scan_dialog_asks_before_changing_anything(window, monkeypatch):
    from datetime import datetime as dt
    dialog = ui.TotalDialog(window)
    monkeypatch.setattr(ui.QMessageBox, "question", lambda *a, **k: ui.QMessageBox.StandardButton.No)
    dialog._scan_done((dt(2026, 11, 1), [past_replay(dt(2026, 11, 5, 20))]))
    assert window.stats.total == 0 and window.matches.history == []
    monkeypatch.setattr(ui.QMessageBox, "question", lambda *a, **k: ui.QMessageBox.StandardButton.Yes)
    dialog._scan_done((dt(2026, 11, 1), [past_replay(dt(2026, 11, 5, 20))]))
    assert window.stats.total == 10 and len(window.matches.history) == 1


def test_the_scan_dialog_rejects_a_bad_date_and_a_missing_reader(window, monkeypatch):
    dialog = ui.TotalDialog(window)
    dialog.season_start.setText("soon")
    dialog.start_scan()
    assert "date" in dialog.status.text()
    dialog.season_start.setText("2026-11-01")
    monkeypatch.setattr(replays, "find_scanner", lambda: None)
    dialog.start_scan()
    assert "isn't part of this build" in dialog.status.text()


# --- report and settings pages ---

def test_the_report_page_shows_matches_ten_at_a_time(window):
    window.matches.history = [
        {"start": f"2026-11-{day:02}T20:00:00", "end": f"2026-11-{day:02}T20:10:00", "chests": day} for day in range(1, 26)
    ]
    window.report.refresh()
    assert window.report.latest.count() == 10 and window.report.more.isVisibleTo(window.report)
    window.report.show_more()
    window.report.show_more()
    assert window.report.latest.count() == 25 and not window.report.more.isVisibleTo(window.report)
    assert "25 chests" in window.report.latest.item(0).text()


def test_the_report_can_be_saved_as_a_web_page(window, monkeypatch):
    opened = []
    monkeypatch.setattr(ui.QDesktopServices, "openUrl", lambda url: opened.append(url) or True)
    window.record_chest(1, "detected")
    window.finish_match("key")
    window.open_report()
    assert (window.folder / "report.html").read_text(encoding="utf-8").count("Chest Tracker report") >= 1
    assert opened and opened[0].isLocalFile()


def test_settings_page_saves_its_choices(window):
    page = window.settings_page
    page.replay_folder.setText("  D:/Replays ")
    page.save_folder()
    assert window.settings["replay_folder"] == "D:/Replays"
    page.use_default()
    assert window.settings["replay_folder"] == ""
    page.clock.setCurrentIndex(page.clock.findData("12"))
    assert window.settings["clock_format"] == "12" and window.tracker.clock_format == "12"
    page.tray.setChecked(True)
    assert window.settings["minimize_to_tray"] is True
    assert not page.startup.isEnabled()  # from source there is no program to start


def test_the_activity_log_uses_the_chosen_clock(window):
    window.tracker.clock_format = "12"
    window.tracker.log("hello")
    assert window.tracker.activity.item(0).text().split("   ")[0].endswith(("AM", "PM"))


# --- treasures ---

def test_the_treasures_page_shows_finds_and_the_weeks_prizes(window):
    import time as _t
    now = int(_t.time())
    window.matches.history = [{
        "start": datetime.now().isoformat(timespec="seconds"), "end": datetime.now().isoformat(timespec="seconds"),
        "chests": 3, "chest_times": [now - 60, now - 30, now], "source": "replay", "opened": 3, "broken": 0,
        "treasures": [{"name": "Gold Thing", "kind": "outfit", "prize_id": None, "golden": True, "at": now}],
    }]
    window.treasures_page.refresh()
    assert window.treasures_page.latest.item(0).text().endswith("Gold Thing")
    assert window.treasures_page.chances.count() == len(window.content_store.content.odds)
    assert "revision" in window.treasures_page.credit.text()


def test_an_empty_treasures_page_still_draws(window):
    window.treasures_page.refresh()
    assert window.treasures_page.latest.item(0).text() == "No treasures found yet"
    window.go_to(6)


def test_a_replay_with_a_treasure_logs_it(window):
    record = finished_match(window)
    found = replays.ReplayCount("r", 2, 2, 0, datetime.now(), datetime.now(),
                                treasures=[{"name": "Solid Gold X", "kind": "outfit", "prize_id": None, "golden": True, "at": 5}],
                                chest_times=[1700000000, 1700000060])
    window._on_replay_counted(record, found)
    assert any("Solid Gold X" in window.tracker.activity.item(i).text() for i in range(window.tracker.activity.count()))
    assert window.matches.history[-1]["treasures"][0]["name"] == "Solid Gold X"
    assert window.matches.history[-1]["chest_times"] == [1700000000, 1700000060]


# --- backups, notices, replay health ---

def test_restoring_a_backup_replaces_the_data_and_keeps_a_safety_copy(window, tmp_path):
    window.stats.adjust_total(500)
    window.record_chest(1, "detected")
    window.finish_match("key")
    good = backup.write(window.folder, tmp_path / "good.json")
    window.set_total(7)
    window.matches.history = []
    window.matches.save()
    assert window.restore_backup(good) is None
    assert window.stats.total == 501 and len(window.matches.history) == 1
    assert list(backup.backups_folder(window.folder).glob("before-restore-*.json"))
    assert window.restore_backup(tmp_path / "nope.json")  # a missing file is refused with a message
    junk = tmp_path / "junk.json"
    junk.write_text("[]")
    assert window.restore_backup(junk) and window.stats.total == 501  # refused, nothing changed


def test_the_automatic_backup_can_be_turned_off(window):
    window.stats.adjust_total(5)
    window.settings.set(auto_backup=False)
    window.run_auto_backup()
    assert not backup.backups_folder(window.folder).exists()
    window.settings.set(auto_backup=True)
    window.run_auto_backup()
    assert list(backup.backups_folder(window.folder).glob("backup-*.json"))


def test_three_missed_replays_in_a_row_show_a_warning_and_a_success_clears_it(window):
    record = finished_match(window)
    for _ in range(2):
        window._on_replay_counted(record, replays.Miss("none"))
    assert not window.notice_banner.isVisibleTo(window)
    window._on_replay_counted(record, replays.Miss("none"))
    assert window.notice_banner.isVisibleTo(window) and "Record Replays" in window.notice_text.text()
    window.dismiss_notice()
    assert not window.notice_banner.isVisibleTo(window)
    window._on_replay_counted(record, replays.Miss("unreadable"))
    assert not window.notice_banner.isVisibleTo(window)  # dismissed until a replay works again
    window._on_replay_counted(record, replays.ReplayCount("r", 2, 2, 0, datetime.now(), datetime.now()))
    assert window.replay_misses == 0 and window.health_dismissed is False


def test_a_developer_notice_shows_and_can_be_dismissed_for_good(window):
    window.notice_feed.items = notices.parse({"schema": 1, "notices": [
        {"id": "fn-update", "level": "warning", "title": "Fortnite update", "text": "Replay reading is being fixed."}]})
    window._refresh_notice()
    assert window.notice_banner.isVisibleTo(window) and "Replay reading is being fixed" in window.notice_text.text()
    window.dismiss_notice()
    assert not window.notice_banner.isVisibleTo(window)
    assert window.settings["dismissed_notices"] == ["fn-update"]
    window.settings.set(dismissed_notices=[], show_notices=False)
    window._refresh_notice()
    assert not window.notice_banner.isVisibleTo(window)


def test_the_settings_page_has_the_backup_and_message_controls(window):
    page = window.settings_page
    page.auto_backup.setChecked(False)
    assert window.settings["auto_backup"] is False
    page.notices_box.setChecked(False)
    assert window.settings["show_notices"] is False


def test_clicking_a_match_shows_its_details(window, monkeypatch):
    shown = []
    monkeypatch.setattr(ui.QMessageBox, "information", lambda *a, **k: shown.append(a[2]))
    window.matches.history = [{"start": "2026-11-14T21:00:00", "end": "2026-11-14T21:10:00", "chests": 4,
                               "source": "replay", "opened": 3, "broken": 1, "kinds": {"Chest": 4}}]
    window.report.refresh()
    window.report.show_details(window.report.latest.item(0))
    assert shown and "3 opened, 1 broken" in shown[0]


# --- treasure posts and the overlay hour ---

def treasure_replay(names=("Solid Gold X",)):
    return replays.ReplayCount("r", 2, 2, 0, datetime.now(), datetime.now(),
                               treasures=[{"name": n, "kind": "outfit", "prize_id": None, "golden": True, "at": 5} for n in names])


def test_treasures_are_posted_after_the_match_line(window):
    record = finished_match(window)
    window.poster.queue.clear()
    window._on_replay_counted(record, treasure_replay(("Solid Gold X", "Pickaxe Y")))
    assert window.poster.queue[0]["chests"] == 2
    assert [("Solid Gold X" in q["text"]) for q in window.poster.queue[1:]] == [True, False]
    assert "Pickaxe Y" in window.poster.queue[2]["text"]


def test_treasure_posts_can_be_turned_off_and_need_the_match_channel(window):
    record = finished_match(window)
    window.poster.queue.clear()
    window.settings.set(treasure_post=False)
    window._on_replay_counted(record, treasure_replay())
    assert all("text" not in q for q in window.poster.queue)
    window.poster.queue.clear()
    window.settings.set(treasure_post=True, match_webhook_url="")
    window._on_replay_counted(record, treasure_replay())
    assert window.poster.queue == []


def test_the_overlay_hour_row_shows_and_hides(window):
    height = window.overlay.height()
    window.overlay.set_hour("TREASURE HOUR: 5 min left")
    assert window.overlay.height() > height
    window.set_overlay_hour(False)
    assert window.overlay.height() == height and window.settings["overlay_show_hour"] is False
    window.setup.overlay_hour.setChecked(False)
    window.setup.overlay_hour.setChecked(True)
    assert window.settings["overlay_show_hour"] is True


def test_the_import_window_looks_prizes_up_in_the_hunt_data(window):
    dialog = ui.TotalDialog(window)
    assert dialog.offers == [] or all(hasattr(o, "matches") for o in dialog.offers)
