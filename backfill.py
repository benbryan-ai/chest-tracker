"""Counts the replays already on this PC: adds matches the app never saw and corrects the ones it counted by screen.

Only matches that a replay covers are touched. Counts from before the oldest replay stay as they are.
"""

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable

from replays import SLACK, ReplayCount, run_scan

BATCH = 8  # files per scanner run, so one slow replay can't stall the rest


@dataclass
class BackfillPlan:
    since: datetime
    replays_in_season: int = 0
    new: list[dict] = field(default_factory=list)  # matches to add
    replaced: list[dict] = field(default_factory=list)  # {"old": [records], "new": record}
    already: int = 0  # replays whose match already carries the replay's count
    total_change: int = 0

    @property
    def nothing_to_do(self) -> bool:
        return not self.new and not self.replaced


def _record(r: ReplayCount) -> dict:
    return {"start": r.start.isoformat(timespec="seconds"), "end": r.end.isoformat(timespec="seconds"),
            "chests": r.chests, "opened": r.opened, "broken": r.broken, "source": "replay", "kinds": r.kinds}


def scan_folder(
    scanner: Path, folder: Path, since: datetime,
    progress: Callable[[int, int], None] = lambda done, total: None,
    scan: Callable[[Path, list[Path]], list[ReplayCount]] = run_scan,
) -> list[ReplayCount]:
    """Read every finished replay in the folder written since `since`."""
    try:
        files = sorted(
            (p for p in folder.glob("*.replay") if datetime.fromtimestamp(p.stat().st_mtime) >= since),
            key=lambda p: p.stat().st_mtime,
        )
    except OSError:
        return []
    found: list[ReplayCount] = []
    for index in range(0, len(files), BATCH):
        batch = files[index : index + BATCH]
        found += scan(scanner, batch)
        progress(min(index + BATCH, len(files)), len(files))
    return found


def make_plan(counts: list[ReplayCount], history: list[dict], since: datetime) -> BackfillPlan:
    """What would change. Matches are paired with replays the same way live counting does."""
    plan = BackfillPlan(since=since)
    taken: set[int] = set()
    for r in sorted(counts, key=lambda c: c.start):
        if r.start < since or r.chests < 1:
            continue
        plan.replays_in_season += 1
        covered = [
            (i, m) for i, m in enumerate(history)
            if i not in taken and r.start - SLACK <= datetime.fromisoformat(m["start"]) <= r.end + SLACK
        ]
        taken.update(i for i, _ in covered)
        if covered and all(m.get("source") == "replay" for _, m in covered) and len(covered) == 1 \
                and covered[0][1]["chests"] == r.chests:
            plan.already += 1
            continue
        record = _record(r)
        if covered:
            old = [m for _, m in covered]
            plan.replaced.append({"old": old, "new": record})
            plan.total_change += r.chests - sum(m["chests"] for m in old)
        else:
            plan.new.append(record)
            plan.total_change += r.chests
    return plan
