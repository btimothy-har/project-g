import asyncio
import coc
import os
import logging
import pendulum

from typing import *

from discord.ext import tasks
from art import text2art
from time import process_time

from redbot.core import Config, commands
from redbot.core.bot import Red
from redbot.core.data_manager import cog_data_path
from redbot.core.utils import AsyncIter

from .client.global_client import GlobalClient
from .client.db_client import MotorClient
from .client.coc_client import ClashClient
from .exceptions import *

from .coc_objects.season.season import aClashSeason
from .coc_objects.players.player import BasicPlayer
from .utils.components import clash_embed, DefaultView, DiscordButton, EmojisUI

COC_LOG = logging.getLogger("coc.main")

############################################################
############################################################
#####
##### CLIENT COG
#####
############################################################
############################################################
class ClashOfClansMain(commands.Cog):
    """
    API Client connector for Clash of Clans

    This cog uses the [coc.py Clash of Clans API wrapper](https://cocpy.readthedocs.io/en/latest/).

    Client parameters are stored RedBot's API framework, using the `[p]set api clashapi` command. The accepted parameters are as follows:
    - `username` : API Username
    - `password` : API Password
    - `keys` : Number of keys to use. Defaults to 1.

    You can register for a Username and Password at https://developer.clashofclans.com.

    You may also add multiple API Logins by binding additional logins to clashapi1, clashapi2, etc up to clashapi29. To use multiple logins, use the `[p]reloadkeys` command and reload the cog.

    This cog also includes support for the Clash DiscordLinks service. If you have a username and password, set them with `[p]set api clashlinks` (parameters: `username` and `password`).

    The use of Clash DiscordLinks is optional.
    """

    __author__ = "bakkutteh"
    __version__ = "2024.03.1"

    def __init__(self,bot:Red):
        self.bot = bot
        self.bot.last_status_update = None
        
        self.global_client = None
        self.coc_client = None
        self.db_client = None

        self._season_lock = asyncio.Lock()

        self.config = Config.get_conf(self,identifier=644530507505336330,force_registration=True)
        default_global = {
            "client_keys":[]
            }
        self.config.register_global(**default_global)

    def format_help_for_context(self, ctx: commands.Context) -> str:
        context = super().format_help_for_context(ctx)
        return f"{context}\n\nAuthor: {self.__author__}\nVersion: {self.__version__}"

    ############################################################
    #####
    ##### DATABASE CONNECT
    #####
    ############################################################
    async def cog_load(self):
        log_path = f"{cog_data_path(self)}/logs"
        if not os.path.exists(log_path):
            os.makedirs(log_path)

        log_formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s')
        main_logpath = f"{log_path}/main"
        if not os.path.exists(main_logpath):
            os.makedirs(main_logpath)                
        cocmain_log_handler = logging.handlers.RotatingFileHandler(
            f"{main_logpath}/main.log",
            maxBytes=3*1024*1024,
            backupCount=9
            )
        cocmain_log_handler.setFormatter(log_formatter)
        COC_LOG.addHandler(cocmain_log_handler)

        self.bot.coc_imggen_path = f"{cog_data_path(self)}/imggen"
        self.bot.coc_report_path = f"{cog_data_path(self)}/reports"

        self.global_client = GlobalClient.start_client(self.bot)        
        await self.database_login()
        await self.client_login()

        self.global_client._ready = True

        self.reset_throttler_counter.start()
        self.bot_status_update_loop.start() 
        self.clash_season_check.start()
            
    async def cog_unload(self):
        self.bot_status_update_loop.cancel()
        self.clash_season_check.cancel()

        await self.client_logout()
        await self.database_logout()
        COC_LOG.handlers.clear()
    
    ############################################################
    #####
    ##### DATABASE LOGIN/LOGOUT
    #####
    ############################################################
    async def database_login(self):
        self.db_client = await MotorClient.client_login(self.bot)
        self.global_client.database = self.db_client.database
        await aClashSeason.load_seasons()
    
    async def database_logout(self):
        await self.db_client.close()
    
    ############################################################
    #####
    ##### API CLIENT LOGIN/LOGOUT
    #####
    ############################################################
    async def client_login(self) -> None:
        try:
            keys = await self.config.client_keys()
        except:
            keys = None
        self.coc_client = await ClashClient.start(
            bot=self.bot,
            rate_limit=30,
            keys=keys
            )
        await self.coc_client.discordlinks_login()
        self.coc_client.add_events(
            self.clash_event_error,
            self.clash_maintenance_start,
            self.clash_maintenance_complete,
            )
        self.global_client.coc_client = self.coc_client
    
    async def client_logout(self) -> None:
        await self.coc_client.close()
    
    ############################################################
    #####
    ##### DISCORD LISTENERS
    #####
    ############################################################ 
    @commands.Cog.listener("on_shard_connect")
    async def status_on_connect(self,shard_id):
        await self.bot.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.listening,
                name=f"$help!")
                )
    
    @commands.Cog.listener("on_member_join")
    async def new_discord_member(self,member:discord.Member):
        linked_accounts = await self.coc_client.get_linked_players(member.id)
        async for player in self.coc_client.get_players(linked_accounts):
            if player.discord_user == 0:
                await BasicPlayer.set_discord_link(player.tag,member.id)

    ############################################################
    #####
    ##### LOOPS
    #####
    ############################################################
    @tasks.loop(minutes=10.0)
    async def bot_status_update_loop(self):
        try:
            if self.bot.last_status_update != None and (pendulum.now().int_timestamp - self.bot.last_status_update.int_timestamp) < (6 * 3600):
                return            
            await self.bot.change_presence(
                activity=discord.Activity(
                    type=discord.ActivityType.listening,
                    name=f"$help!")
                    )              
        except Exception:
            COC_LOG.exception(f"Error in Bot Status Loop")
    
    @tasks.loop(seconds=10.0)
    async def reset_throttler_counter(self):
        async with self.coc_client.http_throttler.sent_lock, self.coc_client.http_throttler.rcvd_lock:
            nt = process_time()
            calc_sent = self.coc_client.http_throttler.current_sent / (nt - self.coc_client.http_throttler.sent_time)            
            self.coc_client.http_throttler.sent.append(calc_sent)
            self.coc_client.http_throttler.current_sent = 0
            self.coc_client.http_throttler.sent_time = nt
        
            calc_rcvd = self.coc_client.http_throttler.current_rcvd / (nt - self.coc_client.http_throttler.rcvd_time)            
            self.coc_client.http_throttler.rcvd.append(calc_rcvd)
            self.coc_client.http_throttler.current_rcvd = 0
            self.coc_client.http_throttler.rcvd_time = nt
            
    @tasks.loop(minutes=1.0)
    async def clash_season_check(self):
        if self._season_lock.locked():
            return        
        try:
            async with self._season_lock:
                current_bot_season = aClashSeason.current()
                
                try:
                    current_api_season = await self.coc_client.get_current_goldpass_season()
                except coc.Maintenance:
                    return
                current_api_season_id = f"{current_api_season.start_time.time.month}-{current_api_season.start_time.time.year}"

                if current_bot_season.id == current_api_season_id:
                    return None

                new_season = aClashSeason(current_api_season_id)
                await new_season.load()
                await new_season.set_as_current()
                
                COC_LOG.info(f"New Season Started: {new_season.id} {new_season.description}\n"
                    + text2art(f"{new_season.id}",font="small")
                    )
                
                text = f'start of the {aClashSeason.current().short_description} Season! Clash on!'                
                await GlobalClient.update_bot_status(0,text)
                await self.bot.send_to_owners(f"New Season Started: {new_season.id} {new_season.description}")
        
        except SeasonNotLoaded:
            return
        
        except Exception as exc:
            await self.bot.send_to_owners(f"An error occured during Season Refresh. Check logs for details."
                + f"```{exc}```")
            COC_LOG.exception(f"Error in Season Refresh")
    
    ############################################################
    #####
    ##### STATUS REPORT
    #####
    ############################################################ 
    async def status_embed(self):
        embed = await clash_embed(self.bot,
            title="**Clash of Clans API**",
            message=f"### {pendulum.now().format('dddd, DD MMM YYYY HH:mm:ssZZ')}",
            timestamp=pendulum.now()
            )
        
        waiters = len(self.coc_client.http._HTTPClient__lock._waiters) if self.coc_client.http._HTTPClient__lock._waiters else 0
        embed.add_field(
            name="**API Client**",
            value="```ini"
                + f"\n{'[Maintenance]':<15}{self.coc_client.maintenance}"
                + f"\n{'[API Keys]':<15}" + f"{self.coc_client.http.key_count:,}"
                + f"\n{'[API Requests]':<15}" + f"{(self.coc_client.http.key_count) - self.coc_client.http._HTTPClient__lock._value:,} / {self.coc_client.http.key_count:,}" + f" (Waiting: {waiters:,})"
                + f"\n{'[Discovery]':<15}" + f"{self.coc_client._use_discovery}"
                + "```",
            inline=False
            )
        embed.add_field(
            name="**Player API**",
            value="```ini"
                + f"\n{'[Last]':<10} {(self.coc_client.player_api[-1] if len(self.coc_client.player_api) > 0 else 0)/1000:.3f}s"
                + f"\n{'[Mean]':<10} {self.coc_client.player_api_avg/1000:.3f}s"
                + f"\n{'[Min/Max]':<10} {(min(self.coc_client.player_api) if len(self.coc_client.player_api) > 0 else 0)/1000:.3f}s ~ {(max(self.coc_client.player_api) if len(self.coc_client.player_api) > 0 else 0)/1000:.3f}s"
                + "```",
            inline=False
            )
        embed.add_field(
            name="**Clan API**",
            value="```ini"
                + f"\n{'[Last]':<10} {(self.coc_client.clan_api[-1] if len(self.coc_client.clan_api) > 0 else 0)/1000:.3f}s"
                + f"\n{'[Mean]':<10} {self.coc_client.clan_api_avg/1000:.3f}s"
                + f"\n{'[Min/Max]':<10} {(min(self.coc_client.clan_api) if len(self.coc_client.clan_api) > 0 else 0)/1000:.3f}s ~ {(max(self.coc_client.clan_api) if len(self.coc_client.clan_api) > 0 else 0)/1000:.3f}s"
                + "```",
            inline=False
            )
        
        sent, rcvd = self.coc_client.api_current_throughput
        avg_rcvd, last_rcvd, max_rcvd = self.coc_client.rcvd_stats
        avg_sent, last_sent, max_sent = self.coc_client.sent_stats
        
        embed.add_field(
            name="**Throughput (sent / rcvd, per second)**",
            value="```ini"
                + f"\n{'[Now]':<6} {sent:.2f} / {rcvd:.2f}"
                + f"\n{'[Last]':<6} {last_sent:.2f} / {last_rcvd:.2f}"
                + f"\n{'[Avg]':<6} {avg_sent:.2f} / {avg_rcvd:.2f}"
                + f"\n{'[Max]':<6} {max_sent:.2f} / {max_rcvd:.2f}"
                + "```",
            inline=False
            )
        return embed
    
    @commands.group(name="cocapi")
    @commands.is_owner()
    async def cmdgrp_cocapi(self,ctx:commands.Context):
        """Manage the Clash of Clans API Client."""
        if not ctx.invoked_subcommand:
            pass
    
    @cmdgrp_cocapi.command(name="status")
    @commands.is_owner()
    async def subcmd_cocapi_status(self,ctx:commands.Context):
        """Status of the Clash of Clans API Client."""
        embed = await self.status_embed()
        view = RefreshStatus(self,ctx)
        await ctx.reply(embed=embed,view=view)
    
    @cmdgrp_cocapi.command(name="httplog")
    @commands.is_owner()
    async def subcmd_cocapi_httplog(self,ctx:commands.Context):
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
    
    @cmdgrp_cocapi.group(name="keys")
    @commands.is_owner()
    async def cmdgrp_cocapi_keys(self,ctx:commands.Context):
        """Manage the Clash of Clans API Keys."""
        if not ctx.invoked_subcommand:
            pass
    
    @cmdgrp_cocapi_keys.command(name="reload")
    @commands.is_owner()
    async def subcmd_cocapi_keys_reload(self,ctx:commands.Context):
        """
        Reload the API Keys used for the Clash of Clans API Client.

        This will reset the API Connection.
        """

        msg = await ctx.reply(f"Reloading keys...")

        await self.client_logout()

        available_clients = ['clashapi']
        for i in range(1,30):
            available_clients.append(f'clashapi{str(i)}')

        keys = []
        async for client in AsyncIter(available_clients):
            try:
                clashapi_login = await self.bot.get_shared_api_tokens(client)
            except:
                continue
            if clashapi_login.get("username") is None:
                continue
            if clashapi_login.get("password") is None:
                continue

            client = coc.Client(
                key_count=int(clashapi_login.get("keys",1)),
                key_names='project-g',
                )
            await client.login(clashapi_login.get("username"),clashapi_login.get("password"))
            keys.extend(client.http._keys)
            await client.close()

        await self.config.client_keys.set(keys)
        await self.client_login()
        await msg.edit(content=f"Found {len(keys)} keys. Reloaded API Client.")

    @cmdgrp_cocapi_keys.command(name="reset")
    @commands.is_owner()
    async def subcmd_cocapi_keys_reset(self,ctx:commands.Context):
        """
        Resets the API Keys used for the Clash of Clans API Client.

        This will reset the API Connection and default to Username/Password login.
        """

        msg = await ctx.reply(f"Reloading keys...")

        await self.client_logout()
        await self.config.client_keys.clear()

        await self.client_login()
        await msg.edit(content=f"Reset API Client to Username/Password login.")
    
    ############################################################
    #####
    ##### EVENTS
    #####
    ############################################################
    @coc.ClientEvents.event_error()
    async def clash_event_error(self,exception:Exception):
        if isinstance(exception,coc.HTTPException):
            # suppress 404 (notFound) and 503 (Maintenance) errors
            if exception.status in [404,503]:
                return
        if isinstance(exception,asyncio.CancelledError):
            return
        COC_LOG.exception(f"Clash Event Error: {exception}",exc_info=exception)

    @coc.ClientEvents.maintenance_start()
    async def clash_maintenance_start(self):
        self.coc_client.maintenance = True

        COC_LOG.warning(f"Clash Maintenance Started.\n"
            + text2art("Clash Maintenance Started",font="small")
            )
        await GlobalClient.update_bot_status(0,'Clash Maintenance!')

    @coc.ClientEvents.maintenance_completion()
    async def clash_maintenance_complete(self,time_started):
        await self.coc_client.http_throttler.reset_counter()
        self.coc_client.maintenance = False

        maint_start = pendulum.instance(time_started)
        maint_end = pendulum.now()

        COC_LOG.warning(f"Clash Maintenance Completed. Maintenance took: {maint_end.diff(maint_start).in_minutes()} minutes.\n"
            + text2art("Clash Maintenance Completed",font="small")
            )
        await GlobalClient.update_bot_status(0,'Clash of Clans!')

class RefreshStatus(DefaultView):
    def __init__(self,cog:ClashOfClansMain,context:Union[discord.Interaction,commands.Context]):

        button = DiscordButton(
            function=self._refresh_embed,
            emoji=EmojisUI.REFRESH,
            label="Refresh",
            )

        super().__init__(context,timeout=9999999)
        self.cog = cog
        self.is_active = True
        self.add_item(button)
    
    async def _refresh_embed(self,interaction:discord.Interaction,button:DiscordButton):
        await interaction.response.defer()
        embed = await self.cog.status_embed()
        await interaction.followup.edit_message(interaction.message.id,embed=embed)