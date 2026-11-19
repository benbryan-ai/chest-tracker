"""Chest Tracker: starts the app."""

import logging
import os
import sys
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path

from PySide6.QtGui import QIcon
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication, QSystemTrayIcon

from chest_tracker.data.settings import data_dir, import_old_setup
from chest_tracker.gui.ui import MainWindow
from chest_tracker.system import updater
from chest_tracker.system.paths import app_folder, resource_folder
from chest_tracker.system.version import VERSION

INSTANCE_NAME = "ChestTrackerSingleInstance"


def set_up_logging(folder: Path) -> None:
    handler = RotatingFileHandler(
        folder / "chest-tracker.log", maxBytes=500_000, backupCount=1, encoding="utf-8"
    )
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger = logging.getLogger("chest-tracker")
    logger.setLevel(logging.INFO)
    logger.addHandler(handler)
    sys.excepthook = lambda kind, value, trace: logger.error(
        "Unhandled error", exc_info=(kind, value, trace)
    )


def already_running() -> bool:
    """Ask a running copy to show itself. Two copies would count every chest twice."""
    socket = QLocalSocket()
    socket.connectToServer(INSTANCE_NAME)
    if socket.waitForConnected(300):
        socket.disconnectFromServer()
        return True
    return False


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Chest Tracker")
    app.setQuitOnLastWindowClosed(False)

    if os.environ.pop("CHEST_TRACKER_UPDATED", None):
        # Just installed an update: the old copy is still closing. Give it a few seconds to let go.
        deadline = time.monotonic() + 10
        while already_running() and time.monotonic() < deadline:
            time.sleep(0.3)
    if already_running():
        return 0

    folder = data_dir()
    set_up_logging(folder)
    log = logging.getLogger("chest-tracker")
    if updater.running_exe():
        updater.clean_up_leftovers(updater.running_exe())
    if import_old_setup(app_folder(), folder):
        log.info("Imported the old setup from %s", app_folder())

    icon = QIcon(str(resource_folder() / "assets" / "icon.png"))
    app.setWindowIcon(icon)
    window = MainWindow(folder, icon)
    if not ("--minimized" in sys.argv and QSystemTrayIcon.isSystemTrayAvailable()):
        window.show()  # started by Windows with --minimized: stay in the tray

    QLocalServer.removeServer(INSTANCE_NAME)
    server = QLocalServer()
    server.newConnection.connect(window.bring_to_front)
    server.listen(INSTANCE_NAME)

    log.info("App started (version %s)", VERSION)
    code = app.exec()
    log.info("App closed")
    return code


if __name__ == "__main__":
    sys.exit(main())
