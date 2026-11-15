# Release notes

Each release's text on GitHub, and the "What's new" box in the app, is the section below with that version's heading.
Add a new `## vX.Y.Z` section at the top before tagging a release.

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
