"""Starting the app with Windows (minimized to the tray), through the current user's Run list."""

import sys
from pathlib import Path

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE = "Chest Tracker"
ARGUMENT = "--minimized"


def command(exe: Path) -> str:
    return f'"{exe}" {ARGUMENT}'


def _winreg():
    if sys.platform != "win32":
        return None
    import winreg

    return winreg


def supported(exe: Path | None) -> bool:
    """Only the installed program can start itself: a run from source has no program to point at."""
    return exe is not None and _winreg() is not None


def is_enabled() -> bool:
    reg = _winreg()
    if reg is None:
        return False
    try:
        with reg.OpenKey(reg.HKEY_CURRENT_USER, RUN_KEY) as key:
            reg.QueryValueEx(key, VALUE)
            return True
    except OSError:
        return False


def set_enabled(on: bool, exe: Path | None) -> bool:
    """Turn it on or off. Returns False if Windows refused or there is nothing to start."""
    reg = _winreg()
    if reg is None:
        return False
    try:
        with reg.OpenKey(reg.HKEY_CURRENT_USER, RUN_KEY, 0, reg.KEY_SET_VALUE) as key:
            if on:
                if exe is None:
                    return False
                reg.SetValueEx(key, VALUE, 0, reg.REG_SZ, command(exe))
            else:
                try:
                    reg.DeleteValue(key, VALUE)
                except FileNotFoundError:
                    pass
        return True
    except OSError:
        return False
