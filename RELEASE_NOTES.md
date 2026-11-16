# Release notes

Each release's text on GitHub, and the "What's new" box in the app, is the section below with that version's heading.
Add a new `## vX.Y.Z` section at the top before tagging a release.

## v1.5.0

- **Treasures tab** for the Treasure Hunters hunt: how many treasures you've found, this week's prizes (found or not yet), your chances for each kind of prize, upcoming Treasure Hours, and your latest finds.
- Treasures are read from the replay after each match (the replay records the golden chest's prize), so they appear for matches counted from a replay, including **Count my past replays**. The tracker log shows "Treasure found: ..." when one turns up.
- **Your chances** use the odds in the hunt data and the boosted odds during Treasure Hours, applied to each chest by the time it was searched. Chests counted only from the screen have just a match time, so they count at normal odds. The chance is shown as a percentage that never claims 100%.
- **Hunt data stays current without a new version.** The weeks, prizes, odds and Treasure Hours come from ChestCounter's `content.json` (LED-N, MIT). A copy is built in; the app checks GitHub every couple of hours and only accepts a file that passes a strict check and has a higher revision, so a broken file can't replace a good one. Without a connection it just uses what it has.
- ChestCounter's other messages in that file (about its own tool) are not shown here.

## v1.4.0

- **Report tab.** Your total, this session, matches, average per match and best match; a bar chart of chests per day (last 14 days); chests by type (chest, rare chest, buried chest and so on); and your latest matches, 10 at a time. **Open as a web page** saves `report.html` in the app's data folder and opens it in your browser; it's a single file you can keep or share, and it needs nothing from the internet.
- Chest types come from the replay, so matches counted from the screen show as "Type not recorded", and matches counted from a replay (new ones, or through **Count my past replays**) fill in the types.
- **Settings tab.** Choose the replay folder (or keep the default), 12 or 24 hour clock, minimize to the system tray, and start with Windows (minimized to the tray, in the installed .exe only). There's also a button that opens the data folder.
- Replay-counted matches are saved with their chest types, and the export and the report use the clock you chose.

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
