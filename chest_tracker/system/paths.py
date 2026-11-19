"""Where the app's own files live: the bundled assets, and the folder the program runs from."""

import sys
from pathlib import Path

# chest_tracker/system/paths.py -> the project folder is three levels up
SOURCE_ROOT = Path(__file__).resolve().parents[2]


def resource_folder() -> Path:
    """Where bundled files (assets/, chest-scan.exe) are: the unpacked bundle in the .exe, the project folder otherwise."""
    return Path(getattr(sys, "_MEIPASS", SOURCE_ROOT))


def app_folder() -> Path:
    """The folder holding the .exe, or the project folder when run from source."""
    return Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else SOURCE_ROOT
