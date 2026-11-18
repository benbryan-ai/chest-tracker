"""The message format the watcher posts and the bot reads back."""

import re
from urllib.parse import urlsplit

_PATTERN = re.compile(r"\U0001F4E6 chests \(([+-]\d+)\)")


def format_delta(amount: int) -> str:
    return f"\U0001F4E6 chests ({amount:+d})"


def parse_delta(content: str) -> int | None:
    """Return the chest change in a tracker message, or None for anything else."""
    match = _PATTERN.fullmatch(content.strip())
    return int(match.group(1)) if match else None


# Discord refuses webhook posts whose username contains these words, whatever the case.
_BANNED_NAME_WORDS = ("discord", "clyde")
MAX_NAME_LENGTH = 32
_WEBHOOK_HOSTS = {"discord.com", "discordapp.com", "ptb.discord.com", "canary.discord.com"}


def name_problem(name: str) -> str | None:
    """Why Discord would refuse this player name, or None if it is fine.

    The name is sent as the webhook's username, so it has to follow Discord's rules.
    An empty name is allowed (it just means "don't share to Discord").
    """
    name = name.strip()
    if not name:
        return None
    if len(name) > MAX_NAME_LENGTH:
        return f"Use {MAX_NAME_LENGTH} characters or fewer."
    lowered = name.lower()
    for word in _BANNED_NAME_WORDS:
        if word in lowered:
            return f'Discord doesn\'t allow names that contain "{word}". Pick another name.'
    return None


def is_webhook_url(url: str) -> bool:
    """True for a https://discord.com/api/webhooks/... link (and Discord's other official hosts)."""
    parts = urlsplit(url.strip())
    return (
        parts.scheme == "https"
        and (parts.hostname or "").lower() in _WEBHOOK_HOSTS
        and parts.path.startswith("/api/webhooks/")
    )


# --- match posts: one line per finished match, and the party code that groups players ---

_MATCH_PATTERN = re.compile(
    r"\U0001F3AE (\d+) chests? this match(?: · party ([A-Z0-9]{3,12}))?"
)
PARTY_PATTERN = re.compile(r"[A-Z0-9]{3,12}")


def normalize_party(code: str) -> str:
    """A party code as it is shared: upper case, no spaces."""
    return "".join(code.split()).upper()


def party_problem(code: str) -> str | None:
    """Why this party code can't be used, or None if it is fine (empty means no party)."""
    code = normalize_party(code)
    if not code or PARTY_PATTERN.fullmatch(code):
        return None
    return "Use 3 to 12 letters or numbers, with no spaces or symbols."


TREASURE_PREFIX = "\U0001F3F4\u200D\u2620\uFE0F Found a treasure: "


def format_treasure(name: str) -> str:
    """A plain line for a treasure find. The bot doesn't read it; it's there for people in the channel."""
    clean = " ".join(re.sub(r"[`*_~|<>@#\[\]()]", "", name).split())[:100]
    return f"{TREASURE_PREFIX}{clean or 'something golden'}"


# --- match stats: one line per finished match, read by the bot to build the leaderboards ---

_STATS_PATTERN = re.compile(
    r"\U0001F4CA <t:(\d{9,11}):[tTdDfFR]> · (\d+) chests? · (\d+) opened · (\d+) broken · (\d+) treasures?"
)
MAX_MATCH_CHESTS = 600


def format_match_stats(start: int, chests: int, opened: int, broken: int, treasures: int) -> str:
    """A line for a finished match. Discord shows the <t:...> part as the match's time in each reader's own zone."""
    return (
        f"\U0001F4CA <t:{int(start)}:f> · {chests} chest{'' if chests == 1 else 's'} · {opened} opened · "
        f"{broken} broken · {treasures} treasure{'' if treasures == 1 else 's'}"
    )


def parse_match_stats(content: str) -> tuple[int, int, int, int, int] | None:
    """(start, chests, opened, broken, treasures) from a match stats line, or None for anything else."""
    found = _STATS_PATTERN.fullmatch(content.strip())
    if not found:
        return None
    start, chests, opened, broken, treasures = (int(g) for g in found.groups())
    if chests < 1 or chests > MAX_MATCH_CHESTS or opened > chests or broken > chests or treasures > 50:
        return None
    return start, chests, opened, broken, treasures


def format_match(chests: int, party: str = "") -> str:
    text = f"\U0001F3AE {chests} chest{'' if chests == 1 else 's'} this match"
    party = normalize_party(party)
    return f"{text} · party {party}" if party else text


def parse_match(content: str) -> tuple[int, str] | None:
    """(chests, party code or "") from a match post, or None for anything else."""
    found = _MATCH_PATTERN.fullmatch(content.strip())
    if not found:
        return None
    return int(found.group(1)), found.group(2) or ""
