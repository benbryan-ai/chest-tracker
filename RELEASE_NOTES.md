# Release notes

Each release's text on GitHub, and the "What's new" box in the app, is the section below with that version's heading.
Add a new `## vX.Y.Z` section at the top before tagging a release.

## v2.0.3

More on the chest map. If you're updating from an older version, the notes for v2.0.2 and the ones before it (below) also apply.

- **A single match.** The Map tab's period list now has **A single match...**, with a second list of your recent matches (those with positions) to pick from.
- **Most searched.** Under the controls, a line lists the areas where you searched the most chests, such as "Near Lil' Uzi's Stronghold (106)". It names the nearest town within about 300 m and "Elsewhere" otherwise. The town spots are approximate.

## v2.0.2

Finer control over the chest map. If you're updating from an older version, the notes for v2.0.1 and the ones before it (below) also apply.

- **Smaller resizing steps.** Scrolling on the map now changes the dots' size by 2% a notch instead of 10%, and Shift+scroll by half a percent.
- **Dots size controls.** New **-** and **+** buttons resize the dots a little at a time, and you can type exactly how many kilometres the picture shows across.
- **Arrow keys.** Click the map, then use the arrow keys to move the dots a pixel at a time (five with Shift).
- **Save as this picture's default.** Once the dots line up, save that alignment and **Reset position** will come back to it.

## v2.0.1

The chest map and a console counter. If you're updating from an older version, the notes for v1.11.0 and the ones before it (below) also apply.

- **Chest map.** A new **Map** tab shows where you searched chests, from your replays, as glowing spots over a kilometre grid. Filter by all matches, this season, this week or your last match.
- **Use a map picture.** Replays don't include the island's picture, so choose one yourself with **Map picture...** (a screenshot of the in-game map works). A picture of the whole island (like the ones on map sites) lines up by itself; for other pictures, drag the dots to move them and scroll to resize them. Your alignment is remembered.
- **Tidier code.** The Python files are now grouped into folders inside `chest_tracker/` (counting, data, stats, group, gui, system). Nothing changes in how the app works; the README lists what's where.
- **Older matches.** Positions are only saved for matches counted from a replay with this version. Run **Count my past replays** once (Edit total...) to fill in your earlier matches.
- **Console counter.** `console/index.html` is a free phone-friendly page for console players: tap +1 for each chest and it posts to your group's Discord webhook in the app's format. Turn on GitHub Pages (Settings > Pages > Source: GitHub Actions) to host it.

## v1.11.0

The share card. If you're updating from an older version, the notes for v1.10.0 and the ones before it (below) also apply.

- **Share card.** On the **Report** tab, **Share card...** makes a picture of your **week**, **last 7 days**, **month** or **season**: total chests, matches, best match, average, opened and broken chests, treasures, your goal streak, and a chart of chests per day (or per week for a season).
- **Copy, save or post.** Copy the picture to paste into Discord, save it as a PNG, or **Post to Discord** with your webhook (it goes to the match channel if you have one set, otherwise your chest channel).

## v1.10.0

Fortnite stats on the leaderboards. If you're updating from an older version, the notes for v1.9.0 and the ones before it (below) also apply.

- **Compare Fortnite stats.** The Leaderboards tab has four new categories: Fortnite wins, eliminations, K/D and win rate, with the same side-by-side table. They cover **This season** (Fortnite's own season) and **All time**; Fortnite doesn't have a weekly number. K/D and win rate need 10 matches to rank.
- **It's opt-in.** On the Fortnite Stats tab, tick **Share my stats with the group**. Your app then looks up your own overall numbers with your own Fortnite-API key and sends them to your group's channel every few hours while the app is open (only when they've changed). Your key and Epic name are never sent, and anyone who doesn't tick it simply doesn't appear on those boards.
- **`/leaderboard` in Discord** understands the new categories too.
- The bot must be updated by the person running it, and each player updates their own app to share. Players whose Fortnite stats aren't public can't be looked up by Fortnite-API, so they won't show.

## v1.9.0

Leaderboards. If you're updating from an older version, the notes for v1.8.0, v1.7.2 and v1.7.1 (below) also apply.

- **The Group tab is now Leaderboards.** Pick a period (**This week**, **This season** or **All time**) and a category: most chests, best match, average per match, chests opened, chests broken, treasures found, or matches played. Below the ranking, a table shows everyone's numbers side by side.
- **Match stats.** Each finished match now sends a short stats line to your chest channel (its time, chests, opened, broken and treasures). The bot uses these for the new boards. All-time chests still come from the running total, so edits and imports are included.
- **Share my match history.** One button sends your matches since the season began, so the boards include games you played before this version.
- **`/leaderboard` in Discord** now takes a period and a category, and shows this week's most chests by default.
- **Who needs to update.** The player running the bot, and everyone who wants to appear on the new boards (besides most chests, all time). Older apps keep working: their chest counts still add up.

## v1.8.0

Goals. If you're updating from an older version, the notes for v1.7.2 and v1.7.1 (below) also apply.

- **Daily goal.** Set a chests-per-day target in **Settings**. The Tracker tab shows a progress bar under today's count, plus your streak (days in a row that reached the goal).
- **Per-match goal.** The same for each match, shown under "This match".
- **On the overlay.** Thin progress bars along the bottom of the overlay show how far through the match goal and daily goal you are. They only appear when a goal is set.
- **Goal reached.** A line appears in Recent activity, and a double chime plays (it can be turned off in **Settings**). Each goal is announced once.
- The goal boxes in Settings now match the dark theme.

## v1.7.2

Fixes the group leaderboard missing changes you make to your own total. If you're updating from an older version, the notes for v1.7.1 (below) also apply: they cover everything since v1.5.0.

- **Your group total now follows your edits.** Edit total, importing from another tracker, and *Count my past replays* now post their change to your group's leaderboard, and undoing one posts the reverse. Before, only chests counted while playing reached the group.
- **Sync my total.** If your leaderboard number is already out of step (for example you added chests before this update), the Group tab shows how far off it is with a **Sync my total** button that posts the difference. It appears on the PC running the bot. Anyone else can ask the bot's owner to use `/add` with their name and the missing amount.
- A fix to the Treasures tab: prize names containing "&" were shown with an underlined letter instead of the "&".
- A fix to the Group tab: the "no chests on the leaderboard yet" message could stay on screen behind the rows.
- The app now looks for updates in the new project address, `benbryan-ai/chest-tracker`. Versions before 1.7.1 can't update themselves from here, so download this once by hand.

## v1.7.1

This release also includes everything from v1.6.0, v1.6.1 and v1.7.0, listed below.

- **Tick off treasures by hand.** On the Treasures tab every prize in the week has a checkbox, so you can add the ones the replays didn't show. Prizes found in a replay are ticked for you and locked. Your ticks count towards "treasures found" and are included in backups.
- **Past weeks stay up.** A week picker on the Treasures tab lets you look back at any week that has started, with its prizes, what you found, and your chances for that week.

### Also new since v1.5.0

**Treasure posts in Discord.** When a replay shows you found a treasure, a line like "Found a treasure: Solid Gold ..." goes to the match channel after that match's own post. There's a checkbox next to *Post each match to Discord* to turn it off. The group bot ignores these lines.
**Treasure Hour on the overlay.** During the hunt, a small row shows how long the current Treasure Hour has left, or when the next one is expected. It can be turned off under the overlay options.
**Imports bring treasures too.** Importing from ChestCounter now also brings its treasure finds and the time of each chest.
**Fills in older replay-counted matches.** *Count my past replays* now also fills in chest types, treasures and chest times on matches already counted from a replay. Counts and totals don't change.
**Match details.** Click a match in the Report tab to see its chests, types, treasures and how it was counted.
**Backup and restore.** *Back up now...* and *Restore from a backup...* in Settings, plus an automatic daily backup (last 7 kept).
**Replay counting warning.** A banner explains why if the replay can't be read for 3 matches in a row.
**Messages from the developer.** Short plain-text notices (dismissable, can be turned off in Settings) without needing a new release.

## v1.7.0

- **Treasure posts in Discord.** When a replay shows you found a treasure, a line like "Found a treasure: Solid Gold ..." goes to the match channel after that match's own post. There's a checkbox next to *Post each match to Discord* to turn it off. The group bot ignores these lines, so the group report is unchanged.
- **Treasure Hour on the overlay.** During the hunt, a small row shows "TREASURE HOUR: 40 min left" while one is on, or "Treasure Hour in 2h 10m (expected)" when one is coming within 6 hours. It disappears when there's nothing to show, and can be turned off under the overlay options.
- **Imports bring treasures too.** Importing from ChestCounter now also brings its treasure finds (with prize names filled in from the hunt data) and the time of each chest, so the Treasures tab and your chances include your history from there.

## v1.6.1

- **Fills in older replay-counted matches.** Running **Count my past replays** (in *Edit total...*) now also updates matches that were already counted from a replay before chest types, treasures and chest times were saved. Their chest count stays the same; only the details are filled in, and your total doesn't change. The confirm window says how many matches this applies to, and it can be undone like the rest.
- **Match details.** Click a match in the Report tab to see when it started, how many chests were opened and broken, the chest types, any treasures and how it was counted. Matches with treasures say so in the list.

## v1.6.0

- **Backup and restore.** In **Settings**, *Back up now...* saves your total, match history and list of changes to one file, and *Restore from a backup...* brings it back (after showing what's in it and asking first). Your current data is saved before any restore, so you can go back. Discord settings are never included in a backup.
- **Automatic backups.** Once a day the app saves a backup in the `backups` folder inside its data folder and keeps the last 7. You can turn this off in Settings.
- **Replay counting warning.** If the replay can't be read for 3 matches in a row, a banner says why: the replay folder wasn't found, no replay was saved (is Record Replays on?), or a replay was found but couldn't be read (a Fortnite update may have changed the format). The screen count keeps being used meanwhile.
- **Messages from the developer.** The app can show a short message (for example "a Fortnite update broke replay reading, a fix is coming") without a new release. They come from `notices.json` in this repo, only plain text is shown, you can dismiss each one, and you can turn them off in Settings.

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
