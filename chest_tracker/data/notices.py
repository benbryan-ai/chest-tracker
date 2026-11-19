"""Short messages from the developer (for example "a Fortnite update broke replay reading"), without a new release.

The app reads notices.json from the project's GitHub page. Only plain text is used and every field is checked.
A message can be limited to dates and to app versions, and each person can dismiss it.
"""

import html
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

import requests

from chest_tracker.system import updater
from chest_tracker.system.version import REPO, VERSION

log = logging.getLogger("chest-tracker")

URL = f"https://raw.githubusercontent.com/{REPO}/main/notices.json"
MAX_BYTES = 40_000
MAX_NOTICES = 10
LEVELS = ("info", "warning")


@dataclass(frozen=True)
class Notice:
    id: str
    level: str
    title: str
    text: str
    start: datetime | None
    end: datetime | None
    min_version: str | None
    max_version: str | None

    def active(self, now: datetime, version: str = VERSION) -> bool:
        if (self.start and now < self.start) or (self.end and now >= self.end):
            return False
        current = updater.parse_version(version)
        for bound, below in ((self.min_version, True), (self.max_version, False)):
            wanted = updater.parse_version(bound) if bound else None
            if wanted and current:
                if below and current[0] < wanted[0]:
                    return False
                if not below and current[0] > wanted[0]:
                    return False
        return True

    def html(self) -> str:
        title = f"<b>{html.escape(self.title)}</b>: " if self.title else ""
        return title + html.escape(self.text)


def _moment(value) -> datetime | None:
    if value is None:
        return None
    moment = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if moment.tzinfo is None:
        raise ValueError("no timezone")
    return moment.astimezone(timezone.utc)


def parse(data) -> list[Notice]:
    """The notices in a file. A bad entry is skipped; a file that isn't ours gives nothing."""
    if not isinstance(data, dict) or data.get("schema") != 1 or not isinstance(data.get("notices"), list):
        return []
    found: list[Notice] = []
    for raw in data["notices"][:MAX_NOTICES]:
        try:
            if not isinstance(raw, dict):
                raise ValueError
            ident, text = raw["id"], raw["text"]
            title = raw.get("title") or ""
            level = raw.get("level", "info")
            if not (isinstance(ident, str) and 0 < len(ident) <= 60 and isinstance(text, str) and 0 < len(text) <= 400
                    and isinstance(title, str) and len(title) <= 80 and level in LEVELS):
                raise ValueError
            bounds = []
            for key in ("minVersion", "maxVersion"):
                value = raw.get(key)
                if value is not None and (not isinstance(value, str) or updater.parse_version(value) is None):
                    raise ValueError
                bounds.append(value)
            found.append(Notice(ident, level, title.strip(), text.strip(), _moment(raw.get("from")),
                                _moment(raw.get("to")), bounds[0], bounds[1]))
        except (KeyError, ValueError, TypeError):
            continue
    return found


class NoticeFeed:
    def __init__(self, get: Callable = requests.get, url: str = URL):
        self.get, self.url = get, url
        self.items: list[Notice] = []

    def refresh(self) -> bool:
        """Fetch the file. True if the list of notices changed. Never raises."""
        try:
            response = self.get(self.url, timeout=10, headers={"Accept": "application/json"})
            if response.status_code != 200 or len(response.content) > MAX_BYTES:
                return False
            fresh = parse(json.loads(response.content.decode("utf-8-sig")))
        except (requests.RequestException, ValueError, UnicodeDecodeError) as error:
            log.info("Notices not refreshed: %s", error)
            return False
        changed = fresh != self.items
        self.items = fresh
        return changed

    def current(self, dismissed: list[str], now: datetime | None = None, version: str = VERSION) -> list[Notice]:
        moment = now or datetime.now(timezone.utc)
        return [n for n in self.items if n.id not in dismissed and n.active(moment, version)]
