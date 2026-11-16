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

import ui


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def window(app, tmp_path):
    main = ui.MainWindow(tmp_path, QIcon())
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
    assert window.overlay.width() == round(220 * 1.5) and window.overlay.height() == round(76 * 1.5)
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
    assert target.read_text(encoding="utf-8-sig").splitlines()[1].endswith(",1")


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

import updater as updater_module


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
