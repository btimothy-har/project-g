import discord
import asyncio
import coc
import pendulum
import logging
import random

from typing import *
from mongoengine import *

from art import text2art
from discord.ext import tasks
from redbot.core import commands
from redbot.core.bot import Red
from redbot.core.utils import AsyncIter, bounded_gather

from .api_client import BotClashClient as client
from .cog_coc_client import ClashOfClansClient

from .coc_objects.clans.mongo_clan import db_Clan
from .coc_objects.players.mongo_player import db_Player
from .coc_objects.events.mongo_events import db_ClanWar, db_RaidWeekend

from .tasks.player_tasks import PlayerLoop
from .tasks.clan_tasks import ClanLoop
from .tasks.war_tasks import ClanWarLoop
from .tasks.raid_tasks import ClanRaidLoop
from .tasks.guild_tasks import DiscordGuildLoop

from .coc_objects.season.season import aClashSeason
from .coc_objects.clans.mongo_clan import db_AllianceClan
from .discord.guild import aGuild
from .discord.user_application import listener_user_application
from .discord.recruiting_reminder import RecruitingReminder

from .utils.components import clash_embed

bot_client = client()

############################################################
############################################################
#####
##### TASKS COG
#####
############################################################
############################################################
class ClashOfClansTasks(commands.Cog):
    """
    Background task handler for Clash of Clans.
    """

    __author__ = "bakkutteh"
    __version__ = "2023.10.2"

    def __init__(self,bot:Red):
        self.bot = bot
        self.last_coc_task_error = None

        self._master_task_lock = asyncio.Lock()
        self._task_lock = asyncio.Lock()
        self.task_lock_timestamp = None
        self.task_semaphore_limit = 10000
        self.task_semaphore = asyncio.Semaphore(self.task_semaphore_limit)

        self.queue_lock = asyncio.Lock()

        self.refresh_lock = asyncio.Lock()
        self.last_task_refresh = None

        self.refresh_recruiting_lock = asyncio.Lock()

        self.api_maintenance = False

    def format_help_for_context(self, ctx: commands.Context) -> str:
        context = super().format_help_for_context(ctx)
        return f"{context}\n\nAuthor: {self.__author__}\nVersion: {self.__version__}"
    
    @property
    def task_lock(self) -> asyncio.Lock:
        if self._master_task_lock.locked():
            return self._master_task_lock
        return self._task_lock

    @property
    def client(self) -> ClashOfClansClient:
        return bot_client.bot.get_cog('ClashOfClansClient')

    @property
    def coc_main_log(self) -> logging.Logger:
        return bot_client.coc_main_log

    @property
    def coc_data_log(self) -> logging.Logger:
        return bot_client.coc_data_log

    ##################################################
    ### COG LOAD
    ##################################################
    async def cog_load(self):
        while True:
            if getattr(bot_client,'_api_logged_in',False):
                break
            await asyncio.sleep(1)
        
        asyncio.create_task(self.start_recruiting_loop())
        
        bot_client.coc.add_events(
            self.clash_maintenance_start,
            self.clash_maintenance_complete
            )

        self.api_semaphore_limit = int((len(bot_client.coc.http._keys)*20))
        self.api_semaphore = asyncio.Semaphore(self.api_semaphore_limit)

        self.clan_queue_semaphore = asyncio.Semaphore(int(self.api_semaphore_limit / 10))
        self.player_queue_semaphore = asyncio.Semaphore(int(self.api_semaphore_limit / 10))
        
        self.coc_main_log.info(f"Found {len(bot_client.coc.http._keys):,} API Keys, setting semaphore limit at {self.api_semaphore_limit:,}.")

        self.refresh_discord_tasks.start()
        self.coc_task_controller.start()
        self.coc_data_queue.start()
        self.refresh_coc_tasks.start()
    
    async def start_recruiting_loop(self):
        await bot_client.bot.wait_until_red_ready()
        async with self.refresh_recruiting_lock:
            posts = RecruitingReminder.get_all()
            async for post in AsyncIter(posts):
                count = 0
                while True:
                    try:
                        count += 1
                        await post.refresh_reminder()
                        break
                    except Exception:
                        if count > 30:
                            self.coc_main_log.exception(f"Could not refresh reminder for {post.id} - {post}")
                            break
                        await asyncio.sleep(1)        
            self.refresh_recruiting_reminders.start()

    ##################################################
    ### COG LOAD
    ##################################################
    async def cog_unload(self):
        self.refresh_discord_tasks.cancel()
        self.refresh_coc_tasks.cancel()
        self.coc_data_queue.cancel()
        self.coc_task_controller.cancel()

        self.coc_main_log.info(f"Stopped Clash Data Loop.")

        for handler in self.coc_main_log.handlers:
            self.coc_main_log.removeHandler(handler)
        for handler in self.coc_data_log.handlers:
            self.coc_data_log.removeHandler(handler)

        stop_tasks = []
        stop_tasks.extend([asyncio.create_task(i.stop()) for i in DiscordGuildLoop.loops()])
        stop_tasks.extend([asyncio.create_task(i.stop()) for i in ClanRaidLoop.loops()])
        stop_tasks.extend([asyncio.create_task(i.stop()) for i in ClanWarLoop.loops()])
        stop_tasks.extend([asyncio.create_task(i.stop()) for i in ClanLoop.loops()])
        stop_tasks.extend([asyncio.create_task(i.stop()) for i in PlayerLoop.loops()])    
    
    @commands.Cog.listener("on_member_join")
    async def new_discord_member(self,member:discord.Member):        
        linked_accounts = await bot_client.get_linked_players(member.id)
        async for tag in AsyncIter(linked_accounts):
            player = await self.client.fetch_player(tag)
            if player.discord_user == 0:                    
                player.discord_user = member.id
    
    @commands.Cog.listener("on_guild_channel_create")
    async def recruiting_ticket_listener(self,channel):

        application_id = None
        await asyncio.sleep(2)        
        
        guild = aGuild(channel.guild.id)
        if len(guild.apply_panels) == 0:
            return
        
        async for message in channel.history(limit=1,oldest_first=True):
            for embed in message.embeds:
                if embed.footer.text == "Application ID":                    
                    application_id = embed.description
                    break
        if not application_id:
            return
        
        await listener_user_application(channel, application_id)

    ############################################################
    #####
    ##### CLASH LOOP TASK HELPERS
    #####
    ############################################################
    async def create_player_task(self,player_tag:str):
        loop = PlayerLoop(player_tag)
        if not loop.loop_active:
            await loop.start()
            return player_tag
    
    async def create_clan_task(self,clan_tag:str):
        loop = ClanLoop(clan_tag)
        if not loop.loop_active:
            await loop.start()
            return clan_tag
    
    async def create_war_task(self,clan_tag:str):
        loop = ClanWarLoop(clan_tag)
        if not loop.loop_active:
            await loop.start()
            return clan_tag
    
    async def create_raid_task(self,clan_tag:str):
        loop = ClanRaidLoop(clan_tag)
        if not loop.loop_active:
            await loop.start()
            return clan_tag
    
    ############################################################
    #####
    ##### CLASH OF CLANS CORE DATA LOOPS
    #####
    ############################################################
    @tasks.loop(seconds=1)
    async def coc_task_controller(self):
        if self.task_lock.locked():
            return
        async with self._task_lock:
            self.task_lock_timestamp = pendulum.now()
            while self.api_semaphore._value < self.api_semaphore_limit:
                await asyncio.sleep(0)

    @tasks.loop(seconds=60)
    async def coc_data_queue(self):
        if self.queue_lock.locked():
            return        
        try:
            async with self.queue_lock:                
                await asyncio.gather(
                    self.load_clan_queue(),
                    self.load_player_queue(),
                    return_exceptions=True)

        except Exception as exc:
            await self.bot.send_to_owners(f"An error occured during COC Data Queue. Check logs for details."
                + f"```{exc}```")
            self.coc_main_log.exception(
                f"Error in Clash Data Loop"
                )
    
    async def load_clan_queue(self):        
        async def fetch_clan(clan_tag):
            await self.client.fetch_clan(clan_tag)
            bot_client.clan_cache.remove_from_queue(clan_tag)
        
        clan_queue = bot_client.clan_cache.queue.copy()
        bounded_gather(*(fetch_clan(c) for c in clan_queue),
            semaphore=self.clan_queue_semaphore,
            return_exceptions=True
            )
        
    async def load_player_queue(self):
        async def fetch_player(player_tag):
            await self.client.fetch_player(player_tag)
            bot_client.player_cache.remove_from_queue(player_tag)
        
        player_queue = bot_client.player_cache.queue.copy()
        bounded_gather(*(fetch_player(p) for p in player_queue),
            semaphore=self.player_queue_semaphore,
            return_exceptions=True
            )

    @tasks.loop(seconds=30)
    async def refresh_coc_tasks(self):
        def predicate_clan_not_in_loop(clan):
            if clan.tag not in [i.tag for i in ClanLoop.loops() if i.loop_active]:
                return True
            return False        
        def predicate_player_not_in_loop(player):
            return player.tag not in [i.tag for i in PlayerLoop.loops() if i.loop_active]
        
        if self.refresh_lock.locked():
            return
        
        try:
            async with self.refresh_lock:
                clans = AsyncIter(bot_client.clan_cache.values)
                async for clan in clans.filter(predicate_clan_not_in_loop):
                    await self.create_clan_task(clan.tag)

                players = AsyncIter(bot_client.player_cache.values)
                async for player in players.filter(predicate_player_not_in_loop):
                    await self.create_player_task(player.tag)
                
                alliance_clans = AsyncIter(db_AllianceClan.objects().only('tag'))
                async for clan in alliance_clans:
                    if clan.tag not in [i.tag for i in ClanWarLoop.loops() if i.loop_active]:
                        await self.create_war_task(clan.tag)
                    if clan.tag not in [i.tag for i in ClanRaidLoop.loops() if i.loop_active]:
                        await self.create_raid_task(clan.tag)

                await self._season_check()

        except Exception as exc:
            await self.bot.send_to_owners(f"An error occured during Task Refresh. Check logs for details."
                + f"```{exc}```")
            self.coc_main_log.exception(
                f"Error in Clash Data Loop"
                )        
        finally:
            self.last_task_refresh = pendulum.now()
    
    async def _season_check(self):
        season = aClashSeason.get_current_season()

        if season.id == bot_client.current_season.id:
            return None
        
        async with self._master_task_lock:
            while self.task_semaphore._value < self.task_semaphore_limit:
                await asyncio.sleep(0)
            self.current_season = season
        
        self.coc_main_log.info(f"New Season Started: {season.id} {season.description}\n"
            + text2art(f"{season.id}",font="small")
            )
        self.coc_data_log.info(f"New Season Started: {season.id} {season.description}\n"
            + text2art(f"{season.id}",font="small")
            )
        
        await bot_client.bot.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.playing,
                name=f"start of the {self.current_season.short_description} Season! Clash on!")
                )

        bank_cog = bot_client.bot.get_cog('Bank')
        if bank_cog:
            await bank_cog.member_legend_rewards()
            await bank_cog.apply_bank_taxes()
            await bank_cog.month_end_sweep()
    
    @tasks.loop(minutes=5)
    async def refresh_discord_tasks(self):
        guilds = AsyncIter(self.bot.guilds)
        async for guild in guilds:
            if guild.id not in [i.guild_id for i in DiscordGuildLoop.loops() if i.loop_active]:
                loop = DiscordGuildLoop(guild.id)
                if not loop.loop_active:
                    await loop.start()
    
    @tasks.loop(minutes=5.0)
    async def refresh_recruiting_reminders(self):
        if self.refresh_recruiting_lock.locked():
            return
        
        try:
            async with self.refresh_recruiting_lock:
                posts = RecruitingReminder.get_all()
                async for post in AsyncIter(posts):
                    await post.send_reminder()

        except Exception:
            await self.bot.send_to_owners(f"An error occured during Recruiting Loop. Check logs for details.")
            self.coc_main_log.exception(f"Error in Recruiting Loop")
    
    ############################################################
    #####
    ##### CLASH OF CLANS MAINTENANCE
    #####
    ############################################################
    @coc.ClientEvents.maintenance_start()
    async def clash_maintenance_start(self):
        self.api_maintenance = True
        await self._master_task_lock.acquire()

        self.coc_main_log.warning(f"Clash Maintenance Started. Sync loops locked.\n"
            + text2art("Clash Maintenance Started",font="small")
            )
        await bot_client.update_bot_status(
            cooldown=0,
            text="Clash Maintenance!"
            )
    
    @coc.ClientEvents.maintenance_completion()
    async def clash_maintenance_complete(self,time_started):
        self.api_maintenance = False
        if self._master_task_lock.locked():
            self._master_task_lock.release()

        maint_start = pendulum.instance(time_started)
        maint_end = pendulum.now()

        self.coc_main_log.warning(f"Clash Maintenance Completed. Maintenance took: {maint_end.diff(maint_start).in_minutes()} minutes. Sync loops unlocked.\n"
            + text2art("Clash Maintenance Completed",font="small")
            )
        await bot_client.update_bot_status(
            cooldown=0,
            text="Clash of Clans!"
            )
    
    @commands.group(name="cocdata")
    @commands.is_owner()
    async def command_group_clash_data(self,ctx):
        """Manage the Clash of Clans Data Client."""
        if not ctx.invoked_subcommand:
            pass

    @command_group_clash_data.command(name="status")
    @commands.is_owner()
    async def subcommand_clash_data_status(self,ctx):
        """Clash of Clans Data Status."""

        if not getattr(bot_client,'_is_initialized',False):
            return await ctx.reply("Clash of Clans API Client not yet initialized.")
        
        embed = await clash_embed(ctx,
            title="**Clash of Clans Data Report**",
            message="Last Refresh: " + (f"<t:{self.last_task_refresh.int_timestamp}:R>" if self.last_task_refresh else "None")
            )
        embed.add_field(
            name="**Tasks Client**",
            value="```ini"
                + f"\n{'[Master Lock]':<15} " + ('Locked' if self._master_task_lock.locked() else 'Unlocked')
                + f"\n{'[Control Lock]':<15} " + (f"Locked ({self.task_lock_timestamp.format('HH:mm:ss')})" if self._task_lock.locked() and self.task_lock_timestamp else 'Unlocked')
                + f"\n{'[Running]':<15} " + f"{self.task_semaphore_limit - self.task_semaphore._value:,}"
                + "```",
            inline=False
            )
        embed.add_field(
            name="**API Client**",
            value="```ini"
                + f"\n{'[Maintenance]':<15} {self.api_maintenance}"
                + f"\n{'[API Keys]':<15} {len(bot_client.coc.http._keys)}"
                + f"\n{'[API Requests]':<15} {self.api_semaphore._value:,} / {self.api_semaphore_limit} (Waiting: {len(self.api_semaphore._waiters) if self.api_semaphore._waiters else 0:,})"
                + "```",
            inline=False
            )
        embed.add_field(
            name="**Players**",
            value="```ini"
                + f"\n{'[Mem/DB/Queue]':<15} {len(bot_client.player_cache):,} / {len(db_Player.objects()):,} (Queue: {len(bot_client.player_cache.queue):,})"
                + f"\n{'[Loops]':<15} {len([i for i in PlayerLoop.loops() if i.loop_active]):,}"
                + f"\n{'[Work Time]':<15} {round(PlayerLoop.worktime_avg())}s (min: {round(PlayerLoop.worktime_min())}s, max: {round(PlayerLoop.worktime_max())}s)"
                + f"\n{'[Run Time]':<15} {round(PlayerLoop.runtime_avg())}s (min: {round(PlayerLoop.runtime_min())}s, max: {round(PlayerLoop.runtime_max())}s)"
                + "```",
            inline=False
            )
        embed.add_field(
            name="**Clans**",
            value="```ini"
                + f"\n{'[Mem/DB/Queue]':<15} {len(bot_client.clan_cache):,} / {len(db_Clan.objects()):,} (Queue: {len(bot_client.clan_cache.queue):,})"
                + f"\n{'[Loops]':<15} {len([i for i in ClanLoop.loops() if i.loop_active]):,}"
                + f"\n{'[Work Time]':<15} {round(ClanLoop.worktime_avg())}s (min: {round(ClanLoop.worktime_min())}s, max: {round(ClanLoop.worktime_max())}s)"
                + f"\n{'[Run Time]':<15} {round(ClanLoop.runtime_avg())}s (min: {round(ClanLoop.runtime_min())}s, max: {round(ClanLoop.runtime_max())}s)"
                + "```",
            inline=False
            )
        embed.add_field(
            name="**Clan Wars**",
            value="```ini"
                + f"\n{'[Database]':<15} {len(db_ClanWar.objects()):,}"
                + f"\n{'[Loops]':<15} {len([i for i in ClanWarLoop.loops() if i.loop_active]):,}"
                + f"\n{'[Work Time]':<15} {round(ClanWarLoop.worktime_avg())}s"
                + f"\n{'[Run Time]':<15} {round(ClanWarLoop.runtime_avg())}s"
                + "```",
            inline=True
            )
        embed.add_field(
            name="**Capital Raids**",
            value="```ini"
                + f"\n{'[Database]':<15} {len(db_RaidWeekend.objects()):,}"
                + f"\n{'[Loops]':<15} {len([i for i in ClanRaidLoop.loops() if i.loop_active]):,}"
                + f"\n{'[Work Time]':<15} {round(ClanRaidLoop.worktime_avg())}s"
                + f"\n{'[Run Time]':<15} {round(ClanRaidLoop.runtime_avg())}s"
                + "```",
            inline=True
            )        
        embed.add_field(
            name="**Discord Guilds**",
            value="```ini"
                + f"\n{'[Available]':<15} {len(self.bot.guilds):,}"
                + f"\n{'[Loops]':<15} {len([i for i in DiscordGuildLoop.loops() if i.loop_active]):,}"
                + "```",
            inline=False
            )
        await ctx.reply(embed=embed)
    
    @command_group_clash_data.command(name="lock")
    @commands.is_owner()
    async def subcommand_clash_data_lock(self,ctx):
        """Lock the Clash of Clans Data Loop."""
        if self.task_lock.locked():
            await ctx.reply("Clash Data Loop is already locked.")
        else:
            await self._master_task_lock.acquire()
            await ctx.reply("Clash Data Loop locked.")
    
    @command_group_clash_data.command(name="unlock")
    @commands.is_owner()
    async def subcommand_clash_data_unlock(self,ctx):
        """Unlock the Clash of Clans Data Loop."""
        if self._master_task_lock.locked():
            self._master_task_lock.release()
            await ctx.reply("Clash Data Loop unlocked.")
        else:
            await ctx.reply("Clash Data Loop is not locked.")
    
    @command_group_clash_data.command(name="stream")
    @commands.is_owner()
    async def subcommand_clash_data_stream(self,ctx):
        """Toggle the Clash of Clans Data Stream."""

        current_data_level = self.coc_data_log.level

        if current_data_level == logging.INFO:
            self.coc_main_log.setLevel(logging.DEBUG)
            self.coc_data_log.setLevel(logging.DEBUG)
            self.coc_main_log.debug("Clash Data Stream enabled.")
            await ctx.reply("Clash Data Stream enabled.")
        
        else:
            self.coc_main_log.setLevel(logging.INFO)
            self.coc_data_log.setLevel(logging.INFO)
            self.coc_main_log.info("Clash Data Stream disabled.")
            await ctx.reply("Clash Data Stream disabled.")
    
    @command_group_clash_data.command(name="httplog")
    @commands.is_owner()
    async def command_httplog(self,ctx:commands.Context):
        """
        Turns on HTTP logging for the Clash of Clans API.
        """
        current = logging.getLogger("coc.http").level
        if current == logging.DEBUG:
            logging.getLogger("coc.http").setLevel(logging.INFO)
            await ctx.tick()
        else:
            logging.getLogger("coc.http").setLevel(logging.DEBUG)
            await ctx.tick()