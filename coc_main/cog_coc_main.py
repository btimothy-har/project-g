import coc
import os

from typing import *

from redbot.core import Config, commands
from redbot.core.data_manager import cog_data_path
from redbot.core.utils import AsyncIter

from .api_client import BotClashClient

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
    __version__ = "2023.11.5"

    def __init__(self,bot):
        self.bot = bot
        self.client = None

        self.config = Config.get_conf(self,identifier=644530507505336330,force_registration=True)
        default_global = {
            "client_keys":[],
            "throttler":0
            }
        self.config.register_global(**default_global)

    def format_help_for_context(self, ctx: commands.Context) -> str:
        context = super().format_help_for_context(ctx)
        return f"{context}\n\nAuthor: {self.__author__}\nVersion: {self.__version__}"

    ##################################################
    ### COG LOAD / UNLOAD
    ##################################################
    async def cog_load(self):
        self.bot.coc_log_path = f"{cog_data_path(self)}/logs"
        if not os.path.exists(self.bot.coc_log_path):
            os.makedirs(self.bot.coc_log_path)

        self.bot.coc_report_path = f"{cog_data_path(self)}/reports"
        if not os.path.exists(self.bot.coc_report_path):
            os.makedirs(self.bot.coc_report_path)
        
        self.bot.coc_imggen_path = f"{cog_data_path(self)}/imggen"
        if not os.path.exists(self.bot.coc_imggen_path):
            os.makedirs(self.bot.coc_imggen_path)

        keys = await self.config.client_keys()

        self.client = await BotClashClient.initialize(
            bot=self.bot,
            author=self.__author__,
            version=self.__version__,
            client_keys=keys,
            )
        
    async def cog_unload(self):
        self.client._is_initialized = False
        cog = self.bot.get_cog('ClashOfClansTasks')
        if cog:
            await cog.shutdown()

        await self.client.shutdown()
        del self.client

    @commands.group(name="cocreload")
    @commands.is_owner()
    async def command_reload_project_g(self,ctx:commands.Context):
        """
        Commands to reload Cog Configuration.
        """
        if not ctx.invoked_subcommand:
            pass
    
    @command_reload_project_g.command(name="nebula")
    @commands.is_owner()
    async def command_reload_nebula(self,ctx:commands.Context):
        """
        Reload N.E.B.U.L.A. Cogs.
        """

        await ctx.invoke(self.bot.get_command("reload"),'coc_data')
        await ctx.invoke(self.bot.get_command("reload"),'coc_commands', 'coc_leaderboards', 'g_eclipse', 'g_bank')
        await ctx.message.delete()
    
    @command_reload_project_g.command(name="meteor")
    @commands.is_owner()
    async def command_reload_meteor(self,ctx:commands.Context):
        """
        Reload M.E.T.E.O.R. Cogs.
        """

        await ctx.invoke(self.bot.get_command("reload"),'coc_data')
        await ctx.message.delete()
    
    @command_reload_project_g.command(name="keys")
    @commands.is_owner()
    async def command_reload_keys(self,ctx:commands.Context):

        msg = await ctx.reply(f"Reloading keys...")
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
        await msg.edit(content=f"Found {len(keys)} keys. To login with these keys, reload the cog.")