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
from redbot.core.utils.chat_formatting import humanize_list,box
from aiolimiter import AsyncLimiter

from .api_client import BotClashClient as client
from .cog_coc_client import ClashOfClansClient

from .coc_objects.clans.clan import db_Clan, db_WarLeagueClanSetup, aClan, BasicClan
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
semaphore_limit = 10000

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

        #API CONTROLLER
        self.task_api_slots = int(bot_client.rate_limit * 0.6)
        self.api_semaphore = AsyncLimiter(1,1/self.task_api_slots)
        
        # TASK CONTROLLER
        self._master_lock = asyncio.Lock()
        self._task_lock = asyncio.Lock()
        self._controller_loop = None
        self.task_lock_timestamp = None
        self.task_semaphore = asyncio.Semaphore(semaphore_limit)
        self.task_limiter = AsyncLimiter(1,1/(self.task_api_slots*10))

        # DATA QUEUE
        self._clan_queue_task = None
        self._player_queue_task = None

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

        await bot_client.bot.wait_until_red_ready()
        
        asyncio.create_task(self.start_recruiting_loop())

        self._controller_loop = asyncio.create_task(self.coc_task_controller())
        self._player_queue_task = asyncio.create_task(self.player_queue_task())
        self._clan_queue_task = asyncio.create_task(self.clan_queue_task())        
        self.clash_season_check.start()    
        self.refresh_coc_loops.start()

        asyncio.create_task(self.player_loop.start())
        asyncio.create_task(self.clan_loop.start())
        
        # asyncio.create_task(self.war_loop.start())
        # asyncio.create_task(self.raid_loop.start())
        # asyncio.create_task(self.discord_loop.start())
    
    async def start_recruiting_loop(self):
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
        self._clan_queue_task.cancel()
        self._player_queue_task.cancel()
        self.refresh_coc_loops.cancel()
        self.clash_season_check.cancel()
        
        self._controller_loop.cancel()

        bot_client.coc_main_log.info(f"Stopped Clash Data Loop.")

        for handler in bot_client.coc_main_log.handlers:
            bot_client.coc_main_log.removeHandler(handler)
        for handler in bot_client.coc_data_log.handlers:
            bot_client.coc_data_log.removeHandler(handler)

        stop_tasks = []
        # stop_tasks.append(asyncio.create_task(self.discord_loop.stop()))
        # stop_tasks.append(asyncio.create_task(self.raid_loop.stop()))
        # stop_tasks.append(asyncio.create_task(self.war_loop.stop()))
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
                try:
                    await asyncio.sleep(0.5)
                    if self.task_lock.locked():
                        continue
                    if self.task_semaphore._value == semaphore_limit:
                        continue

                    if self.task_semaphore._value <= semaphore_limit * 0.7:
                        async with self._task_lock:
                            self.task_lock_timestamp = pendulum.now()
                            while maintain_lock():
                                await asyncio.sleep(0.25)

                            self.task_lock_timestamp = None
                            await asyncio.sleep(0.5)

                except Exception:
                    bot_client.coc_main_log.exception(f"Error in Clash Task Controller")
                    continue
        
        except asyncio.CancelledError:
            return
    
    async def clan_queue_task(self):
        sleep = 0.01
        try:
            while True:
                try:
                    tag = await bot_client.clan_queue.get()
                    clan = await BasicClan(tag)
                    self.clan_loop.add_to_loop(clan.tag)
                    bot_client.clan_queue.task_done()
                    await asyncio.sleep(sleep)

                except asyncio.CancelledError:
                    raise
                except Exception:
                    bot_client.coc_main_log.exception(f"Error in Clan Queue Task")
                    continue
        except asyncio.CancelledError:
            return
    
    async def player_queue_task(self):
        sleep = 0.01
        try:
            while True:
                try:
                    tag = await bot_client.player_queue.get()
                    player = await BasicPlayer(tag)
                    self.player_loop.add_to_loop(player.tag)
                    bot_client.player_queue.task_done()
                    await asyncio.sleep(sleep)

                except asyncio.CancelledError:
                    raise
                except Exception:
                    bot_client.coc_main_log.exception(f"Error in Clan Queue Task")
                    continue
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
                return 
                # alliance_tags = await bot_client.run_in_thread(_get_alliance_tags)
                # alliance_clans = AsyncIter(alliance_tags)
                # async for tag in alliance_clans:
                #     self.war_loop.add_to_loop(tag)
                #     self.raid_loop.add_to_loop(tag)
                #     await asyncio.sleep(0)
                
                # cwl_tags = await bot_client.run_in_thread(_get_war_league_tags)
                # cwl_clans = AsyncIter(cwl_tags)
                # async for tag in cwl_clans:
                #     self.war_loop.add_to_loop(tag)
                #     await asyncio.sleep(0)

                # try:
                #     players = await bot_client.coc.get_location_players()
                # except:
                #     pass
                # else:
                #     for player in players:
                #         await asyncio.sleep(0)
                #         self.player_loop.add_to_loop(player.tag)
                
                # try:
                #     players = await bot_client.coc.get_location_players_builder_base()
                # except:
                #     pass
                # else:
                #     for player in players:
                #         await asyncio.sleep(0)
                #         self.player_loop.add_to_loop(player.tag)

                # try:
                #     locations = await bot_client.coc.search_locations()
                # except:
                #     pass
                # else:
                #     for location in locations:
                #         await asyncio.sleep(0)
                #         try:
                #             clans = await bot_client.coc.get_location_clans(location.id,limit=100)
                #         except:
                #             pass
                #         else:
                #             for clan in clans:
                #                 await asyncio.sleep(0)
                #                 self.clan_loop.add_to_loop(clan.tag)
                        
                #         try:
                #             bb_clan = await bot_client.coc.get_location_clans_builder_base(location.id,limit=100)
                #         except:
                #             pass
                #         else:
                #             for clan in bb_clan:
                #                 await asyncio.sleep(0)
                #                 self.clan_loop.add_to_loop(clan.tag)
                        
                #         try:
                #             capital_clan = await bot_client.coc.get_location_clans_capital(location.id,limit=100)
                #         except:
                #             pass
                #         else:
                #             for clan in capital_clan:
                #                 await asyncio.sleep(0)
                #                 self.clan_loop.add_to_loop(clan.tag)
                
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
                + f"\n\n**Current Season: {bot_client.current_season.description}**",
            timestamp=pendulum.now()
            )
        
        embed.add_field(
            name="**Loop Refresh**",
            value=f"Last: " + (f"<t:{self.last_task_refresh.int_timestamp}:R>" if self.last_task_refresh else "None")
                + "```ini"
                + f"\n{'[Running]':<10} " + (f"{'True':<5}" if self.refresh_lock.locked() else f"{'False':<5}")
                + "```",
            inline=True
            )
        embed.add_field(
            name="**Season Check**",
            value=f"Last: " + (f"<t:{self.last_season_check.int_timestamp}:R>" if self.last_season_check else "None")
                + "```ini"
                + f"\n{'[Running]':<10} " + (f"{'True':<5}" if self.season_lock.locked() else f"{'False':<5}")
                + "```",
            inline=True
            )
        embed.add_field(name="\u200b",value="\u200b",inline=True)

        client_waiters = len(self.api_semaphore._waiters) if self.api_semaphore._waiters else 0
        embed.add_field(
            name="**Tasks Client**",
            value="```ini"
                + f"\n{'[Master Lock]':<15} " + (f"{'Locked':<10}" if self._master_lock.locked() else f"{'Unlocked':<10}")
                + f"\n{'[Control Lock]':<15} " + (f"{'Locked'}" if self._task_lock.locked() else f"{'Unlocked'}") + (f" ({self.task_lock_timestamp.format('HH:mm:ss')})" if self.task_lock_timestamp else '')
                + f"\n{'[Running]':<15} " + f"{semaphore_limit - self.task_semaphore._value:,}"
                + "```",
            inline=False
            )
        # embed.add_field(name="\u200b",value="\u200b",inline=True)
        # embed.add_field(name="\u200b",value="\u200b",inline=True)
        embed.add_field(
            name="**Player Loops**",
            value=f"Last: <t:{self.player_loop.last_loop.int_timestamp}:R>"
                + "```ini"
                + f"\n{'[Tags]':<10} {len(self.player_loop._tags):,}"
                + f"\n{'[Running]':<10} {'True' if self.player_loop._running else 'False'}"
                + f"\n{'[LoopTime]':<10} {self.player_loop.dispatch_avg:.2f}s"
                + f"\n{'[RunTime]':<10} {self.player_loop.runtime_avg:.2f}s"
                + f"\n{'[Queue]':<10} {len(bot_client.player_queue):,}"
                + "```",
            inline=True
            )
        embed.add_field(
            name="**Clan Loops**",
            value=f"Last: <t:{self.clan_loop.last_loop.int_timestamp}:R>"
                + "```ini"
                + f"\n{'[Tags]':<10} {len(self.clan_loop._tags):,}"
                + f"\n{'[Running]':<10} {'True' if self.clan_loop._running else 'False'}"
                + f"\n{'[LoopTime]':<10} {self.clan_loop.dispatch_avg:.2f}s"
                + f"\n{'[RunTime]':<10} {self.clan_loop.runtime_avg:.2f}s"
                + f"\n{'[Queue]':<10} {len(bot_client.clan_queue):,}"
                + "```",
            inline=True
            )
        # embed.add_field(name="\u200b",value="\u200b",inline=True)
        # embed.add_field(
        #     name="**Clan Wars**",
        #     value="Last: " + (f"<t:{self.war_loop.last_loop.int_timestamp}:R>" if self.war_loop.last_loop else "None")
        #         + "```ini"                
        #         + f"\n{'[Tags]':<10} {len(self.war_loop._tags):,}"
        #         + f"\n{'[Running]':<10} {'True' if self.war_loop._running else 'False'}"
        #         + f"\n{'[Runtime]':<10} {self.war_loop.runtime_avg:.2f}s"
        #         + f"\n{'[Cache]':<10} {len(aClanWar._cache):,}"
        #         + "```",
        #     inline=True
        #     )
        # embed.add_field(
        #     name="**Capital Raids**",
        #     value="Last: " + (f"<t:{self.raid_loop.last_loop.int_timestamp}:R>" if self.raid_loop.last_loop else "None")
        #         + "```ini"                
        #         + f"\n{'[Tags]':<10} {len(self.raid_loop._tags):,}"
        #         + f"\n{'[Running]':<10} {'True' if self.raid_loop._running else 'False'}"
        #         + f"\n{'[Runtime]':<10} {self.raid_loop.runtime_avg:.2f}s"
        #         + f"\n{'[Cache]':<10} {len(aRaidWeekend._cache):,}"
        #         + "```",
        #     inline=True
        #     )
        # embed.add_field(name="\u200b",value="\u200b",inline=True)
        # embed.add_field(
        #     name="**Discord**",
        #     value="Last: " + (f"<t:{self.discord_loop.last_loop.int_timestamp}:R>" if self.discord_loop.last_loop else "None")
        #         + "```ini"
        #         + f"\n{'[Guilds]':<10} {len(self.bot.guilds):,}"
        #         + f"\n{'[Users]':<10} {len(self.bot.users):,}"
        #         + f"\n{'[Running]':<10} {'True' if self.discord_loop._running else 'False'}"
        #         + "```",
        #     inline=True
        #     )
        # embed.add_field(name="\u200b",value="\u200b",inline=True)
        # embed.add_field(name="\u200b",value="\u200b",inline=True)
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