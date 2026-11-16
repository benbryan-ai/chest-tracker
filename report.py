"""The report: totals, an average, the best match, chests per day, chest types and the latest matches."""

import html
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from timefmt import format_stamp

DAYS_SHOWN = 14
UNSORTED = "Type not recorded"  # matches counted from the screen don't say what type each chest was


@dataclass
class ReportData:
    total: int
    session: int
    match_count: int
    chests_in_matches: int
    average: float
    best: int
    days: list[tuple[date, int]] = field(default_factory=list)  # oldest first, every day filled in
    kinds: list[tuple[str, int]] = field(default_factory=list)  # biggest first
    latest: list[dict] = field(default_factory=list)  # newest first: everything the log kept


def build(history: list[dict], total: int, session: int, today: date | None = None) -> ReportData:
    today = today or date.today()
    per_day: dict[date, int] = {}
    kinds: dict[str, int] = {}
    for m in history:
        try:
            day = datetime.fromisoformat(m["start"]).date()
        except (KeyError, ValueError):
            continue
        per_day[day] = per_day.get(day, 0) + m["chests"]
        recorded = m.get("kinds") or {}
        for name, count in recorded.items():
            kinds[name] = kinds.get(name, 0) + count
        rest = m["chests"] - sum(recorded.values())
        if rest > 0:
            kinds[UNSORTED] = kinds.get(UNSORTED, 0) + rest
    chests = sum(m["chests"] for m in history)
    ordered = sorted(history, key=lambda m: m["start"], reverse=True)
    return ReportData(
        total=total, session=session, match_count=len(history), chests_in_matches=chests,
        average=chests / len(history) if history else 0.0,
        best=max((m["chests"] for m in history), default=0),
        days=[(today - timedelta(days=n), per_day.get(today - timedelta(days=n), 0)) for n in range(DAYS_SHOWN - 1, -1, -1)],
        kinds=sorted(kinds.items(), key=lambda item: (item[0] == UNSORTED, -item[1], item[0])),
        latest=ordered,
    )


def match_line(m: dict, clock: str) -> str:
    """One match as a short line, like 'Nov 14, 9:32 PM: 22 chests (3 broken)'."""
    word = "chest" if m["chests"] == 1 else "chests"
    broken = f" ({m['broken']} broken)" if m.get("broken") else ""
    return f"{format_stamp(datetime.fromisoformat(m['start']), clock)}: {m['chests']:,} {word}{broken}"


def render_html(data: ReportData, clock: str = "auto", generated: datetime | None = None) -> str:
    """A page that stands alone: no scripts, nothing loaded from the internet."""
    esc = html.escape
    top = max((n for _, n in data.days), default=0) or 1
    bars = "".join(
        f'<div class="bar"><div class="fill" style="height:{round(100 * n / top)}%"></div>'
        f'<span class="n">{n}</span><span class="d">{d.day}</span></div>'
        for d, n in data.days
    )
    kinds = "".join(f"<tr><td>{esc(k)}</td><td class=\"r\">{n:,}</td></tr>" for k, n in data.kinds) \
        or '<tr><td colspan="2">Nothing yet</td></tr>'
    latest = "".join(f"<li>{esc(match_line(m, clock))}</li>" for m in data.latest[:50]) or "<li>No matches yet</li>"
    stamp = (generated or datetime.now()).strftime("%Y-%m-%d %H:%M")
    tiles = "".join(
        f'<div class="tile"><div class="v">{v}</div><div class="l">{esc(l)}</div></div>'
        for v, l in (
            (f"{data.total:,}", "chests in total"), (f"{data.session:,}", "this session"),
            (f"{data.match_count:,}", "matches"), (f"{data.average:.1f}", "chests per match"),
            (f"{data.best:,}", "best match"),
        )
    )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Chest Tracker report</title>
<style>
body{{margin:0;background:#0b0b0d;color:#e9e4d6;font:15px/1.5 Segoe UI,system-ui,sans-serif}}
main{{max-width:860px;margin:0 auto;padding:28px 18px 48px}}
h1{{font-size:26px;margin:0 0 4px}} h2{{font-size:17px;margin:28px 0 10px;color:#d9b84a}}
.muted{{color:#8d887a;font-size:13px}}
.tiles{{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin-top:16px}}
.tile{{background:#17171b;border:1px solid #2a2a30;border-radius:10px;padding:12px 14px}}
.v{{font-size:28px;font-weight:700;color:#f3cf5a}} .l{{color:#8d887a;font-size:13px}}
.chart{{display:flex;gap:6px;align-items:flex-end;height:150px;background:#17171b;border:1px solid #2a2a30;border-radius:10px;padding:14px 12px 4px}}
.bar{{flex:1;display:flex;flex-direction:column;justify-content:flex-end;align-items:center;height:100%;position:relative}}
.fill{{width:100%;background:#d9b84a;border-radius:4px 4px 0 0;min-height:1px}}
.n{{font-size:11px;color:#e9e4d6}} .d{{font-size:11px;color:#8d887a}}
table{{width:100%;border-collapse:collapse;background:#17171b;border:1px solid #2a2a30;border-radius:10px}}
td{{padding:8px 12px;border-bottom:1px solid #2a2a30}} .r{{text-align:right}}
ul{{list-style:none;padding:0;margin:0;background:#17171b;border:1px solid #2a2a30;border-radius:10px}}
li{{padding:8px 12px;border-bottom:1px solid #2a2a30}}
</style></head><body><main>
<h1>Chest Tracker report</h1><div class="muted">Made {esc(stamp)}</div>
<div class="tiles">{tiles}</div>
<h2>Chests per day (last {DAYS_SHOWN} days)</h2><div class="chart">{bars}</div>
<h2>By chest type</h2><table>{kinds}</table>
<h2>Latest matches</h2><ul>{latest}</ul>
</main></body></html>
"""
