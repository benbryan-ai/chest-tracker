"""Discord bot: counts the chest messages the app posts and answers slash commands."""

import asyncio
import logging
import threading
import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

import discord
from discord import app_commands

import boards
from protocol import parse_delta, parse_match, parse_match_stats
from reports import GroupReports, format_report
from store import Store

log = logging.getLogger("chest-tracker")


def ingest(store: Store, message) -> bool:
    """Count a message if it is a tracker post from a webhook. Returns True if newly counted."""
    if message.webhook_id is None:
        return False
    amount = parse_delta(message.content)
    if amount is None:
        stats = parse_match_stats(message.content)
        if stats is None:
            return False
        start, chests, opened, broken, treasures = stats
        if start > message.created_at.timestamp() + 86400:  # a match can't start in the future
            return False
        store.record_match(message.author.name, start, chests, opened, broken, treasures)
        return True
    return store.record_message(
        message.id, message.author.name, amount, int(message.created_at.timestamp())
    )


def collect_match(reports: GroupReports, message, now: float) -> bool:
    """Note a party match post from a webhook. Returns True if it joins a group game."""
    if message.webhook_id is None:
        return False
    parsed = parse_match(message.content)
    if parsed is None or not parsed[1]:
        return False  # not a match post, or a solo one: that line is already its own summary
    reports.add(parsed[1], message.author.name, parsed[0], now)
    return True


class ChestBot(discord.Client):
    def __init__(
        self, store: Store, channel_id: int, on_status: Callable[[str, str], None],
        match_channel_id: int | None = None, season_start: str = "",
    ):
        intents = discord.Intents.none()
        intents.guilds = True
        intents.guild_messages = True
        intents.message_content = True
        super().__init__(intents=intents, allowed_mentions=discord.AllowedMentions.none())
        self.store = store
        self.channel_id = channel_id
        # The same channel for both would send every chest post down the wrong path.
        self.match_channel_id = match_channel_id if match_channel_id != channel_id else None
        self.reports = GroupReports()
        self._report_task: asyncio.Task | None = None
        self.on_status = on_status
        self.tree = app_commands.CommandTree(self)
        self.synced = False
        register_commands(self.tree, store, season_start)

    async def on_ready(self):
        try:
            channel = await self.fetch_channel(self.channel_id)
            if not self.synced:
                # Syncing to the one server makes the commands appear straight away.
                self.tree.copy_global_to(guild=channel.guild)
                await self.tree.sync(guild=channel.guild)
                self.synced = True
            await self.catch_up(channel)
            if self.match_channel_id and self._report_task is None:
                self._report_task = asyncio.create_task(self._post_reports())
        except discord.NotFound:
            self.on_status("problem", "Channel not found. Check the channel ID, then restart the bot.")
        except discord.Forbidden:
            self.on_status("problem", "The bot can't access that channel. Check its permissions, then restart it.")
        else:
            log.info("Bot ready as %s in #%s", self.user, channel.name)
            self.on_status("running", f"Online as {self.user}, counting in #{channel.name}")

    async def catch_up(self, channel) -> None:
        """Count whatever was posted while the bot was offline."""
        last = self.store.get_last_message_id()
        after = discord.Object(last) if last else None
        counted = 0
        async for message in channel.history(limit=None, after=after, oldest_first=True):
            counted += ingest(self.store, message)
            self.store.set_last_message_id(message.id)
        if counted:
            log.info("Caught up on %d missed message(s)", counted)

    async def _post_reports(self) -> None:
        """Every few seconds, post the group reports whose waiting time is up."""
        while True:
            await asyncio.sleep(5)
            for report in self.reports.pop_due(time.monotonic()):
                try:
                    channel = await self.fetch_channel(self.match_channel_id)
                    await channel.send(format_report(report, discord.utils.escape_markdown))
                except discord.HTTPException as error:
                    log.warning("Couldn't post the group report: %s", error.__class__.__name__)
                    self.on_status("problem", "The bot can't post in the match reports channel. Check its permissions.")

    async def on_message(self, message: discord.Message):
        if self.match_channel_id and message.channel.id == self.match_channel_id:
            collect_match(self.reports, message, time.monotonic())
            return
        if message.channel.id != self.channel_id:
            return
        ingest(self.store, message)
        self.store.set_last_message_id(message.id)


def register_commands(tree: app_commands.CommandTree, store: Store, season_start: str = "") -> None:
    @tree.command(name="chests", description="Show how many chests have been opened")
    @app_commands.describe(player="Whose count to show (leave empty for everyone)")
    async def chests(interaction: discord.Interaction, player: str | None = None):
        who = player or "Everyone"
        await interaction.response.send_message(
            f"\U0001F4E6 **{who}**: {store.total(player):,} chests opened "
            f"({store.today(player):,} today)"
        )

    @tree.command(name="leaderboard", description="Show the leaderboard (this week by default)")
    @app_commands.describe(period="This week, this season or all time", category="What to rank players by")
    @app_commands.choices(
        period=[app_commands.Choice(name=text, value=key) for key, text in boards.PERIODS],
        category=[app_commands.Choice(name=text, value=key) for key, text in boards.CATEGORIES],
    )
    async def leaderboard(interaction: discord.Interaction, period: str = "week", category: str = "chests"):
        since = boards.period_start(period, datetime.now(), season_start)
        rows = store.player_stats(None if period == "all" else since if since is not None else 0)
        await interaction.response.send_message(
            boards.format_board(rows, period, category, escape=discord.utils.escape_markdown)
        )

    @tree.command(name="add", description="Correct a count (use a negative number to remove)")
    @app_commands.describe(player="Player name, as on the leaderboard", amount="Chests to add")
    @app_commands.default_permissions(manage_guild=True)
    async def add(interaction: discord.Interaction, player: str, amount: int):
        store.add_manual(player, amount, int(time.time()))
        await interaction.response.send_message(
            f"**{player}** now has {store.total(player):,} chests."
        )

    @tree.command(name="reset", description="Erase one player's chest count")
    @app_commands.describe(player="Player name, as on the leaderboard")
    @app_commands.default_permissions(manage_guild=True)
    async def reset(interaction: discord.Interaction, player: str):
        removed = store.reset_player(player)
        text = f"Reset **{player}** to 0." if removed else f"No chests found for **{player}**."
        await interaction.response.send_message(text)


class BotRunner:
    """Runs the bot on its own thread so the app window stays responsive."""

    def __init__(
        self, token: str, channel_id: int, db_path: Path, on_status, match_channel_id: int | None = None,
        season_start: str = "",
    ):
        self.token = token
        self.channel_id = channel_id
        self.match_channel_id = match_channel_id
        self.season_start = season_start
        self.db_path = db_path
        self.on_status = on_status
        self.loop: asyncio.AbstractEventLoop | None = None
        self.client: ChestBot | None = None
        self.thread = threading.Thread(target=self._run, daemon=True)

    def start(self) -> None:
        self.on_status("starting", "Connecting to Discord...")
        self.thread.start()

    def stop(self) -> None:
        if self.loop and self.client and self.loop.is_running():
            asyncio.run_coroutine_threadsafe(self.client.close(), self.loop)
        self.thread.join(5)

    def _run(self) -> None:
        store = Store(self.db_path)  # SQLite connections stay on the thread that made them
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.client = ChestBot(
            store, self.channel_id, self.on_status, self.match_channel_id, self.season_start
        )
        status, message = "stopped", "Bot is off."
        try:
            self.loop.run_until_complete(self.client.start(self.token))
        except discord.LoginFailure:
            status, message = "error", "Discord rejected the bot token. Copy a new one from the portal."
        except discord.PrivilegedIntentsRequired:
            status, message = "error", "Turn on Message Content Intent on the portal's Bot page."
        except Exception as error:
            log.exception("Bot stopped unexpectedly")
            status, message = "error", f"Bot stopped: {error.__class__.__name__}. See the log."
        finally:
            store.db.close()
            self.loop.close()
        log.info("Bot status: %s (%s)", status, message)
        self.on_status(status, message)
