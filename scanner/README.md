# chest-scan

Counts the chests a player searched (with `--json` it also lists where each was searched, as `ChestSpots`) in a Fortnite replay, including broken ones the screen can't see.
Replays are only readable after the match ends.

    chest-scan [--json] [--timeout SECONDS] [replay or folder]...

With no path it scans `%LOCALAPPDATA%\FortniteGame\Saved\Demos`.
Status per file: `ok`, `live` (still recording), `incomplete` (no key, match didn't finish), `error`.

Credits: see THIRD_PARTY_NOTICES.md.
