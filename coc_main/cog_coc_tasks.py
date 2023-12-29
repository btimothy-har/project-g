import asyncio
import coc
import discord
import pendulum
import logging

from typing import *

from art import text2art
from discord.ext import tasks
from aiolimiter import AsyncLimiter

from redbot.core import commands
from redbot.core.bot import Red
from redbot.core.utils import AsyncIter

from .api_client import BotClashClient as client
from .cog_coc_client import ClashOfClansClient

from .coc_objects.season.season import aClashSeason
from .coc_objects.players.player import BasicPlayer

from .tasks.player_tasks import PlayerLoop
from .tasks.clan_tasks import ClanLoop
from .tasks.war_tasks import ClanWarLoop
from .tasks.raid_tasks import ClanRaidLoop
from .tasks.guild_tasks import DiscordGuildLoop

from .discord.member import aMember
from .discord.application_panel import GuildApplicationPanel, listener_user_application
from .discord.recruiting_reminder import RecruitingReminder

from .utils.components import DefaultView, DiscordButton, clash_embed
from .utils.constants.ui_emojis import EmojisUI

bot_client = client()
semaphore_limit = 10

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
        self.task_api_slots = int(bot_client.rate_limit * 0.6)
        self.api_semaphore = AsyncLimiter(1,1/self.task_api_slots)

        # DATA QUEUE
        self._clan_queue_task = None
        self._player_queue_task = None

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
            if getattr(bot_client,'_is_initialized',False):
                break
            await asyncio.sleep(1)

        await bot_client.bot.wait_until_ready()
        
        #asyncio.create_task(self.start_recruiting_loop())
        self._player_queue_task = asyncio.create_task(self.player_queue_task())
        self._clan_queue_task = asyncio.create_task(self.clan_queue_task())        
        self.clash_season_check.start()

        asyncio.create_task(self.player_loop.start())
        asyncio.create_task(self.clan_loop.start())
        asyncio.create_task(self.war_loop.start())
        asyncio.create_task(self.raid_loop.start())
        asyncio.create_task(self.discord_loop.start())
    
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
    async def shutdown(self):
        self._clan_queue_task.cancel()
        self._player_queue_task.cancel()
        self.clash_season_check.cancel()
        
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
    async def clan_queue_task(self):
        sleep = 0.1
        try:
            while True:
                try:
                    tag = await bot_client.clan_queue.get()
                    n_tag = coc.utils.correct_tag(tag)
                    try:
                        clan = await self.client.fetch_clan(n_tag)
                    except:
                        continue
                    await clan._sync_cache()
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
        sleep = 0.1
        try:
            while True:
                try:
                    tag = await bot_client.player_queue.get()
                    n_tag = coc.utils.correct_tag(tag)
                    try:
                        player = await self.client.fetch_player(n_tag)
                    except:
                        continue
                    await player._sync_cache()
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
                season = await aClashSeason.get_current_season()

                if season.id == bot_client.current_season.id:
                    return None
                
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
                        name=f"start of the {bot_client.current_season.short_description} Season! Clash on!")
                        )

                bank_cog = bot_client.bot.get_cog('Bank')
                if bank_cog:
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
        
    async def status_embed(self):
        embed = await clash_embed(self.bot,
            title="**Clash of Clans Data Status**",
            message=f"### {pendulum.now().format('dddd, DD MMM YYYY HH:mm:ssZZ')}"
                + f"\n\n**Current Season: {bot_client.current_season.description}**",
            timestamp=pendulum.now()
            )

        clan_running = (semaphore_limit - self.clan_loop._task_semaphore._value) + (len(self.clan_loop._task_semaphore._waiters) if self.clan_loop._task_semaphore._waiters else 0)
        player_running = (semaphore_limit - self.player_loop._task_semaphore._value) + (len(self.player_loop._task_semaphore._waiters) if self.player_loop._task_semaphore._waiters else 0)
        war_running = (semaphore_limit - self.player_loop._task_semaphore._value) + (len(self.player_loop._task_semaphore._waiters) if self.player_loop._task_semaphore._waiters else 0)
        embed.add_field(
            name="**Tasks Client**",
            value=f"Season Check: " + (f"<t:{self.last_season_check.int_timestamp}:R>" if self.last_season_check else "None")
                + "```ini"
                + f"\n{'[Player]':<15} {player_running:,}"
                + f"\n{'[Clan]':<15} {clan_running:,}"
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
                + "```",
            inline=True
            )
        embed.add_field(name="\u200b",value="\u200b",inline=True)
        embed.add_field(
            name="**Clan Wars**",
            value="Last: " + (f"<t:{self.war_loop.last_loop.int_timestamp}:R>" if self.war_loop.last_loop else "None")
                + "```ini"                
                + f"\n{'[Tags]':<10} {len(self.war_loop._tags):,}"
                + f"\n{'[Running]':<10} {'True' if self.war_loop._running else 'False'}"
                + f"\n{'[LoopTime]':<10} {self.war_loop.dispatch_avg:.2f}s"
                + f"\n{'[RunTime]':<10} {self.war_loop.runtime_avg:.2f}s"
                + "```",
            inline=True
            )
        embed.add_field(
            name="**Capital Raids**",
            value="Last: " + (f"<t:{self.raid_loop.last_loop.int_timestamp}:R>" if self.raid_loop.last_loop else "None")
                + "```ini"                
                + f"\n{'[Tags]':<10} {len(self.raid_loop._tags):,}"
                + f"\n{'[Running]':<10} {'True' if self.raid_loop._running else 'False'}"
                + f"\n{'[LoopTime]':<10} {self.war_loop.dispatch_avg:.2f}s"
                + f"\n{'[RunTime]':<10} {self.war_loop.runtime_avg:.2f}s"
                + "```",
            inline=True
            )
        embed.add_field(name="\u200b",value="\u200b",inline=True)
        embed.add_field(
            name="**Discord**",
            value="Last: " + (f"<t:{self.discord_loop.last_loop.int_timestamp}:R>" if self.discord_loop.last_loop else "None")
                + "```ini"
                + f"\n{'[Guilds]':<10} {len(self.bot.guilds):,}"
                + f"\n{'[Users]':<10} {len(self.bot.users):,}"
                + f"\n{'[Running]':<10} {'True' if self.discord_loop._running else 'False'}"
                + "```",
            inline=True
            )
        embed.add_field(name="\u200b",value="\u200b",inline=True)
        embed.add_field(name="\u200b",value="\u200b",inline=True)
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