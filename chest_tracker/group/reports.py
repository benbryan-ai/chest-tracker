"""The group game report: teammates' match counts combined into one post."""

from collections.abc import Callable
from dataclasses import dataclass, field

WAIT_SECONDS = 180.0  # after the first player reports, wait this long for the rest of the team
MAX_PLAYERS = 4  # a full squad: no point waiting any longer once everyone has reported
MIN_PLAYERS = 2  # one player's post is already their own summary


@dataclass
class _Game:
    first_at: float
    counts: dict[str, int] = field(default_factory=dict)  # player (lower case) -> chests
    names: dict[str, str] = field(default_factory=dict)  # player (lower case) -> name as shown


@dataclass
class Report:
    party: str
    players: list[tuple[str, int]]  # most chests first

    @property
    def total(self) -> int:
        return sum(chests for _, chests in self.players)


class GroupReports:
    """Collects match posts per party code, and says when a report is ready.

    Time is passed in, so this has no clock of its own and is easy to test.
    """

    def __init__(self, wait: float = WAIT_SECONDS):
        self.wait = wait
        self.games: dict[str, _Game] = {}

    def add(self, party: str, player: str, chests: int, now: float) -> None:
        game = self.games.setdefault(party, _Game(first_at=now))
        key = player.lower()
        game.counts[key] = chests  # a repeat from the same player replaces the first
        game.names[key] = player

    def pop_due(self, now: float) -> list[Report]:
        """Reports ready to post. Each game is returned once and then forgotten."""
        ready = []
        for party, game in list(self.games.items()):
            full = len(game.counts) >= MAX_PLAYERS
            if full or now - game.first_at >= self.wait:
                del self.games[party]
                if len(game.counts) >= MIN_PLAYERS:
                    players = sorted(
                        ((game.names[k], c) for k, c in game.counts.items()),
                        key=lambda row: (-row[1], row[0].lower()),
                    )
                    ready.append(Report(party, players))
        return ready


def format_report(report: Report, escape: Callable[[str], str] = lambda text: text) -> str:
    top = report.players[0][1]
    lines = [f"\U0001F3AE **Group game report** · party `{report.party}`"]
    for rank, (name, chests) in enumerate(report.players, 1):
        trophy = " \U0001F3C6" if chests == top else ""
        lines.append(f"**{rank}.** {escape(name)}: {chests:,} chest{'' if chests == 1 else 's'}{trophy}")
    lines.append(f"**Team total: {report.total:,} chests** · {len(report.players)} players")
    return "\n".join(lines)
