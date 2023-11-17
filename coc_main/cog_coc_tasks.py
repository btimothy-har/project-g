import discord
import asyncio
import coc
import pendulum
import logging

from typing import *
from mongoengine import *

from art import text2art
from itertools import islice
from discord.ext import tasks
from redbot.core import commands
from redbot.core.bot import Red
from redbot.core.utils import AsyncIter, bounded_gather
from redbot.core.utils.chat_formatting import humanize_list

from .api_client import BotClashClient as client
from .cog_coc_client import ClashOfClansClient

from .coc_objects.clans.clan import db_Clan, db_WarLeagueClanSetup, aClan
from .coc_objects.players.player import db_Player, db_PlayerStats, aPlayer, BasicPlayer
from .coc_objects.events.clan_war import db_ClanWar, aClanWar
from .coc_objects.events.raid_weekend import db_RaidWeekend, aRaidWeekend

from .tasks.player_tasks import PlayerLoop
from .tasks.clan_tasks import ClanLoop
from .tasks.war_tasks import ClanWarLoop
from .tasks.raid_tasks import ClanRaidLoop
from .tasks.guild_tasks import DiscordGuildLoop

from .coc_objects.season.season import aClashSeason
from .coc_objects.clans.mongo_clan import db_AllianceClan
from .discord.guild import aGuild
from .discord.member import aMember
from .discord.application_panel import GuildApplicationPanel, listener_user_application
from .discord.recruiting_reminder import RecruitingReminder

from .utils.components import DefaultView, DiscordButton, clash_embed
from .utils.constants.ui_emojis import EmojisUI

bot_client = client()
semaphore_limit = 100000

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

    __author__ = bot_client.author
    __version__ = bot_client.version

    def __init__(self,bot:Red):
        self.bot = bot

        self.player_loop = PlayerLoop()
        self.clan_loop = ClanLoop()
        self.war_loop = ClanWarLoop()
        self.raid_loop = ClanRaidLoop()
        self.discord_loop = DiscordGuildLoop()

        #API CONTROLLER
        self.api_semaphore = asyncio.Semaphore(int(bot_client.rate_limit * 0.9))
        
        # TASK CONTROLLER
        self._master_lock = asyncio.Lock()
        self._task_lock = asyncio.Lock()
        self._controller_loop = None
        self.task_lock_timestamp = None
        self.task_semaphore = asyncio.Semaphore(semaphore_limit)

        # DATA QUEUE
        self.queue_lock = asyncio.Lock()
        self.last_queue_run = None

        # TASK REFRESH
        self.refresh_lock = asyncio.Lock()
        self.last_task_refresh = None

        # RECRUITING TASKS
        self.recruiting_loop_started = False

        # SEASON CHECK
        self.season_lock = asyncio.Lock()
        self.last_season_check = None

        # BACKGROUND OBJECT TASKS
        self.last_task_error = None

    def format_help_for_context(self, ctx: commands.Context) -> str:
        context = super().format_help_for_context(ctx)
        return f"{context}\n\nAuthor: {self.__author__}\nVersion: {self.__version__}"

    @property
    def client(self) -> ClashOfClansClient:
        return bot_client.bot.get_cog('ClashOfClansClient')
    
    @property
    def api_maintenance(self) -> bool:
        return self.client.api_maintenance
    
    @property
    def task_lock(self) -> asyncio.Lock:
        if self._master_lock.locked():
            return self._master_lock
        return self._task_lock
    
    @property
    def task_waiters(self) -> int:
        return len(self.task_semaphore._waiters) if self.task_semaphore._waiters else 0

    async def report_error(self,message,error):
        if not self.last_task_error or pendulum.now().int_timestamp - self.last_task_error.int_timestamp > 60:
            self.last_task_error = pendulum.now()
            await bot_client.bot.send_to_owners(f"{message}```{error}```")

    ##################################################
    ### COG LOAD
    ##################################################
    async def cog_load(self):
        asyncio.create_task(self.start_task_cog())
    
    async def start_task_cog(self):
        while True:
            if getattr(bot_client,'_api_logged_in',False):
                break
            await asyncio.sleep(1)
        
        asyncio.create_task(self.start_recruiting_loop())

        #self._controller_loop = asyncio.create_task(self.coc_task_controller())
        self.clash_season_check.start()
        self.coc_data_queue.start()        
        self.refresh_coc_loops.start()

        asyncio.create_task(self.player_loop.start())
        asyncio.create_task(self.clan_loop.start())
        asyncio.create_task(self.war_loop.start())
        asyncio.create_task(self.raid_loop.start())
        asyncio.create_task(self.discord_loop.start())
    
    async def start_recruiting_loop(self):
        await bot_client.bot.wait_until_red_ready()
        posts = await RecruitingReminder.get_all_active()
        async for post in AsyncIter(posts):
            count = 0
            while True:
                try:
                    count += 1
                    await post.refresh_reminder()
                    break
                except Exception:
                    if count > 30:
                        bot_client.coc_main_log.exception(f"Could not refresh reminder for {post.id} - {post}")
                        break
                    await asyncio.sleep(1)
        self.recruiting_loop_started = True

    ##################################################
    ### COG LOAD
    ##################################################
    async def cog_unload(self):
        self.refresh_coc_loops.cancel()
        self.coc_data_queue.cancel()
        self.clash_season_check.cancel()
        
        #self._controller_loop.cancel()

        bot_client.coc_main_log.info(f"Stopped Clash Data Loop.")

        for handler in bot_client.coc_main_log.handlers:
            bot_client.coc_main_log.removeHandler(handler)
        for handler in bot_client.coc_data_log.handlers:
            bot_client.coc_data_log.removeHandler(handler)

        stop_tasks = []
        stop_tasks.append(asyncio.create_task(self.discord_loop.stop()))
        stop_tasks.append(asyncio.create_task(self.raid_loop.stop()))
        stop_tasks.append(asyncio.create_task(self.war_loop.stop()))
        stop_tasks.append(asyncio.create_task(self.clan_loop.stop()))
        stop_tasks.append(asyncio.create_task(self.player_loop.stop()))
        
        await asyncio.gather(*stop_tasks,return_exceptions=True)

        aMember._global = {}
        aMember._local = {}
    
    @commands.Cog.listener("on_member_join")
    async def new_discord_member(self,member:discord.Member):        
        linked_accounts = await bot_client.get_linked_players(member.id)
        async for tag in AsyncIter(linked_accounts):
            player = await self.client.fetch_player(tag)
            if player.discord_user == 0:
                await BasicPlayer.set_discord_link(player.tag,member.id)
    
    @commands.Cog.listener("on_guild_channel_create")
    async def recruiting_ticket_listener(self,channel):
        application_id = None
        await asyncio.sleep(2)        
        
        panels = await GuildApplicationPanel.get_for_guild(channel.guild.id)
        if len(panels) == 0:
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
    ##### CLASH OF CLANS CORE DATA LOOPS
    #####
    ############################################################
    async def coc_task_controller(self):
        def maintain_lock():
            if self.task_semaphore._value < semaphore_limit:
                return True
            if self.task_waiters > 0:
                return True
            return False
        
        try:
            while True:
                await asyncio.sleep(0.5)

                if self.task_lock.locked():
                    continue

                if self.task_semaphore._value == semaphore_limit:
                    continue

                try:
                    async with self._task_lock:
                        self.task_lock_timestamp = pendulum.now()
                        while maintain_lock():
                            await asyncio.sleep(0.25)

                        self.task_lock_timestamp = None
                        await asyncio.sleep(0.5)
                
                except asyncio.CancelledError:
                    raise

                except Exception:
                    bot_client.coc_main_log.exception(f"Error in Clash Task Controller")
        
        except asyncio.CancelledError:
            return

    @tasks.loop(seconds=10.0)
    async def clash_season_check(self):
        if self.season_lock.locked():
            return
        
        try:
            async with self.season_lock:
                season = aClashSeason.get_current_season()

                if season.id == bot_client.current_season.id:
                    return None
                
                async with self._master_lock:
                    while self.task_semaphore._value < semaphore_limit:
                        await asyncio.sleep(0)
                    await season.set_as_current()
                    await bot_client.load_seasons()
                
                bot_client.coc_main_log.info(f"New Season Started: {season.id} {season.description}\n"
                    + text2art(f"{season.id}",font="small")
                    )
                bot_client.coc_data_log.info(f"New Season Started: {season.id} {season.description}\n"
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
        
        except Exception as exc:
            await self.bot.send_to_owners(f"An error occured during Season Refresh. Check logs for details."
                + f"```{exc}```")
            bot_client.coc_main_log.exception(
                f"Error in Season Refresh"
                )        
        finally:
            self.last_season_check = pendulum.now()

    @tasks.loop(seconds=10)
    async def coc_data_queue(self):
        if self.queue_lock.locked():
            return
        
        sleep = (1 / bot_client.rate_limit) * 3
        
        async def load_clan_queue():            
            async def fetch_clan(clan_tag):
                try:
                    async with self.api_semaphore:
                        await bot_client.coc.get_clan(clan_tag,cls=aClan)
                        bot_client.clan_cache.remove_from_queue(clan_tag)
                except coc.NotFound:
                    bot_client.clan_cache.remove_from_queue(clan_tag)
                    return None
                except:
                    return None
            
            queue = bot_client.clan_cache.queue.copy()
            clan_queue = queue[:1000]
            if len(clan_queue) > 0:
                async for c in AsyncIter(clan_queue):
                    await asyncio.sleep(sleep)
                    asyncio.create_task(fetch_clan(c))
            
        async def load_player_queue():
            async def fetch_player(player_tag):
                try:
                    async with self.api_semaphore:
                        await bot_client.coc.get_player(player_tag,cls=aPlayer)
                        bot_client.player_cache.remove_from_queue(player_tag)
                except coc.NotFound:
                    bot_client.player_cache.remove_from_queue(player_tag)                    
                    return None
                except:
                    return None
            
            queue = bot_client.player_cache.queue.copy()
            player_queue = queue[:1000]
            if len(player_queue) > 0:
                async for p in AsyncIter(player_queue):
                    await asyncio.sleep(sleep)
                    asyncio.create_task(fetch_player(p))
            
        try:
            async with self.queue_lock:
                t = []
                t.append(asyncio.create_task(load_clan_queue()))
                t.append(asyncio.create_task(load_player_queue()))
                await asyncio.gather(*t,return_exceptions=True)

        except Exception as exc:
            await self.bot.send_to_owners(f"An error occured during Clash Data Queue. Check logs for details."
                + f"```{exc}```")
            self.coc_main_log.exception(
                f"Error in Clash Data Queue"
                )
        finally:
            self.last_queue_run = pendulum.now()
    
    @tasks.loop(minutes=1.0)
    async def refresh_coc_loops(self):
        def _get_alliance_tags():
            return [db.tag for db in db_AllianceClan.objects().only('tag')]

        def _get_war_league_tags():
            return [db.tag for db in db_WarLeagueClanSetup.objects().only('tag')]

        if self.refresh_lock.locked():
            return
        
        try:
            async with self.refresh_lock:

                alliance_tags = await bot_client.run_in_thread(_get_alliance_tags)
                alliance_clans = AsyncIter(alliance_tags)
                async for tag in alliance_clans:
                    self.war_loop.add_to_loop(tag)
                    self.raid_loop.add_to_loop(tag)
                    await asyncio.sleep(0)
                
                cwl_tags = await bot_client.run_in_thread(_get_war_league_tags)
                cwl_clans = AsyncIter(cwl_tags)
                async for tag in cwl_clans:
                    self.war_loop.add_to_loop(tag)
                    await asyncio.sleep(0)

        except Exception as exc:
            await self.bot.send_to_owners(f"An error occured during Task Refresh. Check logs for details."
                + f"```{exc}```")
            bot_client.coc_main_log.exception(
                f"Error in Clash Data Loop"
                )        
        finally:
            self.last_task_refresh = pendulum.now()
        
    async def status_embed(self):
        embed = await clash_embed(self.bot,
            title="**Clash of Clans Data Status**",
            message=f"### {pendulum.now().format('dddd, DD MMM YYYY HH:mm:ssZZ')}"
                + f"\n\nCurrent Season: {bot_client.current_season.description}"
                + f"\nTracked Seasons: {humanize_list([i.short_description for i in bot_client.tracked_seasons])}"
                + f"\n\nLoop Refresh: " + ("Running" if self.refresh_lock.locked() else "Not Running") + " (last: " + (f"<t:{self.last_task_refresh.int_timestamp}:R>" if self.last_task_refresh else "None") + ")"
                + f"\nQueue Check: " + ("Running" if self.queue_lock.locked() else "Not Running") + " (last: " + (f"<t:{self.last_queue_run.int_timestamp}:R>" if self.last_queue_run else "None") + ")"
                + f"\nSeason Check: " + ("Running" if self.season_lock.locked() else "Not Running") + " (last: " + (f"<t:{self.last_season_check.int_timestamp}:R>" if self.last_season_check else "None") + ")",
            timestamp=pendulum.now()
            )
        
        client_waiters = len(self.api_semaphore._waiters) if self.api_semaphore._waiters else 0
        embed.add_field(
            name="**Tasks Client**",
            value="```ini"
                + f"\n{'[Master Lock]':<15} " + (f"Locked" if self._master_lock.locked() else 'Unlocked')
                + f"\n{'[Control Lock]':<15} " + (f"Locked" if self._task_lock.locked() else 'Unlocked') + (f" ({self.task_lock_timestamp.format('HH:mm:ss')})" if self.task_lock_timestamp else '')
                + f"\n{'[Running]':<15} " + f"{semaphore_limit - self.task_semaphore._value:,}"
                + f"\n{'[API Slots]':<15} " + f"{int(bot_client.rate_limit * 0.9) - self.api_semaphore._value:,} / {int(bot_client.rate_limit * 0.9):,} (Waiting: {client_waiters:,})"
                + "```",
            inline=False
            )
        embed.add_field(
            name="**Player Loops**",
            value="```ini"
                + f"\n{'[Cache]':<10} {len(bot_client.player_cache):,}"
                + f"\n{'[Queue]':<10} {len(bot_client.player_cache.queue):,}"
                + f"\n{'[Running]':<10} {self.player_loop._running:,}"
                + f"\n{'[Last]':<10} {self.player_loop.last_loop.diff_for_humans()}"
                + f"\n{'[Tasks]':<10} {self.player_loop._queue.qsize():,}"
                + "```",
            inline=False
            )
        embed.add_field(
            name="**Clans**",
            value="```ini"
                + f"\n{'[Cache]':<10} {len(bot_client.clan_cache):,}"
                + f"\n{'[Queue]':<10} {len(bot_client.clan_cache.queue):,}"
                + f"\n{'[Running]':<10} {self.clan_loop._running:,}"
                + f"\n{'[Last]':<10} {self.clan_loop.last_loop.diff_for_humans()}"
                + f"\n{'[Tasks]':<10} {self.clan_loop._queue.qsize():,}"
                + "```",
            inline=False
            )
        embed.add_field(
            name="**Clan Wars**",
            value="```ini"
                + f"\n{'[Cache]':<10} {len(aClanWar._cache):,}"
                + f"\n{'[Clans]':<10} {len(self.war_loop._tags):,}"
                + f"\n{'[Running]':<10} {self.war_loop._running:,}"
                + f"\n{'[Last]':<10} {self.war_loop.last_loop.diff_for_humans()}"
                + f"\n{'[Tasks]':<10} {self.war_loop._queue.qsize():,}"
                + "```",
            inline=True
            )
        embed.add_field(
            name="**Capital Raids**",
            value="```ini"
                + f"\n{'[Cache]':<10} {len(aRaidWeekend._cache):,}"
                + f"\n{'[Clans]':<10} {len(self.raid_loop._tags):,}"
                + f"\n{'[Running]':<10} {self.raid_loop._running:,}"
                + f"\n{'[Last]':<10} {self.raid_loop.last_loop.diff_for_humans()}"
                + f"\n{'[Tasks]':<10} {self.raid_loop._queue.qsize():,}"
                + "```",
            inline=True
            )
        diff = pendulum.now() - self.discord_loop.last_loop
        embed.add_field(
            name="**Discord**",
            value="```ini"
                + f"\n{'[Guilds]':<10} {len(self.bot.guilds):,}"
                + f"\n{'[Users]':<10} {len(self.bot.users):,}"
                + f"\n{'[Running]':<10} {self.discord_loop._running:,}"
                + f"\n{'[Last]':<10} {diff.diff_for_humans()}"
                + f"\n{'[Tasks]':<10} {self.discord_loop._queue.qsize():,}"
                + "```",
            inline=True
            )
        return embed
    
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

        embed = await self.status_embed()
        view = RefreshStatus(ctx)
        await ctx.reply(embed=embed,view=view)
    
    @command_group_clash_data.command(name="lock")
    @commands.is_owner()
    async def subcommand_clash_data_lock(self,ctx):
        """Lock the Clash of Clans Data Loop."""
        if self.task_lock.locked():
            await ctx.reply("Clash Data Loop is already locked.")
        else:
            await self._master_lock.acquire()
            await ctx.reply("Clash Data Loop locked.")
    
    @command_group_clash_data.command(name="unlock")
    @commands.is_owner()
    async def subcommand_clash_data_unlock(self,ctx):
        """Unlock the Clash of Clans Data Loop."""
        if self._master_lock.locked():
            self._master_lock.release()
            await ctx.reply("Clash Data Loop unlocked.")
        else:
            await ctx.reply("Clash Data Loop is not locked.")
    
    @command_group_clash_data.command(name="stream")
    @commands.is_owner()
    async def subcommand_clash_data_stream(self,ctx):
        """Toggle the Clash of Clans Data Stream."""

        current_data_level = bot_client.coc_data_log.level

        if current_data_level == logging.INFO:
            bot_client.coc_main_log.setLevel(logging.DEBUG)
            bot_client.coc_data_log.setLevel(logging.DEBUG)
            bot_client.coc_main_log.debug("Clash Data Stream enabled.")
            await ctx.reply("Clash Data Stream enabled.")
        
        else:
            bot_client.coc_main_log.setLevel(logging.INFO)
            bot_client.coc_data_log.setLevel(logging.INFO)
            bot_client.coc_main_log.info("Clash Data Stream disabled.")
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

class RefreshStatus(DefaultView):
    def __init__(self,context:Union[discord.Interaction,commands.Context]):

        button = DiscordButton(
            function=self._refresh_embed,
            emoji=EmojisUI.REFRESH,
            label="Refresh",
            )

        super().__init__(context,timeout=9999999)
        self.is_active = True

        self.add_item(button)
    
    @property
    def task_cog(self) -> ClashOfClansTasks:
        return bot_client.bot.get_cog("ClashOfClansTasks")
    
    async def _refresh_embed(self,interaction:discord.Interaction,button:DiscordButton):
        await interaction.response.defer()
        embed = await self.task_cog.status_embed()
        await interaction.followup.edit_message(interaction.message.id,embed=embed)