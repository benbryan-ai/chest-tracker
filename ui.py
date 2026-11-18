"""The Chest Tracker window."""

import ctypes
import logging
import sqlite3
import threading
import time
import uuid
from datetime import date, datetime, timezone
from pathlib import Path

import cv2
import numpy as np
from PySide6.QtCore import QPoint, QRect, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import (
    QAction, QColor, QDesktopServices, QGuiApplication, QIcon, QImage, QKeyEvent, QMouseEvent, QPainter, QPen, QPixmap,
    QWheelEvent,
)
from PySide6.QtWidgets import (
    QApplication, QButtonGroup, QCheckBox, QComboBox, QDialog, QFileDialog, QFrame, QGridLayout, QHBoxLayout, QLabel,
    QLineEdit, QListWidget, QListWidgetItem, QMainWindow, QMenu, QMessageBox, QPushButton, QScrollArea,
    QSizePolicy, QSlider, QSpinBox, QStackedWidget, QSystemTrayIcon, QVBoxLayout, QWidget,
)

from bot import BotRunner
from boxfilter import load_bundled
from chime import DEFAULT_VOLUME, MAX_VOLUME, MIN_VOLUME, Chime, clamp_volume
from detection import CANCELLED, PENDING, PromptMatcher
from fortnite_stats import FortniteStatsError, fetch_stats
from gamepad import is_pad_name, pad_label, shared_gamepad
from matches import MatchLog
from overlay import MAX_OPACITY, MAX_SCALE, MIN_OPACITY, MIN_SCALE, ChestOverlay, clamp
from protocol import MAX_NAME_LENGTH, format_treasure, name_problem, normalize_party, party_problem, is_webhook_url
from recap import RecapDetector
import backfill
import importer
import replays
import backup
import content
import notices
import report
import startup
import treasures
import goals
import timefmt
import updater
from adjustments import Adjustments
from marks import TreasureMarks
from version import VERSION
from settings import Settings, Stats
from store import Store
from watcher import (
    VK_F8, VK_F9, VK_F10, KeyEdge, MatchPoster, Sender, WatchEngine, capture_focused_screen, check_webhook, fortnite_focused,
    foreground_window_bounds, interact_check, selection_too_big, key_code
)
from widgets import (
    ASH, BONE, DUSK, EMBER, GOLD, GOLD_DEEP, GOLD_LIGHT, LINE, MINT, NIGHT, RAISED,
    ChestStage, GoalBar, LeaderRow, MatchMeter, StepBadge, TallyMarks,
)

log = logging.getLogger("chest-tracker")

STYLE = f"""
* {{ font-family: "Segoe UI Variable Text", "Segoe UI"; font-size: 14px; color: {BONE}; }}
QMainWindow, QDialog, #page, QScrollArea, #scrollBody {{ background: {NIGHT}; }}
QScrollArea {{ border: none; }}
#topbar {{ background: {NIGHT}; border-bottom: 1px solid {LINE}; }}
#updateBanner {{ background: {DUSK}; border-bottom: 1px solid {GOLD_DEEP}; }}
#brand {{ font-family: "Bahnschrift SemiBold Condensed"; font-size: 23px; }}
#tab {{ background: transparent; border: none; border-bottom: 3px solid transparent; border-radius: 0;
        padding: 16px 16px 13px 16px; color: {ASH}; font-size: 15px; font-weight: 500; }}
#tab:hover {{ color: {BONE}; }}
#tab:checked {{ color: {GOLD}; border-bottom-color: {GOLD}; }}
#tab:focus {{ color: {BONE}; background: {DUSK}; }}
#heading {{ font-family: "Bahnschrift SemiBold Condensed"; font-size: 36px; }}
#subheading {{ font-family: "Bahnschrift SemiBold Condensed"; font-size: 21px; color: {BONE}; }}
#muted {{ color: {ASH}; }}
#small {{ color: {ASH}; font-size: 12px; }}
#rail {{ background: transparent; }}
#statCard, #activityCard {{ background: {DUSK}; border: 1px solid {LINE}; border-radius: 12px; }}
#cardTitle {{ color: {ASH}; font-size: 12px; font-weight: 700; letter-spacing: 1px; }}
#bigNumber {{ font-family: "Bahnschrift SemiBold Condensed"; font-size: 30px; color: {GOLD}; }}
#sessionCount {{ font-family: "Bahnschrift SemiBold Condensed"; font-size: 34px; color: {BONE}; }}
#activityList {{ background: transparent; border: none; outline: none; }}
#activityList::item {{ padding: 8px 0; border-bottom: 1px solid {LINE}; }}
#activityList::item:selected {{ background: transparent; }}
#todayCount {{ font-family: "Bahnschrift SemiBold Condensed"; font-size: 54px; color: {GOLD}; }}
#notice {{ background: {DUSK}; border: 1px solid {LINE}; border-radius: 8px; }}
#pill {{ border: 1px solid {LINE}; border-radius: 14px; min-height: 18px; padding: 4px 12px; font-size: 13px; }}
QLineEdit {{ background: {NIGHT}; border: 1px solid {LINE}; border-radius: 5px; padding: 9px 11px;
             selection-background-color: {GOLD}; selection-color: {NIGHT}; }}
QLineEdit:hover {{ border-color: {ASH}; }}
QLineEdit:focus {{ border: 1px solid {GOLD}; }}
QComboBox {{ background: {NIGHT}; border: 1px solid {LINE}; border-radius: 5px; padding: 8px 10px; min-height: 20px; }}
QComboBox:hover {{ border-color: {ASH}; }}
QSpinBox {{ background: {NIGHT}; border: 1px solid {LINE}; border-radius: 5px; padding: 8px 10px; min-width: 70px;
           selection-background-color: {GOLD}; selection-color: {NIGHT}; }}
QSpinBox:hover {{ border-color: {ASH}; }}
QSpinBox:focus {{ border: 1px solid {GOLD}; }}
QSpinBox::up-button, QSpinBox::down-button {{ width: 0; border: none; }}
QComboBox:focus {{ border: 1px solid {GOLD}; }}
QComboBox::drop-down {{ border: none; width: 24px; }}
QComboBox QAbstractItemView {{ background: {DUSK}; border: 1px solid {LINE}; selection-background-color: #2E2916; }}
QPushButton {{ background: {DUSK}; border: 1px solid {LINE}; border-radius: 5px; padding: 9px 15px; font-weight: 500; }}
QPushButton:hover {{ background: {RAISED}; border-color: {ASH}; }}
QPushButton:pressed {{ background: {NIGHT}; }}
QPushButton:focus {{ border: 1px solid {GOLD}; }}
QPushButton:disabled {{ color: #6C6B67; background: {NIGHT}; border-color: {DUSK}; }}
#primary {{ background: {GOLD}; color: {NIGHT}; border: 1px solid {GOLD}; font-weight: 600; }}
#primary:hover {{ background: {GOLD_LIGHT}; border-color: {GOLD_LIGHT}; }}
#primary:pressed {{ background: {GOLD_DEEP}; border-color: {GOLD_DEEP}; color: {BONE}; }}
#primary:focus {{ border: 2px solid {BONE}; }}
#primary:disabled {{ background: #2A2A2D; color: {ASH}; border-color: #2A2A2D; }}
#capture {{ text-align: left; padding: 12px 15px; font-family: "Bahnschrift SemiBold Condensed"; font-size: 19px; }}
#capture[listening="true"] {{ border: 1px solid {GOLD}; color: {GOLD}; background: {NIGHT}; }}
#step {{ background: transparent; }}
#stepHeader {{ background: transparent; border: none; border-radius: 5px; text-align: left; padding: 8px 10px;
               font-family: "Bahnschrift SemiBold Condensed"; font-size: 21px; }}
#stepHeader:hover {{ background: {DUSK}; }}
#stepHeader:focus {{ background: {DUSK}; color: {GOLD}; }}
#disclosure {{ background: transparent; border: none; text-align: left; padding: 6px 0; color: {ASH}; }}
#disclosure:hover {{ color: {BONE}; }}
#disclosure:focus {{ color: {GOLD}; }}
#promptThumb {{ background: {NIGHT}; border: 1px solid {LINE}; border-radius: 5px; padding: 8px; }}
QListWidget {{ background: transparent; border: none; outline: none; }}
QListWidget::item {{ padding: 6px 0; border: none; }}
QListWidget::item:selected {{ background: transparent; }}
QCheckBox {{ spacing: 9px; }}
QCheckBox::indicator {{ width: 17px; height: 17px; border: 1px solid {ASH}; border-radius: 4px; background: {NIGHT}; }}
QCheckBox::indicator:checked {{ background: {GOLD}; border-color: {GOLD}; }}
QCheckBox:focus {{ color: {GOLD}; }}
QSlider::groove:horizontal {{ height: 4px; border-radius: 2px; background: {LINE}; }}
QSlider::sub-page:horizontal {{ border-radius: 2px; background: {GOLD}; }}
QSlider::handle:horizontal {{ width: 14px; height: 14px; margin: -6px 0; border-radius: 7px; background: {BONE}; border: 1px solid {GOLD_DEEP}; }}
QSlider::handle:horizontal:hover {{ background: {GOLD_LIGHT}; }}
QSlider:focus::handle:horizontal {{ border-color: {GOLD}; }}
QScrollBar:vertical {{ background: transparent; width: 10px; }}
QScrollBar::handle:vertical {{ background: {LINE}; border-radius: 5px; min-height: 30px; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}
QMenu {{ background: {DUSK}; border: 1px solid {LINE}; padding: 4px; }}
QMenu::item {{ padding: 7px 24px; border-radius: 4px; }}
QMenu::item:selected {{ background: {RAISED}; }}
QToolTip {{ background: {DUSK}; color: {BONE}; border: 1px solid {LINE}; padding: 4px; }}
"""

STATES = {
    "off": (ASH, "Paused"),
    "setup": (GOLD, "Setup isn't finished"),
    "waiting": (ASH, "Waiting for Fortnite"),
    "watching": (MINT, "Watching for chests"),
    "black": (EMBER, "Can't see the game"),
}

KEY_LABELS = {
    "BACKSPACE": "Backspace",
    "WHEELUP": "Scroll wheel up", "WHEELDOWN": "Scroll wheel down", "MOUSE1": "Left mouse",
    "MOUSE2": "Right mouse", "MOUSE3": "Middle mouse", "MOUSE4": "Mouse back", "MOUSE5": "Mouse forward",
}

MOUSE_NAMES = {
    Qt.MouseButton.LeftButton: "MOUSE1", Qt.MouseButton.RightButton: "MOUSE2",
    Qt.MouseButton.MiddleButton: "MOUSE3", Qt.MouseButton.BackButton: "MOUSE4",
    Qt.MouseButton.ForwardButton: "MOUSE5",
}


def key_label(name: str) -> str:
    if is_pad_name(name):
        return pad_label(name)
    return KEY_LABELS.get(name.upper(), name.upper())


def qt_key_name(key: int) -> str | None:
    """The settings name for a pressed Qt key, or None if it can't be used."""
    if Qt.Key.Key_A <= key <= Qt.Key.Key_Z or Qt.Key.Key_0 <= key <= Qt.Key.Key_9:
        return chr(key)
    if Qt.Key.Key_F1 <= key <= Qt.Key.Key_F12:
        number = key - Qt.Key.Key_F1 + 1
        return None if number == 8 else f"F{number}"  # F8 is used to capture the prompt
    return {
        Qt.Key.Key_Backspace: "BACKSPACE",
        Qt.Key.Key_Space: "SPACE", Qt.Key.Key_Shift: "SHIFT", Qt.Key.Key_Control: "CTRL",
        Qt.Key.Key_Alt: "ALT", Qt.Key.Key_Tab: "TAB",
    }.get(key)


def label(text: str, name: str = "", wrap: bool = False) -> QLabel:
    widget = QLabel(text)
    if name:
        widget.setObjectName(name)
    widget.setWordWrap(wrap)
    return widget


def dark_title_bar(window: QWidget) -> None:
    """Colors the Windows title bar to match the app. Older Windows just ignores this."""
    handle = int(window.winId())
    dwm = ctypes.windll.dwmapi
    enabled = ctypes.c_int(1)
    dwm.DwmSetWindowAttribute(handle, 20, ctypes.byref(enabled), ctypes.sizeof(enabled))
    color = QColor(NIGHT)
    caption = ctypes.c_int(color.red() | color.green() << 8 | color.blue() << 16)
    dwm.DwmSetWindowAttribute(handle, 35, ctypes.byref(caption), ctypes.sizeof(caption))


def scroll_page(margins: tuple[int, int, int, int] = (40, 30, 40, 34)) -> tuple[QScrollArea, QVBoxLayout]:
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    body = QWidget()
    body.setObjectName("scrollBody")
    scroll.setWidget(body)
    layout = QVBoxLayout(body)
    layout.setContentsMargins(*margins)
    layout.setSpacing(14)
    return scroll, layout


class Pill(QLabel):
    def __init__(self):
        super().__init__()
        self.setObjectName("pill")
        self.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)

    def show_state(self, color: str, text: str) -> None:
        self.setText(f'<span style="color:{color}">●</span>&nbsp; {text}')
        self.setAccessibleName(text)


class KeyCapture(QPushButton):
    """Click it to choose the key or input used for an action."""

    captured = Signal(str)

    def __init__(self, keyboard_only: bool = False, action_label: str = "interact key"):
        super().__init__()
        self.setObjectName("capture")
        self.current = "E"
        self.listening = False
        self.keyboard_only = keyboard_only
        self.action_label = action_label
        self.pad_timer = QTimer(self)
        self.pad_timer.setInterval(30)
        self.pad_timer.timeout.connect(self._check_pad)
        self.clicked.connect(self._listen)
        self._refresh()

    def set_key(self, name: str) -> None:
        self.current = name
        self._refresh()

    def _refresh(self) -> None:
        controller = "" if self.keyboard_only else " or controller button"
        prompt = f"Press your {self.action_label}{controller} (Esc cancels)"
        self.setText(prompt if self.listening else key_label(self.current))
        self.setProperty("listening", self.listening)
        self.style().unpolish(self)
        self.style().polish(self)

    def _listen(self) -> None:
        self.listening = True
        self.grabKeyboard()
        if not self.keyboard_only:
            self.grabMouse()
            try:
                shared_gamepad().take_any()  # forget presses from before this click
                self.pad_timer.start()
            except Exception as error:
                log.warning("Controller input unavailable: %s", error)
        self._refresh()

    def _check_pad(self) -> None:
        try:
            name = shared_gamepad().take_any()
        except Exception:
            self.pad_timer.stop()
            return
        if name:
            self._finish(name)

    def _finish(self, name: str | None) -> None:
        self.listening = False
        self.pad_timer.stop()
        self.releaseKeyboard()
        if not self.keyboard_only:
            self.releaseMouse()
        if name:
            self.current = name
            self.captured.emit(name)
        self._refresh()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if not self.listening:
            super().keyPressEvent(event)
        elif event.key() == Qt.Key.Key_Escape:
            self._finish(None)
        else:
            name = qt_key_name(event.key())
            if name:
                self._finish(name)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if self.listening:
            if self.keyboard_only:
                event.accept()
                return
            self._finish(MOUSE_NAMES.get(event.button()))
        else:
            super().mousePressEvent(event)

    def wheelEvent(self, event: QWheelEvent) -> None:
        if self.listening and event.angleDelta().y():
            if self.keyboard_only:
                event.accept()
                return
            self._finish("WHEELUP" if event.angleDelta().y() > 0 else "WHEELDOWN")
        else:
            super().wheelEvent(event)


class SelectionView(QWidget):
    """Shows a screenshot and lets you drag a box. Big boxes zoom in so tiny text is easy to pick."""

    selected = Signal(object)  # (x, y, width, height) in image pixels, or None

    def __init__(self, image: np.ndarray):
        super().__init__()
        self.image = image
        height, width = image.shape[:2]
        self.qimage = QImage(image.data, width, height, image.strides[0], QImage.Format.Format_RGB32).copy()
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setMinimumSize(640, 360)
        self.reset()

    def reset(self) -> None:
        self.view = QRect(0, 0, self.qimage.width(), self.qimage.height())
        self.selection: QRect | None = None
        self.drag_start: QPoint | None = None
        self.drag_now: QPoint | None = None
        self.selected.emit(None)
        self.update()

    def target(self) -> QRect:
        scale = min(self.width() / self.view.width(), self.height() / self.view.height())
        width, height = int(self.view.width() * scale), int(self.view.height() * scale)
        return QRect((self.width() - width) // 2, (self.height() - height) // 2, width, height)

    def to_image(self, point: QPoint) -> QPoint:
        target = self.target()
        x = self.view.x() + (point.x() - target.x()) * self.view.width() / target.width()
        y = self.view.y() + (point.y() - target.y()) * self.view.height() / target.height()
        return QPoint(int(x), int(y))

    def to_widget(self, rect: QRect) -> QRect:
        target = self.target()
        scale = target.width() / self.view.width()
        return QRect(
            target.x() + int((rect.x() - self.view.x()) * scale),
            target.y() + int((rect.y() - self.view.y()) * scale),
            int(rect.width() * scale),
            int(rect.height() * scale),
        )

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(DUSK))
        painter.drawImage(self.target(), self.qimage, self.view)
        painter.setPen(QPen(QColor(GOLD), 2))
        if self.drag_start and self.drag_now:
            painter.drawRect(QRect(self.drag_start, self.drag_now).normalized())
        elif self.selection:
            painter.drawRect(self.to_widget(self.selection))

    def mousePressEvent(self, event: QMouseEvent) -> None:
        self.drag_start = self.drag_now = event.position().toPoint()
        self.update()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        self.drag_now = event.position().toPoint()
        self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        start, end = self.to_image(self.drag_start), self.to_image(event.position().toPoint())
        self.drag_start = self.drag_now = None
        box = QRect(start, end).normalized().intersected(self.qimage.rect())
        if box.width() < 6 or box.height() < 6:
            self.update()
            return
        if selection_too_big(box.width(), box.height(), self.qimage.height()):
            margin = 12
            self.view = box.adjusted(-margin, -margin, margin, margin).intersected(self.qimage.rect())
            self.selection = None
            self.selected.emit(None)
        else:
            self.selection = box
            self.selected.emit((box.x(), box.y(), box.width(), box.height()))
        self.update()


class TotalDialog(QDialog):
    scanned = Signal(object)
    scan_progress = Signal(int, int)

    """Change the lifetime total by hand, undo earlier changes, or bring numbers in from another tracker."""

    def __init__(self, window: "MainWindow"):
        super().__init__(window)
        self.window_ = window
        self.setWindowTitle("Your total")
        self.setMinimumSize(520, 420)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 20, 24, 20)
        outer.setSpacing(10)
        outer.addWidget(label("Chests in total", "heading"))
        self.current = label("", "muted")
        outer.addWidget(self.current)
        outer.addWidget(label(
            "Type what your total should be. The difference is kept in the list below, so you can undo it. "
            "Today's and this session's counts don't change.", "muted", wrap=True,
        ))
        row = QHBoxLayout()
        self.total_edit = QLineEdit()
        self.total_edit.setPlaceholderText("New total")
        self.total_edit.returnPressed.connect(self.apply_total)
        row.addWidget(self.total_edit, 1)
        self.apply_button = QPushButton("Set total")
        self.apply_button.setObjectName("primary")
        self.apply_button.clicked.connect(self.apply_total)
        row.addWidget(self.apply_button)
        outer.addLayout(row)
        self.status = label("", "small", wrap=True)
        outer.addWidget(self.status)
        outer.addWidget(label("Changes you made", "subheading"))
        self.history = QListWidget()
        self.history.setObjectName("activityList")
        self.history.setMaximumHeight(120)
        outer.addWidget(self.history)
        self.undo = QPushButton("Undo selected change")
        self.undo.clicked.connect(self.undo_selected)
        outer.addWidget(self.undo)
        outer.addWidget(label("Count my past replays", "subheading"))
        outer.addWidget(label(
            "Reads the replays Fortnite has saved on this PC, from the season start date on. Matches the app "
            "never saw are added, and matches it counted from the screen are corrected. Counts from before your "
            "oldest replay stay as they are. You'll see the result and confirm before anything changes.",
            "muted", wrap=True,
        ))
        replay_row = QHBoxLayout()
        self.season_start = QLineEdit(window.settings["season_start"])
        self.season_start.setPlaceholderText("Season start, YYYY-MM-DD")
        self.season_start.setToolTip("Replays from before this date are ignored.")
        replay_row.addWidget(self.season_start, 1)
        self.scan_button = QPushButton("Count my past replays")
        self.scan_button.clicked.connect(self.start_scan)
        replay_row.addWidget(self.scan_button)
        outer.addLayout(replay_row)
        self.scanned.connect(self._scan_done)
        self.scan_progress.connect(lambda done, total: self.status.setText(f"Reading replays... {done} of {total}"))
        outer.addWidget(label("Bring in numbers from another tracker", "subheading"))
        def lookup(prize_id: str):
            prize = window.content_store.content.find_prize(prize_id)
            return (prize.name, prize.kind) if prize else None

        self.offers = importer.find_offers(lookup=lookup)
        self.offer_box = QComboBox()
        for offer in self.offers:
            self.offer_box.addItem(
                f"{offer.source} ({offer.label}): {offer.chests:,} chests, {len(offer.matches):,} matches", offer
            )
        outer.addWidget(self.offer_box)
        self.import_button = QPushButton("Import")
        self.import_button.clicked.connect(self.import_selected)
        outer.addWidget(self.import_button)
        self.import_note = label(
            "" if self.offers else
            "No ChestCounter or chest-tracker data was found on this PC (looked in your AppData folder).",
            "muted", wrap=True,
        )
        outer.addWidget(self.import_note)
        self.import_button.setEnabled(bool(self.offers))
        self.offer_box.setVisible(bool(self.offers))
        self.refresh()

    def refresh(self) -> None:
        total = self.window_.stats.total
        self.current.setText(f"Your total is {total:,}.")
        self.total_edit.setText(str(total))
        self.history.clear()
        for entry in reversed(self.window_.adjustments.entries):
            item = QListWidgetItem(f"{entry['chests']:+,}   {entry['note']}   ({entry['when'].replace('T', ' ')})")
            item.setData(Qt.ItemDataRole.UserRole, entry["id"])
            self.history.addItem(item)
        if not self.window_.adjustments.entries:
            self.history.addItem("Nothing changed by hand yet.")
        self.undo.setEnabled(bool(self.window_.adjustments.entries))

    def apply_total(self) -> None:
        text = self.total_edit.text().strip().replace(",", "")
        if not text.isdigit() or len(text) > 9:
            self.status.setText("Type a whole number, 0 or more.")
            return
        change = self.window_.set_total(int(text))
        self.status.setText("That's already your total." if change == 0 else f"Changed by {change:+,}.")
        self.refresh()

    def undo_selected(self) -> None:
        item = self.history.currentItem()
        entry_id = item.data(Qt.ItemDataRole.UserRole) if item else None
        if not entry_id:
            self.status.setText("Pick a change in the list first.")
            return
        self.window_.undo_adjustment(entry_id)
        self.status.setText("Undone.")
        self.refresh()

    def start_scan(self) -> None:
        try:
            since = datetime.fromisoformat(self.season_start.text().strip())
        except ValueError:
            self.status.setText("Type the season start as a date like 2026-11-01.")
            return
        scanner = replays.find_scanner()
        if scanner is None:
            self.status.setText("The replay reader isn't part of this build, so past replays can't be counted.")
            return
        self.window_.settings.set(season_start=since.date().isoformat())
        folder = Path(self.window_.settings["replay_folder"] or replays.default_replay_folder())
        if not folder.is_dir():
            self.status.setText(f"No replay folder found at {folder}. Is Fortnite's Record Replays setting on?")
            return
        self.scan_button.setEnabled(False)
        self.status.setText("Reading replays...")

        def work() -> None:
            found = []
            try:
                found = backfill.scan_folder(scanner, folder, since, self.scan_progress.emit)
            except Exception:
                log.exception("Reading past replays failed")
            self.scanned.emit((since, found))

        threading.Thread(target=work, daemon=True, name="replay-backfill").start()

    def _scan_done(self, result) -> None:
        since, found = result
        self.scan_button.setEnabled(True)
        plan = backfill.make_plan(found, self.window_.matches.history, since)
        if plan.replays_in_season == 0:
            self.status.setText("No readable replays since that date. Finished matches only; one still recording is skipped.")
            return
        if plan.nothing_to_do:
            self.status.setText(f"{plan.replays_in_season} replays checked. Everything is already counted from them.")
            return
        total = self.window_.stats.total
        answer = QMessageBox.question(
            self, "Count past replays",
            f"Found {plan.replays_in_season} replays since {since.date().isoformat()}.\n\n"
            f"New matches added: {len(plan.new)}\n"
            f"Matches corrected from the replay: {len(plan.replaced) - plan.refreshed}\n"
            f"Matches that only get chest types and treasures filled in: {plan.refreshed}\n"
            f"Already counted from the replay: {plan.already}\n\n"
            f"Your total changes by {plan.total_change:+,}, from {total:,} to {max(0, total + plan.total_change):,}.\n"
            "Matches without a replay stay as they are. You can undo this afterwards.\n\nApply it?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            self.status.setText("Nothing changed.")
            return
        change = self.window_.apply_backfill(plan)
        self.status.setText(f"Done: total changed by {change:+,}.")
        self.refresh()

    def import_selected(self) -> None:
        offer = self.offer_box.currentData()
        if offer is None:
            return
        if self.window_.adjustments.has_import(offer.note):
            self.status.setText("That is already imported. Undo it in the list first to import again.")
            return
        added = self.window_.apply_import(offer)
        self.status.setText(f"Added {offer.chests:,} chests and {added:,} matches from {offer.source}.")
        self.refresh()


class PromptDialog(QDialog):
    """Guides the player through saving a picture of the SEARCH prompt."""

    def __init__(self, parent: QWidget, templates_dir: Path, search_area: list[float]):
        super().__init__(parent)
        self.templates_dir = templates_dir
        self.search_area = search_area
        self.setWindowTitle("Set up the chest prompt")
        self.setMinimumSize(560, 340)
        self.outer = QVBoxLayout(self)
        self.outer.setContentsMargins(28, 24, 28, 24)
        self.outer.setSpacing(14)
        self.heading = label("Capture the prompt", "heading")
        self.outer.addWidget(self.heading)
        self.instructions = label(
            "1.  Open Fortnite in <b>Windowed Fullscreen</b>.<br>"
            "2.  Walk up to a chest so the <b>SEARCH</b> prompt shows.<br>"
            "3.  Press <b>F8</b> while still in the game.",
            wrap=True,
        )
        self.outer.addWidget(self.instructions)
        self.status = label("Waiting for F8.", "muted", wrap=True)
        self.outer.addWidget(self.status)
        self.outer.addStretch(1)
        self.footer = QHBoxLayout()
        self.footer.addStretch(1)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        self.footer.addWidget(cancel)
        self.outer.addLayout(self.footer)

        self.hotkey = KeyEdge(VK_F8)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._poll)
        self.timer.start(30)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        dark_title_bar(self)

    def done(self, result: int) -> None:
        # Cancel, Save or the window's X: either way, stop watching for F8. Otherwise the
        # hidden dialog stays alive and pops back up the next time F8 is pressed in game.
        self.timer.stop()
        super().done(result)

    def _poll(self) -> None:
        if not self.isVisible() or not self.hotkey.pressed():
            return
        if not fortnite_focused():
            self.status.setText("Fortnite wasn't the active window. Click into the game and press F8 again.")
            return
        self.timer.stop()
        self.show_selection(capture_focused_screen())
        self.raise_()
        self.activateWindow()

    def show_selection(self, image: np.ndarray) -> None:
        self.image = image
        self.selection = None
        self.heading.setText("Select the word SEARCH")
        self.instructions.setText(
            "Drag a box around the prompt to zoom in, then drag a tight box around only the word "
            "<b>SEARCH</b>. Leave out the chest, your character and the key icon."
        )
        self.status.hide()
        self.view = SelectionView(image)
        self.view.selected.connect(self._selected)
        self.outer.insertWidget(2, self.view, 1)
        self.outer.setStretch(4, 0)  # the empty space under the instructions goes to the screenshot

        self.preview = QLabel()
        self.footer.insertWidget(0, self.preview)
        again = QPushButton("Start over")
        again.clicked.connect(self.view.reset)
        self.footer.insertWidget(2, again)
        self.save = QPushButton("Save prompt")
        self.save.setObjectName("primary")
        self.save.setEnabled(False)
        self.save.clicked.connect(self._save)
        self.footer.addWidget(self.save)
        self.showMaximized()

    def _selected(self, box) -> None:
        self.selection = box
        self.save.setEnabled(box is not None)
        if box is None:
            self.preview.clear()
            return
        x, y, width, height = box
        rect = QRect(x, y, width, height)
        self.preview.setPixmap(QPixmap.fromImage(self.view.qimage.copy(rect)).scaledToHeight(
            min(44, height * 3), Qt.TransformationMode.FastTransformation
        ))

    def _save(self) -> None:
        x, y, width, height = self.selection
        screen_height, screen_width = self.image.shape[:2]
        left, top, right, bottom = self.search_area
        if (
            x < left * screen_width or x + width > right * screen_width
            or y < top * screen_height or y + height > bottom * screen_height
        ):
            QMessageBox.warning(
                self, "Outside the watched area",
                "That spot is too close to the screen edge for the app to watch. Select the prompt near the center.",
            )
            return
        gray = cv2.cvtColor(self.image[y:y + height, x:x + width], cv2.COLOR_BGRA2GRAY)
        self.templates_dir.mkdir(exist_ok=True)
        numbers = [int(p.stem.split("_")[-1]) for p in self.templates_dir.glob("chest_*.png")]
        cv2.imwrite(str(self.templates_dir / f"chest_{max(numbers, default=0) + 1}.png"), gray)
        self.accept()


class TrackerPage(QWidget):
    def __init__(self, window: "MainWindow"):
        super().__init__()
        self.setObjectName("page")
        self.clock_format = window.settings["clock_format"]
        columns = QHBoxLayout(self)
        columns.setContentsMargins(24, 16, 24, 20)
        columns.setSpacing(16)

        left = QVBoxLayout()
        left.setContentsMargins(0, 0, 0, 0)
        left.setSpacing(12)
        self.notice_frame = QFrame()
        self.notice_frame.setObjectName("notice")
        notice_row = QHBoxLayout(self.notice_frame)
        notice_row.setContentsMargins(16, 10, 12, 10)
        self.notice = label("", wrap=True)
        notice_row.addWidget(self.notice, 1)
        finish = QPushButton("Finish setup")
        finish.setObjectName("primary")
        finish.clicked.connect(lambda: window.go_to(1))
        notice_row.addWidget(finish)
        left.addWidget(self.notice_frame)

        left.addWidget(label("Your hunt at a glance", "heading"))
        subtitle_row = QHBoxLayout()
        subtitle_row.addWidget(label("Your totals and recent activity, in one place.", "muted"), 1)
        self.edit_total = QPushButton("Edit total...")
        self.edit_total.setToolTip("Change your total, undo a change, or import from ChestCounter or chest-tracker.")
        self.edit_total.clicked.connect(window.open_total_dialog)
        subtitle_row.addWidget(self.edit_total)
        left.addLayout(subtitle_row)
        self.stage = ChestStage()
        left.addWidget(self.stage, 1)
        columns.addLayout(left, 1)

        rail = QFrame()
        rail.setObjectName("rail")
        rail.setFixedWidth(360)
        side = QVBoxLayout(rail)
        side.setContentsMargins(0, 0, 0, 0)
        side.setSpacing(10)

        today_card = QFrame()
        today_card.setObjectName("statCard")
        today_layout = QVBoxLayout(today_card)
        today_layout.setContentsMargins(18, 15, 18, 14)
        today_layout.setSpacing(5)
        today_layout.addWidget(label("TODAY", "cardTitle"))
        today_row = QHBoxLayout()
        today_row.setSpacing(8)
        self.today = label("0", "todayCount")
        today_row.addWidget(self.today)
        today_row.addStretch(1)
        self.tally = TallyMarks()
        self.tally.setFixedWidth(142)
        today_row.addWidget(self.tally, 0, Qt.AlignmentFlag.AlignVCenter)
        today_layout.addLayout(today_row)
        today_layout.addWidget(label("chests opened today", "muted"))
        self.day_goal = label("", "small")
        self.day_bar = GoalBar()
        today_layout.addWidget(self.day_goal)
        today_layout.addWidget(self.day_bar)
        self.day_goal.hide()
        self.day_bar.hide()
        side.addWidget(today_card)

        session_card = QFrame()
        session_card.setObjectName("statCard")
        session_layout = QVBoxLayout(session_card)
        session_layout.setContentsMargins(18, 14, 18, 13)
        session_layout.setSpacing(3)
        session_layout.addWidget(label("THIS SESSION", "cardTitle"))
        session_row = QHBoxLayout()
        self.session = label("0", "sessionCount")
        session_row.addWidget(self.session)
        session_row.addWidget(label("chests since launch", "muted"), 0, Qt.AlignmentFlag.AlignBottom)
        session_row.addStretch(1)
        session_layout.addLayout(session_row)
        self.session_matches = label("No matches finished yet this session", "small", wrap=True)
        session_layout.addWidget(self.session_matches)
        side.addWidget(session_card)

        match_card = QFrame()
        match_card.setObjectName("statCard")
        match_layout = QVBoxLayout(match_card)
        match_layout.setContentsMargins(18, 14, 18, 13)
        match_layout.setSpacing(3)
        match_layout.addWidget(label("THIS MATCH", "cardTitle"))
        match_row = QHBoxLayout()
        self.match_count = label("0", "sessionCount")
        match_row.addWidget(self.match_count)
        match_row.addWidget(label("chests this match", "muted"), 0, Qt.AlignmentFlag.AlignBottom)
        match_row.addStretch(1)
        match_layout.addLayout(match_row)
        self.match_goal = label("", "small")
        self.match_bar = GoalBar()
        match_layout.addWidget(self.match_goal)
        match_layout.addWidget(self.match_bar)
        self.match_goal.hide()
        self.match_bar.hide()
        self.last_match = label("", "small", wrap=True)
        match_layout.addWidget(self.last_match)
        self.match_summary = label("No finished matches yet", "small", wrap=True)
        match_layout.addWidget(self.match_summary)
        match_buttons = QHBoxLayout()
        self.new_match = QPushButton("New match")
        self.new_match.setToolTip("Closes this match and starts the next. The new-match key does the same.")
        self.new_match.clicked.connect(lambda: window.finish_match("button"))
        match_buttons.addWidget(self.new_match)
        self.export_matches = QPushButton("Export history")
        self.export_matches.clicked.connect(window.export_match_history)
        match_buttons.addWidget(self.export_matches)
        match_layout.addLayout(match_buttons)
        side.addWidget(match_card)

        activity_card = QFrame()
        activity_card.setObjectName("activityCard")
        activity_layout = QVBoxLayout(activity_card)
        activity_layout.setContentsMargins(18, 14, 18, 10)
        activity_layout.setSpacing(4)
        activity_layout.addWidget(label("Recent activity", "subheading"))
        activity_layout.addWidget(label("Latest tracker events", "small"))
        self.activity = QListWidget()
        self.activity.setObjectName("activityList")
        self.activity.setSelectionMode(QListWidget.SelectionMode.NoSelection)
        self.activity.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.activity.setWordWrap(True)
        activity_layout.addWidget(self.activity, 1)
        self.empty = QListWidgetItem("Open a chest in Fortnite and it appears here.")
        self.empty.setForeground(QColor(ASH))
        self.activity.addItem(self.empty)
        side.addWidget(activity_card, 1)

        actions = QHBoxLayout()
        self.remove = QPushButton("Remove last chest")
        self.remove.setToolTip("Counted one by mistake? Press your undo key while Fortnite is focused.")
        self.remove.clicked.connect(lambda: window.record_chest(-1, "manual"))
        actions.addWidget(self.remove, 1)
        self.pause = QPushButton("Pause tracking")
        self.pause.setObjectName("primary")
        self.pause.clicked.connect(window.toggle_pause)
        actions.addWidget(self.pause)
        side.addLayout(actions)
        columns.addWidget(rail)

    def show_stats(self, stats: Stats) -> None:
        self.today.setText(f"{stats.today:,}")
        self.tally.set_count(stats.today)
        self.session.setText(f"{stats.session:,}")
        self.remove.setEnabled(stats.total > 0)

    def show_goals(self, day_goal: int, today: int, streak: int, match_goal: int, match: int) -> None:
        """The progress bars under today's and this match's counts. They stay hidden with no goal set."""
        for goal, text, bar, line in (
            (day_goal, today, self.day_bar, self.day_goal),
            (match_goal, match, self.match_bar, self.match_goal),
        ):
            bar.setVisible(goal > 0)
            line.setVisible(goal > 0)
            bar.set_value(goals.fraction(text, goal))
        shown = goals.progress_text(today, day_goal, "today")
        if day_goal and streak > 1:
            shown += f" · {streak}-day streak"
        self.day_goal.setText(shown)
        self.match_goal.setText(goals.progress_text(match, match_goal, "chests"))

    def show_matches(self, matches: MatchLog) -> None:
        self.match_count.setText(f"{matches.current:,}")
        self.new_match.setEnabled(matches.current > 0)
        self.export_matches.setEnabled(bool(matches.history))
        last = matches.last_chests()
        self.last_match.setText("" if last is None else f"Last match: {last:,} {'chest' if last == 1 else 'chests'}")
        done = matches.session_matches
        self.session_matches.setText(
            "No matches finished yet this session" if not done
            else f"{done:,} {'match' if done == 1 else 'matches'} finished this session"
        )
        summary = matches.stats()
        if summary is None:
            self.match_summary.setText("No finished matches yet")
        else:
            self.match_summary.setText(
                f"{summary.matches:,} {'match' if summary.matches == 1 else 'matches'} · average {summary.average:.1f} · "
                f"median {summary.median:g} · best {summary.best:,}"
            )

    def log(self, text: str, color: str = BONE) -> None:
        if self.empty is not None:
            self.activity.takeItem(self.activity.row(self.empty))
            self.empty = None
        top = self.activity.item(0)
        line = f"{timefmt.format_time(datetime.now(), self.clock_format)}   {text}"
        if top and top.text() == line:
            return
        item = QListWidgetItem(line)
        item.setForeground(QColor(color))
        self.activity.insertItem(0, item)
        while self.activity.count() > 100:
            self.activity.takeItem(self.activity.count() - 1)


class Step(QWidget):
    """One numbered setup step. Its body opens when the header is clicked."""

    opened = Signal(object)

    def __init__(self, number: int, title: str, last: bool = False):
        super().__init__()
        self.setObjectName("step")
        self.last = last
        self.title = title
        grid = QVBoxLayout(self)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(0)
        row = QHBoxLayout()
        row.setSpacing(8)
        self.badge = StepBadge(number)
        row.addWidget(self.badge)
        self.header = QPushButton(title)
        self.header.setObjectName("stepHeader")
        self.header.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.header.clicked.connect(lambda: self.opened.emit(self))
        row.addWidget(self.header, 1)
        self.summary = label("", "muted")
        self.summary.setTextFormat(Qt.TextFormat.PlainText)
        row.addWidget(self.summary)
        grid.addLayout(row)
        self.body = QWidget()
        self.content = QVBoxLayout(self.body)
        self.content.setContentsMargins(46, 6, 2, 14)
        self.content.setSpacing(10)
        grid.addWidget(self.body)
        grid.addSpacing(14)
        self.done = False
        self.set_open(False)

    def set_open(self, is_open: bool) -> None:
        self.is_open = is_open
        self.body.setVisible(is_open)
        self.summary.setVisible(not is_open)
        self.badge.set_status(self.done, is_open)

    def set_done(self, done: bool, summary: str) -> None:
        self.done = done
        self.summary.setText(summary if done else "Not done yet")
        self.badge.set_status(done, self.is_open)

    def paintEvent(self, event) -> None:
        if self.last:
            return
        p = QPainter(self)
        p.setPen(QPen(QColor(LINE), 2))
        p.drawLine(15, 34, 15, self.height())


UPDATE_MODES = (
    ("notify", "Tell me when there's a new version"),
    ("auto", "Install new versions automatically"),
    ("off", "Don't check for updates"),
)
UPDATE_CHECK_HOURS = 6


class SetupPage(QWidget):
    webhook_result = Signal(bool, str)

    def __init__(self, window: "MainWindow"):
        super().__init__()
        self.window_ = window
        settings = window.settings
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll, layout = scroll_page()
        outer.addWidget(scroll)
        layout.setSpacing(4)
        layout.addWidget(label("Setup", "heading"))
        layout.addWidget(label("Save a chest prompt to start. Name and Discord sharing are optional.", "muted"))
        layout.addSpacing(14)

        self.name_step = Step(1, "Your name")
        self.name_step.content.addWidget(label(
            "Optional. This is how you appear on your group's leaderboard if you connect Discord.",
            "muted", wrap=True,
        ))
        self.name = QLineEdit(settings["player_name"])
        self.name.setPlaceholderText("Player name")
        self.name.setMaxLength(MAX_NAME_LENGTH)
        self.name.editingFinished.connect(self._save_name)
        self.name_step.content.addWidget(self.name)
        self.name_status = label("", "small", wrap=True)
        self.name_status.hide()
        self.name_step.content.addWidget(self.name_status)

        self.webhook_step = Step(2, "Discord channel link")
        self.webhook_step.content.addWidget(label(
            "Optional. Without a webhook, counts stay on this PC. To share counts, paste the webhook "
            "URL your group shares. In Discord, open the channel's Edit Channel, "
            "then Integrations, then Webhooks. Keep it within your group, because anyone who has it "
            "can post to the channel.",
            "muted", wrap=True,
        ))
        row = QHBoxLayout()
        self.webhook = QLineEdit(settings["webhook_url"])
        self.webhook.setPlaceholderText("https://discord.com/api/webhooks/...")
        self.webhook.setEchoMode(QLineEdit.EchoMode.PasswordEchoOnEdit)
        self.webhook.editingFinished.connect(self._save_webhook)
        row.addWidget(self.webhook, 1)
        self.test = QPushButton("Check link")
        self.test.clicked.connect(self._test_webhook)
        row.addWidget(self.test)
        self.webhook_step.content.addLayout(row)
        self.webhook_status = label("", "small", wrap=True)
        self.webhook_status.hide()
        self.webhook_step.content.addWidget(self.webhook_status)
        self.webhook_result.connect(self._show_webhook_result)

        self.webhook_step.content.addWidget(label("Match reports (optional)", "small"))
        self.webhook_step.content.addWidget(label(
            "Posts one line per finished match, for example \"14 chests this match\", to a second "
            "webhook. Point it at a different channel than the one above if you like.",
            "muted", wrap=True,
        ))
        self.match_webhook = QLineEdit(settings["match_webhook_url"])
        self.match_webhook.setPlaceholderText("https://discord.com/api/webhooks/... (match reports channel)")
        self.match_webhook.setEchoMode(QLineEdit.EchoMode.PasswordEchoOnEdit)
        self.match_webhook.editingFinished.connect(self._save_match_webhook)
        self.webhook_step.content.addWidget(self.match_webhook)
        self.match_post = QCheckBox("Post each match to Discord")
        self.match_post.setToolTip("Turn this off to keep your matches to yourself.")
        self.match_post.setChecked(bool(settings["match_post"]))
        self.match_post.toggled.connect(self._save_match_post)
        self.webhook_step.content.addWidget(self.match_post)
        self.treasure_post = QCheckBox("Also post treasures I find")
        self.treasure_post.setToolTip("A line like 'Found a treasure: Solid Gold ...' in the same channel. Needs replay counting.")
        self.treasure_post.setChecked(bool(settings["treasure_post"]))
        self.treasure_post.toggled.connect(lambda on: self.window_.settings.set(treasure_post=on))
        self.webhook_step.content.addWidget(self.treasure_post)
        self.webhook_step.content.addWidget(label(
            "Playing with friends? Everyone enters the same party code (3 to 12 letters or numbers) "
            "and the bot posts one group game report. Leave it empty if you play solo.",
            "muted", wrap=True,
        ))
        self.party = QLineEdit(settings["party_code"])
        self.party.setPlaceholderText("Party code, for example SQUAD42")
        self.party.setMaxLength(24)
        self.party.editingFinished.connect(self._save_party)
        self.webhook_step.content.addWidget(self.party)
        self.match_status = label("", "small", wrap=True)
        self.match_status.hide()
        self.webhook_step.content.addWidget(self.match_status)

        self.key_step = Step(3, "Interact key")
        self.key_step.content.addWidget(label(
            "Click the button, then press the key or scroll the wheel the way you open chests in Fortnite.",
            "muted", wrap=True,
        ))
        self.capture = KeyCapture()
        self.capture.set_key(settings["interact_keys"][0])
        self.capture.captured.connect(self._save_key)
        self.key_step.content.addWidget(self.capture)
        self.key_step.content.addWidget(label(
            "Click to choose an undo key. It works only while Fortnite is focused; F10 is the default.",
            "muted", wrap=True,
        ))
        self.remove_capture = KeyCapture(keyboard_only=True, action_label="undo key")
        self.remove_capture.set_key(settings["remove_key"])
        self.remove_capture.captured.connect(self._save_remove_key)
        self.key_step.content.addWidget(self.remove_capture)
        self.key_step.content.addWidget(label(
            "Click to choose a pause key. Press it in Fortnite to stop counting, and press it again to resume; "
            "F9 is the default.",
            "muted", wrap=True,
        ))
        self.pause_capture = KeyCapture(keyboard_only=True, action_label="pause key")
        self.pause_capture.set_key(settings["pause_key"])
        self.pause_capture.captured.connect(self._save_pause_key)
        self.key_step.content.addWidget(self.pause_capture)
        self.key_step.content.addWidget(label(
            "Click to choose a new-match key. Press it in Fortnite to start counting a new match "
            "if the app missed the end-of-match screen; F8 is the default.",
            "muted", wrap=True,
        ))
        self.match_capture = KeyCapture(keyboard_only=True, action_label="new-match key")
        self.match_capture.set_key(settings["match_key"])
        self.match_capture.captured.connect(self._save_match_key)
        self.key_step.content.addWidget(self.match_capture)

        self.prompt_step = Step(4, "Chest prompt", last=True)
        self.prompt_step.content.addWidget(label(
            "A small picture of the word SEARCH, so the app recognizes the prompt. Set it up again if "
            "you change your resolution or HUD scale.",
            "muted", wrap=True,
        ))
        self.gallery = QHBoxLayout()
        self.gallery.setSpacing(10)
        self.prompt_step.content.addLayout(self.gallery)
        add_row = QHBoxLayout()
        self.add_prompt = QPushButton("Set up prompt")
        self.add_prompt.setObjectName("primary")
        self.add_prompt.clicked.connect(self._calibrate)
        add_row.addWidget(self.add_prompt)
        add_row.addStretch(1)
        self.prompt_step.content.addLayout(add_row)
        self.prompt_step.content.addSpacing(8)
        self.prompt_step.content.addWidget(label("Live match", "subheading"))
        self.prompt_step.content.addWidget(label(
            "Look at a chest in Fortnite. The live bar should reach the marker. Drag the marker to "
            "change the required match: lower values are more permissive, while higher values are stricter.",
            "muted", wrap=True,
        ))
        self.meter = MatchMeter(settings["match_threshold"])
        self.meter.threshold_changed.connect(self._save_threshold)
        self.prompt_step.content.addWidget(self.meter)
        self.score_text = label("Not in game", "small")
        self.prompt_step.content.addWidget(self.score_text)

        self.steps = [self.name_step, self.webhook_step, self.key_step, self.prompt_step]
        for step in self.steps:
            step.opened.connect(self._open_step)
            layout.addWidget(step)

        layout.addSpacing(12)
        layout.addWidget(label("In-game overlay", "subheading"))
        layout.addWidget(label(
            "Show your live chest count over Fortnite. Turn on positioning to drag the badge somewhere "
            "that does not cover your HUD, then finish positioning before you play.",
            "muted", wrap=True,
        ))
        overlay_row = QHBoxLayout()
        self.overlay_enabled = QCheckBox("Show the chest count over Fortnite")
        self.overlay_enabled.setChecked(settings["overlay_enabled"])
        self.overlay_enabled.toggled.connect(window.set_overlay_enabled)
        overlay_row.addWidget(self.overlay_enabled, 1)
        self.overlay_position = QPushButton("Set overlay position")
        self.overlay_position.clicked.connect(self._toggle_overlay_position)
        overlay_row.addWidget(self.overlay_position)
        layout.addLayout(overlay_row)
        self.overlay_match = QCheckBox("Also show this match's chest count")
        self.overlay_match.setChecked(settings["overlay_show_match"])
        self.overlay_match.toggled.connect(window.set_overlay_match)
        layout.addWidget(self.overlay_match)
        self.overlay_hour = QCheckBox("Show the next Treasure Hour (during the treasure hunt)")
        self.overlay_hour.setChecked(settings["overlay_show_hour"])
        self.overlay_hour.toggled.connect(window.set_overlay_hour)
        layout.addWidget(self.overlay_hour)
        self.overlay_last = QCheckBox("Also show the last match and this session")
        self.overlay_last.setChecked(settings["overlay_show_last"])
        self.overlay_last.toggled.connect(window.set_overlay_last)
        layout.addWidget(self.overlay_last)
        self.size_slider, self.size_text = self._option_slider(
            layout, "Size", 100 * MIN_SCALE, 100 * MAX_SCALE,
            100 * clamp(settings["overlay_scale"], MIN_SCALE, MAX_SCALE, 1.0), "{}%", self._save_overlay_scale,
        )
        self.opacity_slider, self.opacity_text = self._option_slider(
            layout, "Opacity", 100 * MIN_OPACITY, 100 * MAX_OPACITY,
            100 * clamp(settings["overlay_opacity"], MIN_OPACITY, MAX_OPACITY, 1.0), "{}%", self._save_overlay_opacity,
        )
        layout.addWidget(label(
            "Use Set overlay position to see the badge while you adjust size and opacity.", "small", wrap=True,
        ))

        layout.addSpacing(12)
        layout.addWidget(label("Chime", "subheading"))
        layout.addWidget(label(
            "A short sound each time a chest is counted, for when you miss the animation.",
            "muted", wrap=True,
        ))
        chime_row = QHBoxLayout()
        self.chime_enabled = QCheckBox("Play a sound when a chest is counted")
        self.chime_enabled.setChecked(bool(settings["chime_enabled"]))
        self.chime_enabled.toggled.connect(self._save_chime_enabled)
        chime_row.addWidget(self.chime_enabled, 1)
        self.chime_test = QPushButton("Play sound")
        self.chime_test.clicked.connect(self.window_.play_chime)
        chime_row.addWidget(self.chime_test)
        layout.addLayout(chime_row)
        self.volume_slider, self.volume_text = self._option_slider(
            layout, "Volume", 100 * MIN_VOLUME, 100 * MAX_VOLUME,
            100 * clamp_volume(settings["chime_volume"]), "{}%", self._save_chime_volume,
        )
        layout.addSpacing(12)
        layout.addWidget(label("Replay counting", "subheading"))
        layout.addWidget(label(
            "After each match the app reads Fortnite's replay file to get the exact chest count, "
            "including chests you broke instead of opening. If the replay can't be read, the count "
            "from the screen is kept. Needs Fortnite's \"Record Replays\" setting turned on.",
            "muted", wrap=True,
        ))
        self.replay_count = QCheckBox("Use the replay to count chests after each match")
        self.replay_count.setChecked(bool(settings["replay_count"]))
        self.replay_count.toggled.connect(lambda on: self.window_.settings.set(replay_count=on))
        layout.addWidget(self.replay_count)
        layout.addSpacing(10)
        layout.addWidget(label("Updates", "small"))
        self.version_label = label(f"You have version {VERSION}.", "muted")
        layout.addWidget(self.version_label)
        update_row = QHBoxLayout()
        self.update_mode = QComboBox()
        for key, text in UPDATE_MODES:
            self.update_mode.addItem(text, key)
        self.update_mode.setCurrentIndex(max(0, self.update_mode.findData(settings["update_mode"])))
        self.update_mode.currentIndexChanged.connect(self._save_update_mode)
        update_row.addWidget(self.update_mode, 1)
        self.update_check = QPushButton("Check for updates")
        self.update_check.clicked.connect(lambda: window.check_for_updates(manual=True))
        update_row.addWidget(self.update_check)
        layout.addLayout(update_row)
        self.update_status = label("", "muted", wrap=True)
        layout.addWidget(self.update_status)
        layout.addStretch(1)
        self.refresh_gallery()
        self.refresh_steps()
        self._show_name_problem(name_problem(settings["player_name"]))
        self._open_step(next((s for s in self.steps if not s.done), self.prompt_step))

    def _open_step(self, chosen: Step) -> None:
        for step in self.steps:
            step.set_open(step is chosen and not (step.is_open and step is chosen))

    def _option_slider(self, layout, name: str, low: float, high: float, value: float, text: str, on_done):
        """A labelled slider that applies as it moves and saves when released."""
        row = QHBoxLayout()
        title = label(name, "muted")
        title.setMinimumWidth(70)
        row.addWidget(title)
        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setRange(round(low), round(high))
        slider.setValue(round(value))
        shown = label(text.format(slider.value()), "small")
        shown.setMinimumWidth(48)
        slider.valueChanged.connect(lambda v: shown.setText(text.format(v)))
        slider.valueChanged.connect(lambda v: on_done(v / 100, False))
        slider.sliderReleased.connect(lambda: on_done(slider.value() / 100, True))
        row.addWidget(slider, 1)
        row.addWidget(shown)
        layout.addLayout(row)
        return slider, shown

    def _save_overlay_scale(self, value: float, final: bool) -> None:
        self.window_.set_overlay_scale(value, save=final or not self.size_slider.isSliderDown())

    def _save_overlay_opacity(self, value: float, final: bool) -> None:
        self.window_.set_overlay_opacity(value, save=final or not self.opacity_slider.isSliderDown())

    def _save_chime_enabled(self, enabled: bool) -> None:
        self.window_.settings.set(chime_enabled=enabled)
        if enabled:
            self.window_.play_chime()

    def _save_chime_volume(self, value: float, final: bool) -> None:
        if final or not self.volume_slider.isSliderDown():
            self.window_.settings.set(chime_volume=clamp_volume(value))
        if final:
            self.window_.play_chime(volume=value)

    def _toggle_overlay_position(self) -> None:
        self.window_.toggle_overlay_positioning()
        self.overlay_position.setText(
            "Done positioning" if self.window_._overlay_positioning else "Set overlay position"
        )

    def refresh_steps(self) -> None:
        settings = self.window_.settings
        name_summary = settings["player_name"] or (
            "Needed to share" if settings["webhook_url"] else "Optional"
        )
        self.name_step.set_done(not settings["webhook_url"] or bool(settings["player_name"]), name_summary)
        self.webhook_step.set_done(True, "Linked" if settings["webhook_url"] else "Local only")
        self.key_step.set_done(
            True,
            f"{key_label(settings['interact_keys'][0])} interact · {key_label(settings['remove_key'])} undo"
            f" · {key_label(settings['pause_key'])} pause · {key_label(settings['match_key'])} new match",
        )
        count = len(list(self.window_.templates_dir.glob("*.png")))
        self.prompt_step.set_done(count > 0, f"{count} saved")

    def refresh_gallery(self) -> None:
        while self.gallery.count():
            item = self.gallery.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        paths = sorted(self.window_.templates_dir.glob("*.png"))
        if not paths:
            self.gallery.addWidget(label("No prompt saved yet.", "small"))
        for path in paths:
            box = QWidget()
            holder = QVBoxLayout(box)
            holder.setContentsMargins(0, 0, 0, 0)
            holder.setSpacing(6)
            thumb = QLabel()
            thumb.setObjectName("promptThumb")
            image = QPixmap(str(path))
            if image.width() > 150 or image.height() > 60:
                image = image.scaled(150, 60, Qt.AspectRatioMode.KeepAspectRatio)
            thumb.setPixmap(image)
            remove = QPushButton("Remove")
            remove.clicked.connect(lambda _=False, p=path: self._remove(p))
            holder.addWidget(thumb)
            holder.addWidget(remove)
            self.gallery.addWidget(box)
        self.gallery.addStretch(1)

    def _remove(self, path: Path) -> None:
        path.unlink(missing_ok=True)
        self.refresh_gallery()
        self.refresh_steps()
        self.window_.restart_engine()

    def _calibrate(self) -> None:
        dialog = PromptDialog(self, self.window_.templates_dir, self.window_.settings["search_area"])
        saved = dialog.exec()
        dialog.deleteLater()
        if saved:
            self.refresh_gallery()
            self.refresh_steps()
            self.window_.restart_engine()

    def _show_name_problem(self, problem: str | None) -> None:
        self.name_status.setVisible(bool(problem))
        if problem:
            self.name_status.setText(f'<span style="color:{EMBER}">{problem}</span>')

    def _save_name(self) -> None:
        name = self.name.text().strip()
        problem = name_problem(name)
        self._show_name_problem(problem)
        if problem:  # Discord would refuse every post under this name, so don't keep it
            return
        if name != self.window_.settings["player_name"]:
            self.window_.settings.set(player_name=name)
            self.refresh_steps()
            self.window_.apply_identity()

    def _save_webhook(self) -> None:
        url = self.webhook.text().strip()
        if url != self.window_.settings["webhook_url"]:
            self.window_.settings.set(webhook_url=url)
            self.refresh_steps()
            self.window_.apply_identity()
            if url:
                self._test_webhook()

    def _save_key(self, name: str) -> None:
        if self._key_taken(name, "interact"):
            self.capture.set_key(self.window_.settings["interact_keys"][0])
            QMessageBox.warning(
                self, "Keys must be different", "Choose a different key for interact, undo, pause and new match."
            )
            return
        self.window_.settings.set(interact_keys=[name])
        self.refresh_steps()
        self.window_.restart_engine()

    def _key_taken(self, name: str, own: str) -> bool:
        """True if another action already uses this key (interact, undo, pause and new match differ)."""
        settings = self.window_.settings
        others = {
            "interact": settings["interact_keys"][0], "remove": settings["remove_key"],
            "pause": settings["pause_key"], "match": settings["match_key"],
        }
        others.pop(own)
        return name in others.values()

    def _typing_key_allowed(self, name: str, what: str) -> bool:
        """Typing in Fortnite (chat, search boxes, party names) would trigger a letter or space key."""
        if not (name == "BACKSPACE" or len(name) == 1 or name == "SPACE"):
            return True
        answer = QMessageBox.question(
            self, "This key is used for typing",
            f"{key_label(name)} is pressed while typing in Fortnite, so chat or a search box could "
            f"{what} by accident. Use it anyway?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return answer == QMessageBox.StandardButton.Yes

    def _save_remove_key(self, name: str) -> None:
        settings = self.window_.settings
        if self._key_taken(name, "remove"):
            self.remove_capture.set_key(settings["remove_key"])
            QMessageBox.warning(
                self, "Keys must be different", "Choose a different key for interact, undo, pause and new match."
            )
            return
        if not self._typing_key_allowed(name, "remove chests"):
            self.remove_capture.set_key(settings["remove_key"])
            return
        settings.set(remove_key=name)
        self.refresh_steps()
        self.window_.restart_engine()

    def _save_pause_key(self, name: str) -> None:
        settings = self.window_.settings
        if self._key_taken(name, "pause"):
            self.pause_capture.set_key(settings["pause_key"])
            QMessageBox.warning(
                self, "Keys must be different", "Choose a different key for interact, undo, pause and new match."
            )
            return
        if not self._typing_key_allowed(name, "pause tracking"):
            self.pause_capture.set_key(settings["pause_key"])
            return
        settings.set(pause_key=name)
        self.refresh_steps()
        self.window_.restart_engine()

    def _save_match_key(self, name: str) -> None:
        settings = self.window_.settings
        if self._key_taken(name, "match"):
            self.match_capture.set_key(settings["match_key"])
            QMessageBox.warning(self, "Keys must be different", "Choose a different key for interact, undo, pause and new match.")
            return
        if not self._typing_key_allowed(name, "start a new match"):
            self.match_capture.set_key(settings["match_key"])
            return
        settings.set(match_key=name)
        self.refresh_steps()
        self.window_.restart_engine()

    def _save_threshold(self, value: float) -> None:
        if value != self.window_.settings["match_threshold"]:
            self.window_.settings.set(match_threshold=value)
            self.window_.restart_engine()

    def _save_update_mode(self) -> None:
        self.window_.settings.set(update_mode=self.update_mode.currentData())
        self.window_.schedule_update_checks()

    def show_update_status(self, text: str, problem: bool = False) -> None:
        color = EMBER if problem else ASH
        self.update_status.setText(f'<span style="color:{color}">{text}</span>' if text else "")

    def _show_match_problem(self, text: str | None) -> None:
        self.match_status.setText(f'<span style="color:{EMBER}">{text}</span>' if text else "")
        self.match_status.setVisible(bool(text))

    def _save_match_webhook(self) -> None:
        url = self.match_webhook.text().strip()
        if url and not is_webhook_url(url):
            self._show_match_problem("That doesn't look like a Discord webhook URL.")
            return
        self._show_match_problem(None)
        if url != self.window_.settings["match_webhook_url"]:
            self.window_.settings.set(match_webhook_url=url)
            self.window_.apply_identity()

    def _save_match_post(self, on: bool) -> None:
        self.window_.settings.set(match_post=on)

    def _save_party(self) -> None:
        text = self.party.text()
        problem = party_problem(text)
        self._show_match_problem(problem)
        if problem:
            return
        code = normalize_party(text)
        self.party.setText(code)
        if code != self.window_.settings["party_code"]:
            self.window_.settings.set(party_code=code)

    def _test_webhook(self) -> None:
        url = self.webhook.text().strip()
        self.test.setEnabled(False)
        self.webhook_status.setText("Checking the link.")
        self.webhook_status.show()
        threading.Thread(
            target=lambda: self.webhook_result.emit(*check_webhook(url)), daemon=True
        ).start()

    def _show_webhook_result(self, ok: bool, message: str) -> None:
        self.test.setEnabled(True)
        color = MINT if ok else EMBER
        self.webhook_status.setText(f'<span style="color:{color}">{message}</span>')

    def show_score(self, score: float) -> None:
        self.meter.set_score(score)
        seen = score >= self.window_.settings["match_threshold"]
        self.score_text.setText(f"Match {score:.2f}, needs {self.meter.threshold:.2f}" + (". Prompt seen." if seen else ""))

    def clear_score(self, text: str) -> None:
        self.meter.set_score(0)
        self.score_text.setText(text)


class FortniteStatsPage(QWidget):
    result_ready = Signal(object, str)

    METRICS = (
        ("wins", "Wins"),
        ("winRate", "Win rate"),
        ("kd", "K/D"),
        ("kills", "Eliminations"),
    )

    def __init__(self, window: "MainWindow"):
        super().__init__()
        self.window_ = window
        settings = window.settings
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll, layout = scroll_page()
        outer.addWidget(scroll)

        layout.addWidget(label("Fortnite stats", "heading"))
        layout.addWidget(label(
            "Look up Battle Royale lifetime or current-season stats. Fortnite-API.com is an independent "
            "service, not an Epic Games API. You provide its key and a public player name; this app does "
            "not sign in to Epic.",
            "muted", wrap=True,
        ))

        form = QFrame()
        form.setObjectName("statCard")
        fields = QGridLayout(form)
        fields.setContentsMargins(18, 16, 18, 16)
        fields.setHorizontalSpacing(12)
        fields.setVerticalSpacing(10)
        fields.addWidget(label("Fortnite-API key", "small"), 0, 0)
        self.api_key = QLineEdit(settings["fortnite_api_key"])
        self.api_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_key.setPlaceholderText("Paste your API key; it stays in this app's local settings")
        fields.addWidget(self.api_key, 0, 1, 1, 2)
        api_link = QPushButton("Get API key")
        api_link.clicked.connect(lambda: QDesktopServices.openUrl(QUrl("https://dash.fortnite-api.com/account")))
        fields.addWidget(api_link, 0, 3)

        fields.addWidget(label("Player name", "small"), 1, 0)
        self.account_name = QLineEdit(settings["fortnite_account_name"])
        self.account_name.setPlaceholderText("Fortnite display name")
        fields.addWidget(self.account_name, 1, 1)
        fields.addWidget(label("Platform", "small"), 1, 2)
        self.account_type = QComboBox()
        for text, value in (("Epic", "epic"), ("PlayStation", "psn"), ("Xbox", "xbl")):
            self.account_type.addItem(text, value)
        self._set_combo_data(self.account_type, settings["fortnite_account_type"])
        fields.addWidget(self.account_type, 1, 3)

        fields.addWidget(label("Stats period", "small"), 2, 0)
        self.time_window = QComboBox()
        self.time_window.addItem("Lifetime", "lifetime")
        self.time_window.addItem("Current season", "season")
        self._set_combo_data(self.time_window, settings["fortnite_stats_window"])
        fields.addWidget(self.time_window, 2, 1)
        self.refresh = QPushButton("Refresh stats")
        self.refresh.setObjectName("primary")
        self.refresh.clicked.connect(self._fetch)
        fields.addWidget(self.refresh, 2, 3)
        layout.addWidget(form)

        self.status = label("Enter your key and a player name, then select Refresh stats.", "small", wrap=True)
        layout.addWidget(self.status)
        self.profile_title = label("No stats loaded yet", "subheading")
        layout.addWidget(self.profile_title)

        layout.addWidget(label("Overall", "subheading"))
        self.overall_values = self._add_metric_cards(layout, 4)

        layout.addWidget(label("By game mode", "subheading"))
        self.mode_values = {}
        mode_grid = QGridLayout()
        mode_grid.setHorizontalSpacing(12)
        mode_grid.setVerticalSpacing(12)
        for column, (mode, title) in enumerate((("solo", "Solo"), ("duo", "Duos"), ("squad", "Squads"))):
            self.mode_values[mode] = self._add_mode_card(mode_grid, column, title)
        layout.addLayout(mode_grid)
        layout.addStretch(1)

        self.result_ready.connect(self._show_result)
        cached = settings["fortnite_stats_cache"]
        if isinstance(cached, dict) and cached.get("account"):
            self._render_stats(cached, cached=True)

    @staticmethod
    def _set_combo_data(combo: QComboBox, value: str) -> None:
        index = combo.findData(value)
        if index >= 0:
            combo.setCurrentIndex(index)

    def _add_metric_cards(self, layout: QVBoxLayout, columns: int) -> dict[str, QLabel]:
        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(10)
        values = {}
        for index, (key, title) in enumerate(self.METRICS):
            card = QFrame()
            card.setObjectName("statCard")
            box = QVBoxLayout(card)
            box.setContentsMargins(16, 12, 16, 12)
            box.setSpacing(4)
            box.addWidget(label(title, "cardTitle"))
            value = label("—", "sessionCount")
            box.addWidget(value)
            grid.addWidget(card, index // columns, index % columns)
            values[key] = value
        layout.addLayout(grid)
        return values

    def _add_mode_card(self, grid: QGridLayout, column: int, title: str) -> dict[str, QLabel]:
        card = QFrame()
        card.setObjectName("statCard")
        box = QVBoxLayout(card)
        box.setContentsMargins(16, 12, 16, 12)
        box.setSpacing(6)
        box.addWidget(label(title, "subheading"))
        values = {}
        for key, caption in (("wins", "Wins"), ("winRate", "Win rate"), ("kd", "K/D")):
            row = QHBoxLayout()
            row.addWidget(label(caption, "muted"))
            row.addStretch(1)
            value = label("—", "small")
            row.addWidget(value)
            box.addLayout(row)
            values[key] = value
        grid.addWidget(card, 0, column)
        return values

    def _fetch(self) -> None:
        key = self.api_key.text().strip()
        name = self.account_name.text().strip()
        account_type = self.account_type.currentData()
        time_window = self.time_window.currentData()
        self.window_.settings.set(
            fortnite_api_key=key,
            fortnite_account_name=name,
            fortnite_account_type=account_type,
            fortnite_stats_window=time_window,
        )
        self.status.setText("Fetching stats…")
        self.refresh.setEnabled(False)

        def request() -> None:
            try:
                result = fetch_stats(key, name, account_type, time_window)
            except FortniteStatsError as error:
                self.result_ready.emit(None, str(error))
            except Exception as error:
                log.warning("Fortnite stats lookup failed: %s", error.__class__.__name__)
                self.result_ready.emit(None, "The stats lookup failed unexpectedly. Please try again.")
            else:
                self.result_ready.emit(result, "")

        threading.Thread(target=request, name="fortnite-stats", daemon=True).start()

    def _show_result(self, result: object, error: str) -> None:
        self.refresh.setEnabled(True)
        if error:
            self.status.setText(error)
            return
        if not isinstance(result, dict):
            self.status.setText("The stats service returned no usable stats.")
            return
        self.window_.settings.set(fortnite_stats_cache=result)
        self._render_stats(result, cached=False)

    def _render_stats(self, result: dict, cached: bool) -> None:
        account = result.get("account") or {}
        stats = result.get("stats") or {}
        overall = stats.get("overall") or {}
        self.profile_title.setText(f"{account.get('name', 'Player')} · {result.get('time_window', 'lifetime').title()}")
        for key, _title in self.METRICS:
            self.overall_values[key].setText(self._format_stat(key, overall.get(key)))
        for mode, values in self.mode_values.items():
            row = stats.get(mode) or {}
            for key, value in values.items():
                value.setText(self._format_stat(key, row.get(key)))
        self.status.setText("Showing saved stats." if cached else f"Updated {datetime.now():%Y-%m-%d %H:%M}.")

    @staticmethod
    def _format_stat(key: str, value) -> str:
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            return "—"
        if key == "winRate":
            return f"{value:.1f}%"
        if key == "kd":
            return f"{value:.2f}"
        return f"{int(value):,}"


class GroupPage(QWidget):
    def __init__(self, window: "MainWindow"):
        super().__init__()
        self.window_ = window
        settings = window.settings
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll, layout = scroll_page()
        outer.addWidget(scroll)

        header = QHBoxLayout()
        header.addWidget(label("Group", "heading"))
        header.addStretch(1)
        self.group_total = label("", "muted")
        header.addWidget(self.group_total, 0, Qt.AlignmentFlag.AlignBottom)
        layout.addLayout(header)

        self.board = QVBoxLayout()
        self.board.setSpacing(2)
        layout.addLayout(self.board)
        self.sync_row = QWidget()
        sync = QHBoxLayout(self.sync_row)
        sync.setContentsMargins(0, 6, 0, 0)
        self.sync_text = label("", "muted", wrap=True)
        sync.addWidget(self.sync_text, 1)
        self.sync_button = QPushButton("Sync my total")
        self.sync_button.setToolTip("Post the difference so the leaderboard matches your total.")
        self.sync_button.clicked.connect(self.sync_now)
        sync.addWidget(self.sync_button)
        self.sync_row.hide()
        layout.addWidget(self.sync_row)
        layout.addSpacing(14)

        bot_row = QHBoxLayout()
        self.disclosure = QPushButton()
        self.disclosure.setObjectName("disclosure")
        self.disclosure.clicked.connect(lambda: self._show_connection(not self.connection.isVisible()))
        bot_row.addWidget(self.disclosure)
        bot_row.addStretch(1)
        self.pill = Pill()
        self.pill.show_state(ASH, "Bot off")
        bot_row.addWidget(self.pill)
        layout.addLayout(bot_row)

        self.connection = QWidget()
        section = QVBoxLayout(self.connection)
        section.setContentsMargins(0, 4, 0, 0)
        section.setSpacing(8)
        section.addWidget(label(
            "One person in your group runs the bot, and everyone else can skip this. It keeps the "
            "leaderboard and answers /chests and /leaderboard in Discord. If it's off, it catches up "
            "the next time it starts.",
            "muted", wrap=True,
        ))
        section.addWidget(label("Bot token", "small"))
        self.token = QLineEdit(settings["bot_token"])
        self.token.setEchoMode(QLineEdit.EchoMode.Password)
        self.token.setPlaceholderText("From the Discord Developer Portal, on the Bot page")
        self.token.editingFinished.connect(self._save)
        section.addWidget(self.token)
        section.addWidget(label("Channel ID", "small"))
        self.channel = QLineEdit(settings["channel_id"])
        self.channel.setPlaceholderText("Right-click the channel in Discord, then Copy Channel ID")
        self.channel.editingFinished.connect(self._save)
        section.addWidget(self.channel)
        section.addWidget(label("Match reports channel ID (optional)", "small"))
        self.match_channel = QLineEdit(settings["match_channel_id"])
        self.match_channel.setPlaceholderText("The channel your match reports webhook posts to")
        self.match_channel.editingFinished.connect(self._save)
        section.addWidget(self.match_channel)
        section.addWidget(label(
            "With this set, the bot posts a group game report in that channel when teammates using the "
            "same party code finish a match. It waits 3 minutes for the rest of the team.",
            "muted", wrap=True,
        ))
        self.auto = QCheckBox("Start the bot when the app opens")
        self.auto.setChecked(settings["run_bot"])
        self.auto.toggled.connect(lambda on: settings.set(run_bot=on))
        section.addWidget(self.auto)
        row = QHBoxLayout()
        self.toggle = QPushButton("Start bot")
        self.toggle.setObjectName("primary")
        self.toggle.clicked.connect(window.toggle_bot)
        row.addWidget(self.toggle)
        portal = QPushButton("Open Developer Portal")
        portal.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl("https://discord.com/developers/applications"))
        )
        row.addWidget(portal)
        row.addStretch(1)
        section.addLayout(row)
        self.message = label("", "small", wrap=True)
        self.message.setTextFormat(Qt.TextFormat.PlainText)
        section.addWidget(self.message)
        layout.addWidget(self.connection)
        layout.addStretch(1)
        self._show_connection(not settings["bot_token"])

    def _show_connection(self, visible: bool) -> None:
        self.connection.setVisible(visible)
        self.disclosure.setText(("Hide" if visible else "Show") + " bot connection")

    def _save(self) -> None:
        self.window_.settings.set(
            bot_token=self.token.text().strip(), channel_id=self.channel.text().strip(),
            match_channel_id=self.match_channel.text().strip(),
        )

    def show_leaderboard(self, rows: list[tuple[str, int]], total: int) -> None:
        clear_layout(self.board)
        if not rows:
            self.board.addWidget(label(
                "No chests on the leaderboard yet. The player running the bot sees totals here once "
                "anyone opens a chest.", "muted", wrap=True,
            ))
        me = self.window_.settings["player_name"].lower()
        top = rows[0][1] if rows else 0
        for rank, (name, count) in enumerate(rows, 1):
            self.board.addWidget(LeaderRow(rank, name, count, top, name.lower() == me))
        self.group_total.setText(f"{total:,} chests between you" if rows else "")
        self.update_sync()

    def update_sync(self) -> None:
        """Offer to bring your leaderboard number in line with your total (edits, imports and past replays)."""
        gap = self.window_.group_gap()
        self.sync_row.setVisible(bool(gap))
        if gap:
            direction = "short" if gap > 0 else "too high"
            self.sync_text.setText(
                f"Your total is {self.window_.stats.total:,}, but the leaderboard has you {abs(gap):,} {direction}."
            )

    def sync_now(self) -> None:
        gap = self.window_.sync_group_total()
        if gap:
            self.sync_row.hide()
            self.sync_text.setText("")


def clear_layout(layout) -> None:
    """Remove every widget from a layout right away (deleteLater alone leaves them drawn until the next event)."""
    while layout.count():
        widget = layout.takeAt(0).widget()
        if widget is not None:
            widget.hide()
            widget.setParent(None)
            widget.deleteLater()


class DayChart(QWidget):
    """Bars of chests per day."""

    def __init__(self):
        super().__init__()
        self.days: list[tuple] = []
        self.setMinimumHeight(150)

    def set_days(self, days: list[tuple]) -> None:
        self.days = days
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if not self.days:
            return
        top = max((n for _, n in self.days), default=0) or 1
        width = self.width() / len(self.days)
        base = self.height() - 18
        for index, (day, count) in enumerate(self.days):
            height = (base - 16) * count / top
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(GOLD))
            painter.drawRoundedRect(QRect(round(index * width + 4), round(base - height), max(2, round(width - 8)), max(1, round(height))), 3, 3)
            painter.setPen(QColor(BONE))
            painter.drawText(QRect(round(index * width), round(base - height) - 16, round(width), 14), Qt.AlignmentFlag.AlignCenter, str(count) if count else "")
            painter.setPen(QColor(ASH))
            painter.drawText(QRect(round(index * width), base + 2, round(width), 14), Qt.AlignmentFlag.AlignCenter, str(day.day))


class ReportPage(QWidget):
    PAGE = 10  # matches shown at a time

    def __init__(self, window: "MainWindow"):
        super().__init__()
        self.window_ = window
        self.shown = self.PAGE
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll, layout = scroll_page()
        outer.addWidget(scroll)
        head = QHBoxLayout()
        head.addWidget(label("Report", "heading"), 1)
        self.open_button = QPushButton("Open as a web page")
        self.open_button.setToolTip("Saves report.html in the app's data folder and opens it in your browser.")
        self.open_button.clicked.connect(window.open_report)
        head.addWidget(self.open_button)
        layout.addLayout(head)
        self.tiles = QHBoxLayout()
        layout.addLayout(self.tiles)
        layout.addWidget(label("Chests per day", "subheading"))
        self.chart = DayChart()
        layout.addWidget(self.chart)
        layout.addWidget(label("By chest type", "subheading"))
        self.kinds = QVBoxLayout()
        layout.addLayout(self.kinds)
        layout.addWidget(label("Latest matches", "subheading"))
        self.latest = QListWidget()
        self.latest.setObjectName("activityList")
        self.latest.setToolTip("Click a match for its details.")
        self.latest.itemClicked.connect(self.show_details)
        layout.addWidget(self.latest)
        self.more = QPushButton("Show 10 more")
        self.more.clicked.connect(self.show_more)
        layout.addWidget(self.more)
        layout.addStretch(1)

    def show_more(self) -> None:
        self.shown += self.PAGE
        self.refresh()

    def show_details(self, item) -> None:
        match = item.data(Qt.ItemDataRole.UserRole)
        if match:
            QMessageBox.information(self, "Match details", report.match_details(match, self.window_.settings["clock_format"]))

    def refresh(self) -> None:
        window = self.window_
        data = report.build(window.matches.history, window.stats.total, window.stats.session)
        clear_layout(self.tiles)
        for value, name in (
            (f"{data.total:,}", "chests in total"), (f"{data.session:,}", "this session"),
            (f"{data.match_count:,}", "matches"), (f"{data.average:.1f}", "per match"), (f"{data.best:,}", "best match"),
        ):
            card = QFrame()
            card.setObjectName("statCard")
            inner = QVBoxLayout(card)
            inner.setContentsMargins(14, 10, 14, 10)
            inner.addWidget(label(value, "bigNumber"))
            inner.addWidget(label(name, "muted"))
            self.tiles.addWidget(card)
        self.chart.set_days(data.days)
        clear_layout(self.kinds)
        for name, count in data.kinds or [("Nothing yet", 0)]:
            self.kinds.addWidget(label(f"{name}: {count:,}" if count else name, "small"))
        self.latest.clear()
        clock = window.settings["clock_format"]
        for m in data.latest[: self.shown]:
            row = QListWidgetItem(report.match_line(m, clock))
            row.setData(Qt.ItemDataRole.UserRole, m)
            self.latest.addItem(row)
        if not data.latest:
            self.latest.addItem("No finished matches yet")
        self.more.setVisible(len(data.latest) > self.shown)
        self.latest.setMinimumHeight(min(self.shown, max(1, len(data.latest))) * 26 + 12)


class SettingsPage(QWidget):
    def __init__(self, window: "MainWindow"):
        super().__init__()
        self.window_ = window
        settings = window.settings
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll, layout = scroll_page()
        outer.addWidget(scroll)
        layout.addWidget(label("Settings", "heading"))

        layout.addWidget(label("Replays", "subheading"))
        layout.addWidget(label(
            "Where Fortnite keeps its replay files. Leave it on the default unless you moved them.", "muted", wrap=True,
        ))
        row = QHBoxLayout()
        self.replay_folder = QLineEdit(settings["replay_folder"])
        self.replay_folder.setPlaceholderText(str(replays.default_replay_folder()))
        self.replay_folder.editingFinished.connect(self.save_folder)
        row.addWidget(self.replay_folder, 1)
        browse = QPushButton("Browse...")
        browse.clicked.connect(self.browse)
        row.addWidget(browse)
        default = QPushButton("Use default")
        default.clicked.connect(self.use_default)
        row.addWidget(default)
        layout.addLayout(row)

        layout.addSpacing(8)
        layout.addWidget(label("Goals", "subheading"))
        layout.addWidget(label(
            "Set a target for each day and for each match. Progress shows on the Tracker tab and on the overlay. "
            "Leave a goal at 0 for none.", "muted", wrap=True,
        ))
        goals_row = QHBoxLayout()
        self.day_goal_box = QSpinBox()
        self.match_goal_box = QSpinBox()
        for box, key, text in ((self.day_goal_box, "daily_goal", "Chests per day"),
                               (self.match_goal_box, "match_goal", "Chests per match")):
            box.setRange(0, goals.MAX_GOAL)
            box.setValue(goals.clean_goal(settings[key]))
            box.setSpecialValueText("None")
            box.valueChanged.connect(lambda value, k=key: self.save_goal(k, value))
            goals_row.addWidget(label(text, "small"))
            goals_row.addWidget(box)
            goals_row.addSpacing(14)
        goals_row.addStretch(1)
        layout.addLayout(goals_row)
        self.goal_sound = QCheckBox("Play a double chime when I reach a goal")
        self.goal_sound.setChecked(bool(settings["goal_sound"]))
        self.goal_sound.toggled.connect(lambda on: window.settings.set(goal_sound=on))
        layout.addWidget(self.goal_sound)

        layout.addSpacing(8)
        layout.addWidget(label("Clock", "subheading"))
        self.clock = QComboBox()
        for value, name in timefmt.CLOCKS:
            self.clock.addItem(name, value)
        self.clock.setCurrentIndex(max(0, self.clock.findData(settings["clock_format"])))
        self.clock.currentIndexChanged.connect(self.save_clock)
        layout.addWidget(self.clock)

        layout.addSpacing(8)
        layout.addWidget(label("Window", "subheading"))
        self.tray = QCheckBox("Minimize to the system tray instead of the taskbar")
        self.tray.setChecked(bool(settings["minimize_to_tray"]))
        self.tray.toggled.connect(lambda on: window.settings.set(minimize_to_tray=on))
        layout.addWidget(self.tray)
        exe = updater.running_exe()
        self.startup = QCheckBox("Start with Windows, minimized to the tray")
        self.startup.setEnabled(startup.supported(exe))
        self.startup.setChecked(startup.is_enabled())
        self.startup.toggled.connect(self.save_startup)
        layout.addWidget(self.startup)
        self.startup_note = label(
            "" if startup.supported(exe) else "Only available in the installed Chest-Tracker.exe on Windows.",
            "muted", wrap=True,
        )
        layout.addWidget(self.startup_note)

        layout.addSpacing(8)
        layout.addWidget(label("Messages", "subheading"))
        self.notices_box = QCheckBox("Show short messages from the developer (for example about a Fortnite update)")
        self.notices_box.setChecked(bool(settings["show_notices"]))
        self.notices_box.toggled.connect(self.save_notices)
        layout.addWidget(self.notices_box)

        layout.addSpacing(8)
        layout.addWidget(label("Backup", "subheading"))
        layout.addWidget(label(
            "Saves your total, match history and list of changes in one file (not your Discord settings). "
            "A backup is also made automatically once a day and the last week is kept.", "muted", wrap=True,
        ))
        self.auto_backup = QCheckBox("Back up automatically")
        self.auto_backup.setChecked(bool(settings["auto_backup"]))
        self.auto_backup.toggled.connect(lambda on: window.settings.set(auto_backup=on))
        layout.addWidget(self.auto_backup)
        backup_row = QHBoxLayout()
        save_backup = QPushButton("Back up now...")
        save_backup.clicked.connect(self.back_up_now)
        backup_row.addWidget(save_backup)
        restore = QPushButton("Restore from a backup...")
        restore.clicked.connect(self.restore)
        backup_row.addWidget(restore)
        backup_row.addStretch(1)
        layout.addLayout(backup_row)
        self.backup_status = label("", "small", wrap=True)
        layout.addWidget(self.backup_status)

        layout.addSpacing(8)
        layout.addWidget(label("Files", "subheading"))
        folder = QPushButton("Open the data folder")
        folder.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(window.folder))))
        layout.addWidget(folder)
        layout.addStretch(1)

    def save_notices(self, on: bool) -> None:
        self.window_.settings.set(show_notices=on)
        self.window_._refresh_notice()

    def back_up_now(self) -> None:
        suggested = backup.backups_folder(self.window_.folder) / f"chest-tracker-backup-{datetime.now():%Y-%m-%d}.json"
        chosen, _ = QFileDialog.getSaveFileName(self, "Save a backup", str(suggested), "Backup (*.json)")
        if not chosen:
            return
        try:
            backup.write(self.window_.folder, Path(chosen))
        except OSError as error:
            self.backup_status.setText(f"The backup couldn't be saved: {error}")
            return
        self.backup_status.setText(f"Saved to {chosen}")

    def restore(self) -> None:
        chosen, _ = QFileDialog.getOpenFileName(
            self, "Choose a backup", str(backup.backups_folder(self.window_.folder)), "Backup (*.json)")
        if not chosen:
            return
        try:
            summary = backup.describe(backup.read(Path(chosen)))
        except backup.BadBackup as error:
            self.backup_status.setText(str(error))
            return
        answer = QMessageBox.question(
            self, "Restore a backup",
            f"{summary}\n\nThis replaces your current total, match history and list of changes. Your current data "
            "is saved first, so you can go back.\n\nRestore it?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        problem = self.window_.restore_backup(Path(chosen))
        self.backup_status.setText(problem or "Restored. Your previous data was saved in the backups folder.")

    def save_folder(self) -> None:
        self.window_.settings.set(replay_folder=self.replay_folder.text().strip())

    def browse(self) -> None:
        start = self.replay_folder.text().strip() or str(replays.default_replay_folder())
        chosen = QFileDialog.getExistingDirectory(self, "Fortnite replay folder", start)
        if chosen:
            self.replay_folder.setText(chosen)
            self.save_folder()

    def use_default(self) -> None:
        self.replay_folder.setText("")
        self.save_folder()

    def save_goal(self, key: str, value: int) -> None:
        self.window_.settings.set(**{key: value})
        self.window_._show_goals()

    def save_clock(self) -> None:
        self.window_.settings.set(clock_format=self.clock.currentData())
        self.window_.tracker.clock_format = self.clock.currentData()
        self.window_.report.refresh()

    def save_startup(self, on: bool) -> None:
        done = startup.set_enabled(on, updater.running_exe())
        if not done:
            self.startup.blockSignals(True)
            self.startup.setChecked(not on)
            self.startup.blockSignals(False)
            self.startup_note.setText("Windows wouldn't let the app change this.")
            return
        self.window_.settings.set(start_with_windows=on)
        self.startup_note.setText("")


class TreasuresPage(QWidget):
    def __init__(self, window: "MainWindow"):
        super().__init__()
        self.window_ = window
        self.shown_finds = 10
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll, layout = scroll_page()
        outer.addWidget(scroll)
        layout.addWidget(label("Treasures", "heading"))
        layout.addWidget(label(
            "Golden chests and their prizes during the Treasure Hunters hunt. Treasures are read from the replay "
            "after each match; anything the replays missed can be ticked off by hand.", "muted", wrap=True,
        ))
        self.tiles = QHBoxLayout()
        layout.addLayout(self.tiles)
        week_row = QHBoxLayout()
        self.week_title = label("", "subheading")
        week_row.addWidget(self.week_title, 1)
        self.week_box = QComboBox()
        self.week_box.setToolTip("Look at an earlier week.")
        self.week_box.activated.connect(lambda _: self.refresh())
        week_row.addWidget(self.week_box)
        layout.addLayout(week_row)
        self.week_note = label(
            "Tick a prize you got that the replays didn't show (prizes found in a replay are ticked for you).",
            "muted", wrap=True,
        )
        layout.addWidget(self.week_note)
        self.week = QVBoxLayout()
        layout.addLayout(self.week)
        layout.addWidget(label("Your chances", "subheading"))
        self.chances_note = label("", "muted", wrap=True)
        layout.addWidget(self.chances_note)
        self.chances = QVBoxLayout()
        layout.addLayout(self.chances)
        layout.addWidget(label("Treasure Hours", "subheading"))
        self.hours = QVBoxLayout()
        layout.addLayout(self.hours)
        layout.addWidget(label("Latest finds", "subheading"))
        self.latest = QListWidget()
        self.latest.setObjectName("activityList")
        layout.addWidget(self.latest)
        self.more = QPushButton("Show 10 more")
        self.more.clicked.connect(self.show_more)
        layout.addWidget(self.more)
        self.credit = label("", "muted", wrap=True)
        layout.addWidget(self.credit)
        layout.addStretch(1)

    def tick(self, prize_id: str, on: bool) -> None:
        self.window_.treasure_marks.set(prize_id, on)
        QTimer.singleShot(0, self.refresh)  # after this click has finished, since refreshing rebuilds the boxes

    def show_more(self) -> None:
        self.shown_finds += 10
        self.refresh()

    def refresh(self) -> None:
        window = self.window_
        content = window.content_store.content
        history = window.matches.history
        now = datetime.now(timezone.utc)
        clock = window.settings["clock_format"]
        all_finds = treasures.finds(history)
        marks = self.window_.treasure_marks
        weeks = treasures.started_weeks(content, now)
        numbers = [w.number for w in weeks]
        if numbers != [self.week_box.itemData(i) for i in range(self.week_box.count())]:
            keep = self.week_box.currentData()
            self.week_box.blockSignals(True)
            self.week_box.clear()
            for index, w in enumerate(weeks):
                self.week_box.addItem(f"Week {w.number}" + (" (this week)" if index == 0 and w.end > now else ""), w.number)
            self.week_box.setCurrentIndex(max(0, self.week_box.findData(keep)))
            self.week_box.blockSignals(False)
        week = next((w for w in weeks if w.number == self.week_box.currentData()), None) or content.shown_week(now)

        clear_layout(self.tiles)
        collection = treasures.collection(content, all_finds, week)
        found_now = [(p, n, marks.is_marked(p.id)) for p, n in collection]
        got = sum(1 for _, n, marked in found_now if n or marked)
        shop = sum(max(n, 1 if marked else 0) for p, n, marked in found_now if p.kind == "pirate-shop")
        for value, name in (
            (f"{treasures.total_found(content, all_finds, set(marks.found)):,}", "treasures found"),
            (f"{got} of {len(collection)}" if collection else "-", f"prizes found, week {week.number}" if week else "prizes found"),
            (f"{shop:,}", "Pirate Shop Access"),
        ):
            card = QFrame()
            card.setObjectName("statCard")
            inner = QVBoxLayout(card)
            inner.setContentsMargins(14, 10, 14, 10)
            inner.addWidget(label(value, "bigNumber"))
            inner.addWidget(label(name, "muted"))
            self.tiles.addWidget(card)

        self.week_title.setText(f"Week {week.number}: {week.title}" if week else "This week")
        clear_layout(self.week)
        for prize, count, marked in found_now:
            kind = "" if prize.kind == "pirate-shop" else f" ({treasures.kind_name(prize.kind)})"
            text = prize.name + kind + (f" x{count}" if count > 1 else "") + (" - found in a replay" if count else "")
            box = QCheckBox(text.replace("&", "&&"))  # a lone & would turn the next letter into a shortcut
            box.setChecked(bool(count or marked))
            box.setEnabled(not count)  # a replay already proves it
            box.toggled.connect(lambda on, pid=prize.id: self.tick(pid, on))
            self.week.addWidget(box)
        if not collection:
            self.week.addWidget(label("No hunt data available.", "small"))
        elif week and not week.prizes:
            self.week.addWidget(label("This week's prizes haven't been announced in the data yet.", "small"))

        clear_layout(self.chances)
        rows = treasures.chances(content, history, now, week)
        replay_chests = sum(1 for m in history if m.get("chest_times"))
        self.chances_note.setText(
            "Chance of finding each kind of prize at least once with the chests you opened, counting the boosted "
            "odds during Treasure Hours. Weekly prizes use this week's chests; the rest use the whole hunt."
            + ("" if replay_chests else " Chests counted from the screen only have a match time, so they count at the normal odds.")
        )
        for row in rows:
            self.chances.addWidget(label(
                f"{treasures.kind_name(row.odds.kind)}: 1 in {row.odds.one_in:,} per chest. "
                f"{row.chests:,} chests, {treasures.percent(row.at_least_once)} chance so far "
                f"(about {row.expected:.2f} expected)", "small",
            ))
        clear_layout(self.hours)
        upcoming = [h for h in content.hours if h.end > now][:6]
        for h in upcoming:
            start, end = h.start.astimezone().replace(tzinfo=None), h.end.astimezone().replace(tzinfo=None)
            boosts = ", ".join(f"{treasures.kind_name(k)} x{b:g}" for k, b in h.boosts.items())
            state = "now" if h.start <= now else ("confirmed" if h.confirmed else "expected, not announced yet")
            self.hours.addWidget(label(
                f"{timefmt.format_stamp(start, clock)} to {timefmt.format_time(end, clock)} ({state}): {boosts}", "small",
            ))
        if not upcoming:
            self.hours.addWidget(label("No Treasure Hours listed.", "small"))

        self.latest.clear()
        for f in all_finds[: self.shown_finds]:
            moment = (f.when or f.match_start).astimezone().replace(tzinfo=None)
            self.latest.addItem(f"{timefmt.format_stamp(moment, clock)}: {f.name}")
        if not all_finds:
            self.latest.addItem("No treasures found yet")
        self.latest.setMinimumHeight(min(self.shown_finds, max(1, len(all_finds))) * 26 + 12)
        self.more.setVisible(len(all_finds) > self.shown_finds)
        self.credit.setText(
            f"Hunt data: revision {content.revision} of ChestCounter's content.json (LED-N, MIT), "
            "refreshed from GitHub every couple of hours."
            + (f" Odds: {content.odds_source}" if content.odds_source else "")
            + (f" Treasure Hours: {content.hours_source}" if content.hours_source else "")
        )


class MainWindow(QMainWindow):
    chest = Signal(int, str)
    attempt = Signal(str)
    engine_state = Signal(str)
    match_score = Signal(float)
    delivery = Signal(bool, str)
    bot_status = Signal(str, str)
    pause_pressed = Signal()
    new_match_pressed = Signal()
    match_ended = Signal()
    update_checked = Signal(object, bool)  # the result, and whether the person asked
    update_progress = Signal(float)
    update_ready = Signal(object, object)  # the release and its downloaded file
    update_failed = Signal(str)
    content_refreshed = Signal()
    notices_changed = Signal()
    replay_counted = Signal(object, object)  # the saved match, and its ReplayCount (None: not found)

    def __init__(self, folder: Path, icon: QIcon):
        super().__init__()
        self.folder = folder
        self.templates_dir = folder / "templates"
        self.settings = Settings(folder)
        self.stats = Stats(folder)
        self.matches = MatchLog(folder / "matches.json")
        self.adjustments = Adjustments(folder / "adjustments.json")
        self.treasure_marks = TreasureMarks(folder / "treasure_marks.json")
        self.recap = RecapDetector.load_bundled()  # None: matches are then ended with the key or button
        self.engine: WatchEngine | None = None
        self.bot: BotRunner | None = None
        self.paused = False
        self.delivery_ok = True
        self.current_state = "off"
        self.leaderboard_seen = None
        self.chime = Chime()
        self.box_filter = load_bundled()  # skips ammo and fruit boxes; None keeps counting everything
        self.overlay = ChestOverlay()
        self.overlay.set_scale(self.settings["overlay_scale"])
        self.overlay.set_opacity(self.settings["overlay_opacity"])
        self.overlay.set_count(self.stats.total)
        self.overlay.set_match(self.matches.current)
        self.overlay.set_match_visible(self.settings["overlay_show_match"])
        self.overlay.set_last_visible(self.settings["overlay_show_last"])
        self.overlay.set_hour_visible(self.settings["overlay_show_hour"])
        self.overlay.position_saved.connect(self._save_overlay_position)
        self._overlay_positioning = False
        self._overlay_screen = None

        self.setWindowTitle("Chest Tracker")
        self.setWindowIcon(icon)
        self.resize(1160, 780)
        self.setMinimumSize(920, 650)
        self.setStyleSheet(STYLE)

        root = QWidget()
        self.setCentralWidget(root)
        rows = QVBoxLayout(root)
        rows.setContentsMargins(0, 0, 0, 0)
        rows.setSpacing(0)

        topbar = QFrame()
        topbar.setObjectName("topbar")
        top = QHBoxLayout(topbar)
        top.setContentsMargins(20, 0, 20, 0)
        top.setSpacing(4)
        logo = QLabel()
        logo.setPixmap(icon.pixmap(28, 28))
        top.addWidget(logo)
        top.addSpacing(6)
        top.addWidget(label("Chest Tracker", "brand"))
        top.addSpacing(26)

        self.stack = QStackedWidget()
        self.tracker = TrackerPage(self)
        self.setup = SetupPage(self)
        self.group = GroupPage(self)
        self.fortnite_stats = FortniteStatsPage(self)
        self.content_store = content.ContentStore(folder)
        self._update_hour()
        self.report = ReportPage(self)
        self.treasures_page = TreasuresPage(self)
        self.settings_page = SettingsPage(self)
        self.nav = QButtonGroup(self)
        for index, (name, page) in enumerate(
            (("Tracker", self.tracker), ("Setup", self.setup), ("Group", self.group),
             ("Fortnite Stats", self.fortnite_stats), ("Report", self.report), ("Settings", self.settings_page),
             ("Treasures", self.treasures_page))
        ):
            self.stack.addWidget(page)
            button = QPushButton(name)
            button.setObjectName("tab")
            button.setCheckable(True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            self.nav.addButton(button, index)
            top.addWidget(button)
        self.nav.idClicked.connect(self.stack.setCurrentIndex)
        self.stack.currentChanged.connect(self._page_shown)
        self.nav.button(0).setChecked(True)
        top.addStretch(1)
        self.pill = Pill()
        top.addWidget(self.pill)
        rows.addWidget(topbar)
        self.banner = QFrame()
        self.banner.setObjectName("updateBanner")
        banner_row = QHBoxLayout(self.banner)
        banner_row.setContentsMargins(20, 8, 20, 8)
        self.banner_text = label("", "", wrap=True)
        banner_row.addWidget(self.banner_text, 1)
        self.banner_notes = QPushButton("What's new")
        self.banner_notes.clicked.connect(self.show_update_notes)
        banner_row.addWidget(self.banner_notes)
        self.banner_install = QPushButton("Install and restart")
        self.banner_install.setObjectName("primary")
        self.banner_install.clicked.connect(self.install_update)
        banner_row.addWidget(self.banner_install)
        self.banner_later = QPushButton("Later")
        self.banner_later.clicked.connect(self.banner.hide)
        banner_row.addWidget(self.banner_later)
        self.banner.hide()
        rows.addWidget(self.banner)
        self.notice_banner = QFrame()
        self.notice_banner.setObjectName("updateBanner")
        notice_row = QHBoxLayout(self.notice_banner)
        notice_row.setContentsMargins(20, 8, 20, 8)
        self.notice_text = label("", "", wrap=True)
        notice_row.addWidget(self.notice_text, 1)
        self.notice_dismiss = QPushButton("Dismiss")
        self.notice_dismiss.clicked.connect(self.dismiss_notice)
        notice_row.addWidget(self.notice_dismiss)
        self.notice_banner.hide()
        rows.addWidget(self.notice_banner)
        rows.addWidget(self.stack, 1)

        self.chest.connect(self.record_chest)
        self.attempt.connect(self._on_attempt)
        self.pause_pressed.connect(self.toggle_pause)
        self.new_match_pressed.connect(lambda: self.finish_match("key"))
        self.match_ended.connect(lambda: self.finish_match("recap"))
        self.engine_state.connect(self.set_state)
        self.match_score.connect(self.setup.show_score)
        self.delivery.connect(self._on_delivery)
        self.bot_status.connect(self._on_bot_status)
        self.update_checked.connect(self._on_update_checked)
        self.update_progress.connect(self._on_update_progress)
        self.update_ready.connect(self._on_update_ready)
        self.update_failed.connect(self._on_update_failed)
        self.found_update = None
        self.installing = False
        self._closing = threading.Event()
        self.content_refreshed.connect(lambda: (self.treasures_page.refresh(), self._update_hour()))
        self.notices_changed.connect(self._refresh_notice)
        self.hour_timer = QTimer(self)
        self.hour_timer.timeout.connect(self._update_hour)
        self.hour_timer.start(30_000)
        self.notice_feed = notices.NoticeFeed()
        self.replay_misses = 0  # matches in a row whose replay couldn't be read
        self.miss_reason = "unreadable"
        self.health_dismissed = False
        self._shown_notice: str | None = None
        QTimer.singleShot(20_000, self.run_auto_backup)
        self.backup_timer = QTimer(self)
        self.backup_timer.timeout.connect(self.run_auto_backup)
        self.backup_timer.start(6 * 3600 * 1000)
        QTimer.singleShot(6000, self.refresh_content)
        self.content_timer = QTimer(self)
        self.content_timer.timeout.connect(self.refresh_content)
        self.content_timer.start(2 * 3600 * 1000)
        self.replay_counted.connect(self._on_replay_counted)

        self.sender = Sender(
            self.settings["webhook_url"], self.settings["player_name"],
            folder / "pending.json", self.delivery.emit,
        )
        threading.Thread(target=self.sender.run_forever, daemon=True).start()
        self.poster = MatchPoster(
            self.settings["match_webhook_url"], self.settings["player_name"],
            folder / "pending_matches.json", self.delivery.emit,
        )
        threading.Thread(target=self.poster.run_forever, daemon=True).start()
        if self.poster.queue:
            self.poster.wake.set()
        if self.sender.pending:
            self.sender.wake.set()

        self._build_tray(icon)
        self._show_stats()
        self.tracker.stage.set_count(self.stats.total)
        self.restart_engine()
        if self.settings["run_bot"] and self.bot_ready():
            self.toggle_bot()

        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self._refresh)
        self.refresh_timer.start(5000)
        self.overlay_timer = QTimer(self)
        self.overlay_timer.timeout.connect(self._sync_overlay)
        self.overlay_timer.start(200)
        self._refresh()
        self._sync_overlay()
        self.update_timer = QTimer(self)
        self.update_timer.timeout.connect(lambda: self.check_for_updates(manual=False))
        self.auto_timer = QTimer(self)
        self.auto_timer.timeout.connect(self._try_auto_install)
        self.schedule_update_checks()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        dark_title_bar(self)

    def _build_tray(self, icon: QIcon) -> None:
        self.tray = QSystemTrayIcon(icon, self)
        menu = QMenu()
        show = QAction("Open Chest Tracker", menu)
        show.triggered.connect(self.bring_to_front)
        menu.addAction(show)
        self.tray_pause = QAction("Pause", menu)
        self.tray_pause.triggered.connect(self.toggle_pause)
        menu.addAction(self.tray_pause)
        menu.addSeparator()
        leave = QAction("Quit", menu)
        leave.triggered.connect(self.quit_app)
        menu.addAction(leave)
        self.tray_menu = menu
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(
            lambda reason: self.bring_to_front()
            if reason == QSystemTrayIcon.ActivationReason.Trigger else None
        )
        self.tray.show()

    # --- updates ---

    def schedule_update_checks(self) -> None:
        """Checks soon after start and then every few hours, unless the person turned checking off."""
        self.update_timer.stop()
        if self.settings["update_mode"] == "off":
            return
        self.update_timer.start(UPDATE_CHECK_HOURS * 3600 * 1000)
        QTimer.singleShot(8000, self._first_update_check)

    def _first_update_check(self) -> None:
        if self.settings["update_mode"] != "off":
            self.check_for_updates(manual=False)

    def check_for_updates(self, manual: bool) -> None:
        if self.installing:
            return
        if manual:
            self.setup.update_check.setEnabled(False)
            self.setup.show_update_status("Checking\u2026")
        threading.Thread(
            target=lambda: self.update_checked.emit(updater.check_latest(), manual), daemon=True, name="update-check"
        ).start()

    def _on_update_checked(self, result, manual: bool) -> None:
        self.setup.update_check.setEnabled(True)
        if result.status == "error":
            log.info("Update check failed: %s", result.message)
            if manual:
                self.setup.show_update_status(result.message, problem=True)
            return
        if result.status == "current":
            if manual:
                self.setup.show_update_status(f"You're up to date (version {VERSION}).")
            return
        release = result.release
        self.found_update = release
        self.setup.show_update_status(f"Version {release.version} is available.")
        log.info("Update available: %s", release.version)
        self.banner_text.setText(f"<b>Version {release.version}</b> is available. You have {VERSION}.")
        self.banner_install.setEnabled(True)
        self.banner_install.setText("Install and restart")
        self.banner.show()
        if self.settings["update_mode"] == "auto" and not self.auto_timer.isActive():
            self.auto_timer.start(30_000)
            self._try_auto_install()

    def show_update_notes(self) -> None:
        release = self.found_update
        if release:
            QMessageBox.information(self, f"What's new in {release.version}", release.notes or "No notes for this release.")

    def update_is_safe(self) -> bool:
        """An automatic install waits for a quiet moment: no match with chests, and Fortnite not in front."""
        return self.matches.current == 0 and not fortnite_focused() and not self.installing

    def _try_auto_install(self) -> None:
        if self.settings["update_mode"] != "auto" or self.found_update is None or updater.running_exe() is None:
            self.auto_timer.stop()  # not automatic, or running from source: nothing to replace
            return
        if self.update_is_safe():
            self.auto_timer.stop()
            self.install_update()

    def install_update(self) -> None:
        release = self.found_update
        if release is None or self.installing:
            return
        exe = updater.running_exe()
        if exe is None:
            QDesktopServices.openUrl(QUrl(release.page))  # from source: the release page is the way
            return
        self.installing = True
        self.banner_install.setEnabled(False)
        self.banner_text.setText(f"Downloading version {release.version}\u2026")
        self.banner.show()
        target = exe.with_name(exe.name + ".new")

        def work() -> None:
            try:
                updater.download_update(release, target, on_progress=self.update_progress.emit)
            except updater.UpdateError as error:
                self.update_failed.emit(str(error))
                return
            except Exception as error:  # nothing unexpected should leave the banner stuck
                log.warning("Update download failed: %s", error)
                self.update_failed.emit("The update couldn't be downloaded.")
                return
            self.update_ready.emit(release, target)

        threading.Thread(target=work, daemon=True, name="update-download").start()

    def _on_update_progress(self, fraction: float) -> None:
        if self.installing and self.found_update:
            self.banner_text.setText(f"Downloading version {self.found_update.version}\u2026 {round(fraction * 100)}%")

    def _on_update_failed(self, message: str) -> None:
        self.installing = False
        log.warning("Update failed: %s", message)
        self.banner_install.setEnabled(True)
        self.banner_install.setText("Try again")
        self.banner_text.setText(f"<span style='color:{EMBER}'>{message}</span>")
        self.banner.show()
        self.setup.show_update_status(message, problem=True)

    def _on_update_ready(self, release, downloaded) -> None:
        exe = updater.running_exe()
        try:
            updater.install_update(exe, downloaded)
        except updater.UpdateError as error:
            self._on_update_failed(str(error))
            return
        log.info("Updated to %s, restarting", release.version)
        try:
            updater.relaunch(exe)
        except OSError as error:
            log.error("Couldn't start the new version: %s", error)
        self.quit_app()

    def finish_match(self, how: str) -> None:
        """Close the current match (end screen seen, new-match key or button) and start the next."""
        record = self.matches.finish()
        self.overlay.set_match(0)
        self._show_stats()
        if record is None:
            if how != "recap":
                self.tracker.log("This match had no chests, so nothing was saved", ASH)
            return
        log.info("Match finished (%s): %d chests", how, record["chests"])
        word = "chest" if record["chests"] == 1 else "chests"
        self.tracker.log(f"Match finished: {record['chests']} {word}", GOLD)
        scanner = replays.find_scanner() if self.settings["replay_count"] else None
        if scanner is None:
            self._post_match(record["chests"])
            return
        # The post waits for the replay's exact count (or for the search to give up).
        self.tracker.log("Checking the replay for the exact count...", ASH)
        folder = Path(self.settings["replay_folder"] or replays.default_replay_folder())
        first_chest = datetime.fromisoformat(record["start"])

        def work() -> None:
            found = None
            try:
                found = replays.count_match(first_chest, folder, scanner, stop=self._closing.is_set)
            except Exception:
                log.exception("Reading the replay failed")
            if found is None and not self._closing.is_set():
                found = replays.diagnose(first_chest, folder)
            if not self._closing.is_set():
                self.replay_counted.emit(record, found)

        threading.Thread(target=work, daemon=True, name="replay-count").start()

    def _post_match(self, chests: int) -> None:
        if chests < 1:
            return
        if self.settings["match_post"] and self.settings["match_webhook_url"] and self.settings["player_name"]:
            code = self.settings["party_code"]
            # A hand-edited code the bot couldn't read would turn the post into a plain line.
            self.poster.add(chests, "" if party_problem(code) else normalize_party(code))

    def _post_treasures(self, finds: list) -> None:
        """One line per treasure to the match channel, after the match's own post."""
        s = self.settings
        if finds and s["treasure_post"] and s["match_post"] and s["match_webhook_url"] and s["player_name"]:
            for treasure in finds[:5]:
                self.poster.add_text(format_treasure(treasure["name"]))

    def _on_replay_counted(self, record: dict, found) -> None:
        if found is None or isinstance(found, replays.Miss):
            reason = found.reason if found else "unreadable"
            log.info("No readable replay for the match at %s (%s); keeping the screen count", record["start"], reason)
            self.tracker.log("Couldn't read the replay, so the screen count stands", ASH)
            self._replay_missed(reason)
            self._post_match(record["chests"])
            return
        self._replay_worked()
        if found.note:
            log.info("Replay %s: %s", found.file, found.note)
        change = self.matches.apply_replay(record, found.chests, found.opened, found.broken, found.kinds,
                                           found.treasures, found.chest_times)
        log.info("Replay %s: %d chests (%d opened, %d broken); screen had %d",
                 found.file, found.chests, found.opened, found.broken, record["chests"])
        changed = self.stats.add(change) if change else 0
        if changed:
            self.overlay.set_count(self.stats.total)
            if self.settings["webhook_url"] and self.settings["player_name"]:
                self.sender.add(changed)
            self.tracker.stage.set_count(self.stats.total)
        self._show_stats()
        word = "chest" if found.chests == 1 else "chests"
        detail = f" ({found.opened} opened, {found.broken} broken)" if found.broken else ""
        self.tracker.log(f"Replay count: {found.chests} {word}{detail}", GOLD)
        for treasure in found.treasures:
            self.tracker.log(f"Treasure found: {treasure['name']}", GOLD)
        self._post_match(found.chests)
        self._post_treasures(found.treasures)

    def export_match_history(self) -> None:
        name, _ = QFileDialog.getSaveFileName(
            self, "Export match history", str(Path.home() / "chest-tracker-matches.csv"), "CSV file (*.csv)"
        )
        if not name:
            return
        try:
            written = self.matches.export_csv(Path(name))
        except OSError as error:
            QMessageBox.warning(self, "Couldn't save the file", str(error))
            return
        self.tracker.log(f"Exported {written} matches", MINT)

    def set_overlay_match(self, shown: bool) -> None:
        self.settings.set(overlay_show_match=shown)
        self.overlay.set_match_visible(shown)

    def set_overlay_hour(self, shown: bool) -> None:
        self.settings.set(overlay_show_hour=shown)
        self.overlay.set_hour_visible(shown)
        self._update_hour()

    def _update_hour(self) -> None:
        """Keep the overlay's Treasure Hour line current (it only has text during the hunt, near an hour)."""
        text = treasures.hour_status(self.content_store.content, datetime.now(timezone.utc))
        self.overlay.set_hour(text if self.settings["overlay_show_hour"] else "")

    def set_overlay_last(self, shown: bool) -> None:
        self.settings.set(overlay_show_last=shown)
        self.overlay.set_last_visible(shown)

    def share_change(self, amount: int) -> None:
        """Tell the group about a change to the total that didn't come from opening a chest."""
        if amount and self.settings["webhook_url"] and self.settings["player_name"]:
            self.sender.add(amount)

    def group_gap(self) -> int | None:
        """How far your total is from yours on the leaderboard, if this app is the one running the bot."""
        rows = self.leaderboard_seen[0] if self.leaderboard_seen else []
        me = self.settings["player_name"].strip().lower()
        if not me or self.sender.pending:  # nothing to compare, or a post is still on its way
            return None
        mine = next((count for name, count in rows if name.lower() == me), None)
        return None if mine is None else self.stats.total - mine

    def sync_group_total(self) -> int:
        """Post the difference between your total and the leaderboard's. Returns it."""
        gap = self.group_gap() or 0
        self.share_change(gap)
        return gap

    def set_total(self, new_total: int) -> int:
        """Make the lifetime total this number. Returns how much it changed. The change is kept so it can be undone."""
        changed = self.stats.adjust_total(new_total - self.stats.total)
        if changed:
            self.adjustments.add(changed, "hand", f"Total set to {self.stats.total:,}")
            log.info("Total changed by hand by %+d", changed)
            self.share_change(changed)
        self._refresh_total()
        return changed

    def undo_adjustment(self, entry_id: str) -> None:
        entry = self.adjustments.remove(entry_id)
        if entry is None:
            return
        undone = self.stats.adjust_total(-entry["chests"])
        self.share_change(undone)
        if entry["kind"] in ("import", "replay"):
            self.matches.remove_batch(entry["id"])
        if entry["kind"] == "replay":
            self.matches.restore(entry.get("undo", {}).get("restore", []))
        log.info("Undid a total change of %+d", entry["chests"])
        self._refresh_total()

    def apply_import(self, offer) -> int:
        """Add another tracker's total and matches. Returns how many matches were added."""
        entry = self.adjustments.add(offer.chests, "import", offer.note)
        if entry is None:
            return 0
        added = self.matches.add_imported(entry["id"], offer.matches)
        self.share_change(self.stats.adjust_total(offer.chests))
        log.info("Imported %d chests and %d matches from %s", offer.chests, added, offer.source)
        self._refresh_total()
        return added

    def apply_backfill(self, plan) -> int:
        """Apply a plan from counting past replays. Returns how much the total changed."""
        batch = uuid.uuid4().hex[:12]
        undo = self.matches.apply_backfill(batch, plan.new, plan.replaced)
        changed = self.stats.adjust_total(plan.total_change)
        self.share_change(changed)
        note = (f"Counted past replays since {plan.since.date().isoformat()}: "
                f"{len(plan.new)} added, {len(plan.replaced) - plan.refreshed} corrected, {plan.refreshed} filled in")
        self.adjustments.add(changed, "replay", note, undo=undo, entry_id=batch)
        log.info("%s; total changed by %+d", note, changed)
        self._refresh_total()
        return changed

    def _refresh_total(self) -> None:
        self.overlay.set_count(self.stats.total)
        self.tracker.stage.set_count(self.stats.total)
        self._show_stats()
        self.group.update_sync()

    # --- notices and replay health ---

    HEALTH_AFTER = 3  # matches in a row without a readable replay before the app says something

    def _replay_missed(self, reason: str) -> None:
        self.replay_misses += 1
        self.miss_reason = reason
        self._refresh_notice()

    def _replay_worked(self) -> None:
        self.replay_misses = 0
        self.health_dismissed = False
        self._refresh_notice()

    def _notice_items(self) -> list[tuple[str, str]]:
        """What could be shown, most important first: (id, html)."""
        items = []
        if self.replay_misses >= self.HEALTH_AFTER and not self.health_dismissed:
            items.append(("health", f"<b>Replay counting hasn't worked for the last {self.replay_misses} matches.</b> "
                                    f"{replays.MISS_TEXT.get(self.miss_reason, '')} The screen count is being used."))
        if self.settings["show_notices"]:
            for n in self.notice_feed.current(list(self.settings["dismissed_notices"])):
                items.append((f"notice:{n.id}", n.html()))
        return items

    def _refresh_notice(self) -> None:
        items = self._notice_items()
        if not items:
            self._shown_notice = None
            self.notice_banner.hide()
            return
        self._shown_notice = items[0][0]
        self.notice_text.setText(items[0][1])
        self.notice_banner.show()

    def dismiss_notice(self) -> None:
        shown = self._shown_notice
        if shown == "health":
            self.health_dismissed = True
        elif shown and shown.startswith("notice:"):
            kept = [i for i in self.settings["dismissed_notices"] if isinstance(i, str)] + [shown[len("notice:"):]]
            self.settings.set(dismissed_notices=kept[-100:])
        self._refresh_notice()

    # --- backups ---

    def run_auto_backup(self) -> None:
        if self.settings["auto_backup"] and not self._closing.is_set():
            backup.auto_backup(self.folder)

    def restore_backup(self, path: Path) -> str | None:
        """Replace the total, match history and change list with a backup's. Returns a problem, or None if it worked."""
        try:
            data = backup.read(path)
            stats, matches, adjustments, marks = backup.load(data)
        except backup.BadBackup as error:
            return str(error)
        backup.safety_backup(self.folder)
        self.stats.total, self.stats.today, self.stats.day = stats.total, stats.today, stats.day
        self.stats.roll_over()
        self.stats.save()
        self.matches.history = matches.history
        self.matches.save()
        self.adjustments.entries = adjustments.entries
        self.adjustments.save()
        self.treasure_marks.found = marks.found
        self.treasure_marks.set("", False)  # writes the restored ticks to disk
        log.info("Restored a backup: total %d, %d matches", stats.total, len(matches.history))
        self._refresh_total()
        return None

    def _page_shown(self, index: int) -> None:
        page = self.stack.widget(index)
        if page is self.report or page is self.treasures_page:
            page.refresh()

    def refresh_content(self) -> None:
        """Look for newer treasure hunt data in the background."""
        def work() -> None:
            changed = notices_changed = False
            try:
                changed = self.content_store.refresh()
            except Exception:
                log.exception("Refreshing the treasure data failed")
            try:
                notices_changed = self.notice_feed.refresh()
            except Exception:
                log.exception("Refreshing the notices failed")
            if self._closing.is_set():
                return
            if changed:
                self.content_refreshed.emit()
            if notices_changed:
                self.notices_changed.emit()

        threading.Thread(target=work, daemon=True, name="treasure-data").start()

    def open_report(self) -> None:
        """Save the report as a web page next to the app's data and open it."""
        data = report.build(self.matches.history, self.stats.total, self.stats.session)
        path = self.folder / "report.html"
        path.write_text(report.render_html(data, self.settings["clock_format"]), encoding="utf-8")
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def changeEvent(self, event) -> None:
        super().changeEvent(event)
        if (event.type() == event.Type.WindowStateChange and self.isMinimized() and self.settings["minimize_to_tray"]
                and QSystemTrayIcon.isSystemTrayAvailable()):
            QTimer.singleShot(0, self.hide)  # once Windows has finished minimizing

    def open_total_dialog(self) -> None:
        TotalDialog(self).exec()

    def _show_stats(self) -> None:
        self.overlay.set_last(self.matches.last_chests(), self.stats.session, self.matches.session_matches)
        self.tracker.show_matches(self.matches)
        if self.stack.currentWidget() in (self.report, self.treasures_page):
            self.stack.currentWidget().refresh()
        self.tracker.show_stats(self.stats)
        self._show_goals()
        self.tray.setToolTip(f"Chest Tracker: {self.stats.total:,} chests")

    def _show_goals(self) -> None:
        day_goal = goals.clean_goal(self.settings["daily_goal"])
        match_goal = goals.clean_goal(self.settings["match_goal"])
        streak = 0
        if day_goal:
            streak = goals.streak(goals.per_day(self.matches.history), day_goal, date.today(), self.stats.today)
        self.tracker.show_goals(day_goal, self.stats.today, streak, match_goal, self.matches.current)
        self.overlay.set_goals(
            goals.fraction(self.stats.today, day_goal) if day_goal else None,
            goals.fraction(self.matches.current, match_goal) if match_goal else None,
        )

    def _celebrate_goals(self, before_day: int, before_match: int) -> None:
        """A line in the activity list and a sound when this chest took you to a goal."""
        hit = []
        if goals.crossed(before_day, self.stats.today, goals.clean_goal(self.settings["daily_goal"])):
            hit.append(f"Daily goal reached: {self.stats.today:,} chests today")
        if goals.crossed(before_match, self.matches.current, goals.clean_goal(self.settings["match_goal"])):
            hit.append(f"Match goal reached: {self.matches.current:,} chests")
        for line in hit:
            self.tracker.log(line, MINT)
        if hit and self.settings["goal_sound"]:
            self.play_chime()
            QTimer.singleShot(260, self.play_chime)  # twice, so it's different from a normal chest

    def go_to(self, index: int) -> None:
        self.nav.button(index).setChecked(True)
        self.stack.setCurrentIndex(index)

    def bring_to_front(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def missing_setup(self) -> list[str]:
        missing = []
        if not list(self.templates_dir.glob("*.png")):
            missing.append("the chest prompt")
        return missing

    def restart_engine(self) -> None:
        if self.engine:
            self.engine.stop()
            self.engine.join(2)
            self.engine = None
        self._update_notice()
        if self.missing_setup():
            self.set_state("setup")
            return
        threshold = min(0.99, max(0.5, float(self.settings["match_threshold"])))  # the meter's range
        matcher = PromptMatcher.from_folder(self.templates_dir, threshold)
        try:
            remove_code = key_code(self.settings["remove_key"])
        except ValueError as error:
            log.error("Undo key problem: %s. Using F10.", error)
            self.settings.set(remove_key="F10")
            self.setup.remove_capture.set_key("F10")
            self.setup.refresh_steps()
            remove_code = VK_F10
        try:
            pause_code = key_code(self.settings["pause_key"])
        except ValueError as error:
            log.error("Pause key problem: %s. Using F9.", error)
            self.settings.set(pause_key="F9")
            self.setup.pause_capture.set_key("F9")
            self.setup.refresh_steps()
            pause_code = VK_F9
        try:
            match_code = key_code(self.settings["match_key"])
        except ValueError as error:
            log.error("New-match key problem: %s. Using F8.", error)
            self.settings.set(match_key="F8")
            self.setup.match_capture.set_key("F8")
            self.setup.refresh_steps()
            match_code = VK_F8
        try:
            interact = interact_check(self.settings["interact_keys"])
        except (ValueError, RuntimeError) as error:
            log.error("Interact key problem: %s", error)
            self.tracker.log(f"Interact key problem: {error}", EMBER)
            self.set_state("setup")
            return
        self.engine = WatchEngine(
            matcher, interact, self.settings["search_area"],
            self.chest.emit, self.engine_state.emit, self.match_score.emit, self.attempt.emit,
            remove_hotkey=remove_code, pause_hotkey=pause_code, on_pause=self.pause_pressed.emit,
            box_filter=self.box_filter,
            match_hotkey=match_code, on_new_match=self.new_match_pressed.emit,
            recap=self.recap, match_open=lambda: self.matches.current > 0,
            on_match_end=self.match_ended.emit,
        )
        if self.paused:
            self.engine.paused.set()  # stays paused through a settings change
            self.set_state("off")
        self.engine.start()

    def apply_identity(self) -> None:
        self.sender.url = self.settings["webhook_url"]
        self.sender.player = self.settings["player_name"]
        self.sender.wake.set()
        self.poster.url = self.settings["match_webhook_url"]
        self.poster.player = self.settings["player_name"]
        self.poster.wake.set()
        self.restart_engine()

    def _update_notice(self) -> None:
        missing = self.missing_setup()
        self.tracker.notice_frame.setVisible(bool(missing))
        if missing:
            needed = missing[0] if len(missing) == 1 else f"{', '.join(missing[:-1])} and {missing[-1]}"
            self.tracker.notice.setText(f"To start counting, add {needed}.")

    def set_state(self, state: str) -> None:
        self.current_state = state
        color, text = STATES[state]
        self.pill.show_state(color, text)
        if state == "black":
            self.tracker.log("The game looks blank to the app. Set Fortnite to Windowed Fullscreen, and try turning HDR off.", EMBER)
        if state != "watching":
            self.setup.clear_score("Not in game" if state == "waiting" else text)

    def _on_attempt(self, event: str) -> None:
        if event == PENDING:
            self.tracker.stage.show_pending()
        elif event == CANCELLED:
            self.tracker.stage.show_cancelled()
            self.tracker.log("Search cancelled, not counted", ASH)

    def record_chest(self, amount: int, source: str) -> None:
        before_day, before_match = self.stats.today, self.matches.current
        changed = self.stats.add(amount)  # 0 when there was nothing left to take off
        if source == "detected" and changed > 0 and self.settings["chime_enabled"]:
            self.play_chime()
        if changed:
            self.matches.add(changed)
        self.overlay.set_count(self.stats.total, celebrate=source == "detected" and changed > 0)
        self.overlay.set_match(self.matches.current)
        # Only share what really changed, and only if Discord sharing is set up. Sending a
        # -1 for a chest that was never counted would push the group total below the truth.
        if changed and self.settings["webhook_url"] and self.settings["player_name"]:
            self.sender.add(changed)
        self._show_stats()
        if source == "detected":
            self.tracker.stage.show_opened(self.stats.total)
            self.tracker.log("Chest opened", GOLD)
        elif changed:
            self.tracker.stage.set_count(self.stats.total)
            self.tracker.log("Removed a chest", ASH)
        else:
            self.tracker.log("Nothing to remove, the count is already 0", ASH)
        if changed > 0:
            self._celebrate_goals(before_day, before_match)

    def play_chime(self, volume: float | None = None) -> None:
        self.chime.play(self.settings["chime_volume"] if volume is None else volume)

    def toggle_pause(self) -> None:
        self.paused = not self.paused
        text = "Resume tracking" if self.paused else "Pause tracking"
        self.tracker.pause.setText(text)
        self.tray_pause.setText("Resume" if self.paused else "Pause")
        self.overlay.set_paused(self.paused)
        if self.engine:
            # The engine keeps running so it can hear the pause key again, but counts nothing.
            if self.paused:
                self.engine.paused.set()
            else:
                self.engine.paused.clear()
        if self.paused:
            self.set_state("off")
            self.tracker.log("Paused. Nothing is counted until you resume.", ASH)
        else:
            self.tracker.log("Resumed", MINT)
            if self.engine is None:
                self.restart_engine()

    def set_overlay_scale(self, scale: float, save: bool = True) -> None:
        self.overlay.set_scale(scale)
        if save:
            self.settings.set(overlay_scale=self.overlay.scale)
        if self._overlay_screen is not None:
            self._place_overlay(self._overlay_screen)  # keep the badge on screen at the new size

    def set_overlay_opacity(self, opacity: float, save: bool = True) -> None:
        self.overlay.set_opacity(opacity)
        if save:
            self.settings.set(overlay_opacity=self.overlay.opacity)

    def set_overlay_enabled(self, enabled: bool) -> None:
        self.settings.set(overlay_enabled=enabled)
        if not enabled and self._overlay_positioning:
            self.toggle_overlay_positioning()
        self._sync_overlay()

    def toggle_overlay_positioning(self) -> None:
        self._overlay_positioning = not self._overlay_positioning
        self.overlay.positioning = self._overlay_positioning
        if self._overlay_positioning:
            self._overlay_screen = self.screen() or QGuiApplication.primaryScreen()
            self._place_overlay(self._overlay_screen)
            self.overlay.set_click_through(False)
            self.overlay.show()
            self.overlay.raise_()
        else:
            self._sync_overlay()

    def _place_overlay(self, screen) -> None:
        if screen is None:
            return
        self._overlay_screen = screen
        bounds = screen.geometry()
        max_x = max(0, bounds.width() - self.overlay.width())
        max_y = max(0, bounds.height() - self.overlay.height())
        position = self.settings["overlay_position"]
        x = bounds.left() + round(max_x * min(1.0, max(0.0, position[0])))
        y = bounds.top() + round(max_y * min(1.0, max(0.0, position[1])))
        self.overlay.move(x, y)

    def _save_overlay_position(self, point: QPoint) -> None:
        screen = QGuiApplication.screenAt(self.overlay.frameGeometry().center())
        screen = screen or self._overlay_screen or self.overlay.screen()
        if screen is None:
            return
        self._overlay_screen = screen
        bounds = screen.geometry()
        max_x = max(1, bounds.width() - self.overlay.width())
        max_y = max(1, bounds.height() - self.overlay.height())
        left = min(bounds.left() + max_x, max(bounds.left(), point.x()))
        top = min(bounds.top() + max_y, max(bounds.top(), point.y()))
        self.overlay.move(left, top)
        x = (left - bounds.left()) / max_x
        y = (top - bounds.top()) / max_y
        self.settings.set(overlay_position=[x, y])

    def _sync_overlay(self) -> None:
        if self._overlay_positioning:
            self.overlay.set_click_through(False)
            if not self.overlay.isVisible():
                self.overlay.show()
            return
        if not self.settings["overlay_enabled"] or not fortnite_focused():
            self.overlay.set_click_through(False)
            self.overlay.hide()
            return

        bounds = foreground_window_bounds()
        center = QPoint((bounds[0] + bounds[2]) // 2, (bounds[1] + bounds[3]) // 2)
        screen = QGuiApplication.screenAt(center) or self.screen() or QGuiApplication.primaryScreen()
        if screen is not self._overlay_screen:
            self._place_overlay(screen)
        self.overlay.set_click_through(True)
        if not self.overlay.isVisible():
            self.overlay.show()

    def _on_delivery(self, ok: bool, message: str) -> None:
        if ok != self.delivery_ok:
            if ok:
                self.tracker.log("Back online. Your chests were sent.", MINT)
            else:
                self.tracker.log(message, EMBER)
        self.delivery_ok = ok

    def bot_ready(self) -> bool:
        return bool(self.settings["bot_token"]) and self.settings["channel_id"].isdigit()

    def toggle_bot(self) -> None:
        self.group._save()
        if self.bot:
            self.group.toggle.setEnabled(False)
            threading.Thread(target=self.bot.stop, daemon=True).start()
            return
        if not self.bot_ready():
            self._on_bot_status("error", "Enter the bot token and a numeric channel ID first.")
            return
        self.bot = BotRunner(
            self.settings["bot_token"], int(self.settings["channel_id"]),
            self.folder / "chests.db", self.bot_status.emit,
            int(self.settings["match_channel_id"]) if self.settings["match_channel_id"].isdigit() else None,
        )
        self.group.toggle.setText("Stop bot")
        self.bot.start()

    def _on_bot_status(self, status: str, message: str) -> None:
        page = self.group
        color = {"running": MINT, "starting": GOLD, "problem": EMBER, "error": EMBER}.get(status, ASH)
        text = {"running": "Bot online", "starting": "Bot connecting", "problem": "Bot problem", "error": "Bot problem"}.get(status, "Bot off")
        page.pill.show_state(color, text)
        page.message.setText(message)
        if status in ("stopped", "error"):  # the bot's thread has finished
            self.bot = None
        if status in ("problem", "error"):
            page._show_connection(True)
        page.toggle.setEnabled(True)
        page.toggle.setText("Stop bot" if self.bot else "Start bot")
        self._refresh()

    def _refresh(self) -> None:
        self.stats.roll_over()
        self._show_stats()
        path = self.folder / "chests.db"
        rows, total = [], 0
        if path.exists():
            store = Store.read_only(path)
            try:
                rows, total = store.leaderboard(), store.total()
            except sqlite3.Error:  # the bot is creating the database right now
                pass
            finally:
                store.db.close()
        if (rows, total) != self.leaderboard_seen:  # rebuild only when something changed
            self.leaderboard_seen = (rows, total)
            self.group.show_leaderboard(rows, total)

    def closeEvent(self, event) -> None:
        if self._overlay_positioning:
            self.toggle_overlay_positioning()
            self.setup.overlay_position.setText("Set overlay position")
        if not QSystemTrayIcon.isSystemTrayAvailable():
            event.accept()
            self.quit_app()
            return
        event.ignore()
        self.hide()
        if not self.settings["tray_notice_shown"]:
            self.settings.set(tray_notice_shown=True)
            self.tray.showMessage(
                "Chest Tracker is still counting",
                "It's in the system tray. Right-click the icon and select Quit to exit.",
                self.windowIcon(), 5000,
            )

    def quit_app(self) -> None:
        self._shut_down()
        QApplication.quit()

    def _shut_down(self) -> None:
        self._closing.set()
        self.content_timer.stop()
        self.backup_timer.stop()
        self.hour_timer.stop()
        self.refresh_timer.stop()
        self.overlay_timer.stop()
        self.overlay.close()
        if self.engine:
            self.engine.stop()
            self.engine.join(2)
        if self.bot:
            self.bot.stop()
        self.tray.hide()
        deadline = time.monotonic() + 2
        while (self.sender.pending or self.poster.queue) and time.monotonic() < deadline:
            time.sleep(0.1)
