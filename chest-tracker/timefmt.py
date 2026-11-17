"""Times as the person likes to read them: 12 hour, 24 hour, or whatever their PC uses."""

from datetime import datetime

CLOCKS = (("auto", "Match my PC"), ("12", "12 hour (9:30 PM)"), ("24", "24 hour (21:30)"))


def uses_12_hour(clock: str) -> bool:
    if clock == "12":
        return True
    if clock == "24":
        return False
    try:
        from PySide6.QtCore import QLocale

        pattern = QLocale.system().timeFormat(QLocale.FormatType.ShortFormat).lower()
        return "ap" in pattern or "a" in pattern.replace("hh", "").replace("mm", "")
    except Exception:
        return False


def format_time(moment: datetime, clock: str = "auto") -> str:
    if uses_12_hour(clock):
        return moment.strftime("%I:%M %p").lstrip("0")
    return moment.strftime("%H:%M")


def format_stamp(moment: datetime, clock: str = "auto") -> str:
    """Date and time, like 'Nov 14, 9:32 PM'."""
    return f"{moment.strftime('%b')} {moment.day}, {format_time(moment, clock)}"
