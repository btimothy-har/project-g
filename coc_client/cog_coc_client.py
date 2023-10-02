import os

from redbot.core import commands
from redbot.core.data_manager import cog_data_path
from .api_client import BotClashClient

############################################################
############################################################
#####
##### CLIENT COG
#####
############################################################
############################################################
class ClashOfClansClient(commands.Cog):
    """
    API Client connector for Clash of Clans

    This cog uses the [coc.py Clash of Clans API wrapper](https://cocpy.readthedocs.io/en/latest/).

    Client parameters are stored RedBot's API framework, using the `[p]set api clashapi` command. The accepted parameters are as follows:
    - `username` : API Username
    - `password` : API Password
    - `keys` : Number of keys to use. Defaults to 1.

    You can register for a Username and Password at https://developer.clashofclans.com.

    This cog also includes support for the Clash DiscordLinks service. If you have a username and password, set them with `[p]set api clashlinks` (parameters: `username` and `password`).

    The use of Clash DiscordLinks is optional.
    """

    __author__ = "bakkutteh"
    __version__ = "1.1.0"

    def __init__(self,bot):        
        self.bot = bot
        self.client = None

        self.bot.coc_log_path = f"{cog_data_path(self)}/logs"
        if not os.path.exists(self.bot.coc_log_path):
            os.makedirs(self.bot.coc_log_path)

        self.bot.coc_report_path = f"{cog_data_path(self)}/reports"
        if not os.path.exists(self.bot.coc_report_path):
            os.makedirs(self.bot.coc_report_path)
        
        self.bot.coc_imggen_path = f"{cog_data_path(self)}/imggen"
        if not os.path.exists(self.bot.coc_imggen_path):
            os.makedirs(self.bot.coc_imggen_path)

    def format_help_for_context(self, ctx: commands.Context) -> str:
        context = super().format_help_for_context(ctx)
        return f"{context}\n\nAuthor: {self.__author__}\nVersion: {self.__version__}"

    ##################################################
    ### COG LOAD
    ##################################################
    async def cog_load(self):
        self.client = await BotClashClient.initialize(self.bot)
        self.bot.coc_state = self.client 
    
    ##################################################
    ### COG LOAD
    ##################################################
    async def cog_unload(self):
        await self.client.shutdown()
        del self.client