# Release notes

Each release's text on GitHub, and the "What's new" box in the app, is the section below with that version's heading.
Add a new `## vX.Y.Z` section at the top before tagging a release.

## v1.3.1

- **Count my past replays.** In **Edit total...**, a new button reads the replays Fortnite has saved on your PC and counts them. You pick the season start date (the Treasure Hunters season began 2026-11-01); older replays are ignored.
- Matches the app never saw are added. Matches it counted from the screen are replaced by the replay's exact count, but only where a replay covers them: counts from before your oldest replay stay as they are.
- You see how many matches will be added, how many corrected and what your total becomes, and confirm before anything changes. The whole thing can be undone from the list of changes, and running it again doesn't count anything twice.

## v1.3.0

- **Edit your total.** The tracker page has an **Edit total...** button. Type what your total should be; the difference is saved in a list of changes, and any change can be undone. Today's and this session's counts aren't affected, and typed changes aren't sent to Discord.
- **Import from ChestCounter or chest-tracker.** If either is installed, the same window offers to bring in its total and its match history (so averages and best match include them). Imports follow the other app's own counting rules, so the number matches what it shows, and an import can be undone as one step.
- **Session and last match.** The tracker page shows how many matches you've finished this session and your last match's count. The overlay has a new bottom row with the last match and this session (turn it off in Setup under the overlay options).

## v1.2.0

- **Exact counts from Fortnite's replay.** After each match the app reads Fortnite's replay file and uses its chest count, which also includes chests you broke instead of opened. The screen count is used if the replay can't be read, or if you turn this off in Setup ("Replay counting").
- When the replay's count differs from the screen count, your total, today's count and the match history are corrected, and the match report goes to Discord with the corrected number. The log shows how many were opened and how many broken.
- Fortnite's **Record Replays** setting must be on. Replays can only be read once the match is over, so the count may take up to a few minutes to appear.
- Exported match history now has opened, broken and "counted from" columns.
- Replay reading uses code from ChestCounter by LED-N and FortniteReplayDecompressor (both MIT); see `scanner/THIRD_PARTY_NOTICES.md`.

## v1.1.1

- Updates: the app can now check GitHub for a new version. In Setup, choose to be told about new versions (the default), have them installed automatically, or turn checking off. **Check for updates** checks right away.
- A banner shows what's new in a version, with an **Install and restart** button. Downloads are checked against GitHub's checksum before anything is replaced, and the old version is restored if the install fails.
- Automatic installs only happen when no match is in progress and Fortnite isn't the active window.

## v1.1.0

- Match posts: one line per finished match can go to a second Discord webhook (the match reports channel), with an option to turn it off.
- Group game report: players who enter the same party code get one combined report from the bot, posted 3 minutes after the first player finishes.

## v1.0.5

- Fixed the chime not playing on Windows.

## v1.0.4

- Chests per match: a "this match" count on the Tracker page and overlay, saved match history with average, median and best, a new-match key (F8) and button, and automatic match ending from the end-of-match screen. History can be exported as a CSV file.

## v1.0.3

- Ammo and fruit boxes are no longer counted as chests, and a chest is counted when you open it and the search finishes even if you look away right after.
