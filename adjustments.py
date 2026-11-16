"""The list of hand-made changes to the lifetime total (typed totals and imports), so each can be undone."""

import uuid
from datetime import datetime
from pathlib import Path

from settings import _write_json, read_json

MAX_ENTRIES = 500
KINDS = ("hand", "import", "replay")


class Adjustments:
    """Each entry: id, chests (+/-), when, kind ("hand" or "import"), note, and for imports a batch id."""

    def __init__(self, path: Path):
        self.path = path
        self.entries: list[dict] = []
        saved = read_json(path) or {}
        try:
            for e in saved.get("entries", []):
                entry = {
                    "id": str(e["id"]), "chests": int(e["chests"]), "when": str(e["when"]),
                    "kind": e["kind"] if e.get("kind") in KINDS else "hand", "note": str(e.get("note", "")),
                }
                if isinstance(e.get("undo"), dict):
                    entry["undo"] = e["undo"]
                if entry["chests"] != 0 or entry.get("undo"):
                    self.entries.append(entry)
        except (KeyError, TypeError, ValueError, AttributeError):
            self.entries = []
        self.entries = self.entries[-MAX_ENTRIES:]

    def add(self, chests: int, kind: str, note: str, now: datetime | None = None, undo: dict | None = None,
            entry_id: str | None = None) -> dict | None:
        """`undo` is whatever is needed to take the change back besides the chest number."""
        if chests == 0 and not undo:
            return None
        entry = {
            "id": entry_id or uuid.uuid4().hex[:12], "chests": int(chests),
            "when": (now or datetime.now()).isoformat(timespec="seconds"),
            "kind": kind if kind in KINDS else "hand", "note": note,
        }
        if undo:
            entry["undo"] = undo
        self.entries = (self.entries + [entry])[-MAX_ENTRIES:]
        self.save()
        return entry

    def remove(self, entry_id: str) -> dict | None:
        for entry in self.entries:
            if entry["id"] == entry_id:
                self.entries = [e for e in self.entries if e is not entry]
                self.save()
                return entry
        return None

    def has_import(self, note: str) -> bool:
        return any(e["kind"] == "import" and e["note"] == note for e in self.entries)

    def save(self) -> None:
        _write_json(self.path, {"entries": self.entries})
