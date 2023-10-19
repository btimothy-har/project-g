import coc
import os
import discord
import pendulum

from typing import *
from mongoengine import *

from redbot.core import Config, commands, app_commands
from redbot.core.data_manager import cog_data_path
from redbot.core.utils import AsyncIter

from .api_client import BotClashClient

from .utils.components import DefaultView, DiscordModal, DiscordButton, clash_embed

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
    __version__ = "2023.10.16"

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
    ### COG LOAD
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
        throttler = await self.config.throttler()
            
        self.client = await BotClashClient.initialize(
            bot=self.bot,
            author=self.__author__,
            version=self.__version__,
            client_keys=keys,
            throttler=throttler
            )
    
    ##################################################
    ### COG LOAD
    ##################################################
    async def cog_unload(self):
        await self.client.shutdown()
        del self.client

    @commands.command(name="reloadg")
    @commands.is_owner()
    async def command_reload_clash(self,ctx:commands.Context):
        """
        Reload the Clash of Clans API Client.
        """
        await ctx.invoke(self.bot.get_command("reload"),'coc_commands', 'coc_leaderboards', 'g_eclipse', 'g_bank')
        await ctx.message.delete()
    
    @commands.command(name="reloadkeys")
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
                key_names='Created for Project G, from coc.py',
                )
            await client.login(clashapi_login.get("username"),clashapi_login.get("password"))
            keys.extend(client.http._keys)
            await client.close()

        await self.config.client_keys.set(keys)
        await msg.edit(content=f"Found {len(keys)} keys. To login with these keys, reload the cog.")
    
    @commands.command(name="cocthrottler")
    @commands.is_owner()
    async def command_toggle_throttler(self,ctx:commands.Context):

        current_throttler = await self.config.throttler()
        if current_throttler in [0,1]:
            await self.config.throttler.set(2)
            await ctx.reply(f"Batch Throttler enabled. Reload the cog to take effect.")

        if current_throttler == 2:
            await self.config.throttler.set(1)
            await ctx.reply(f"Basic Throttler enabled. Reload the cog to take effect.")
    
    ##################################################
    ### REPORT BUTTON
    ##################################################
    @commands.command(name="report")
    @commands.cooldown(rate=1,per=60,type=commands.BucketType.user)
    @commands.guild_only()
    async def command_report(self,ctx:commands.Context):
        """
        Report an issue to the Bot Owner.        
        """
        report_view = ReportButton(ctx)

        await ctx.reply(f"Click the button to send a report.",view=report_view)
    
    @app_commands.command(
        name="report",
        description="Report an issue to the Bot Owner.")
    @app_commands.guild_only()
    @app_commands.checks.cooldown(rate=1,per=60)
    async def app_command_report(self,interaction:discord.Interaction):

        report_view = ReportButton(interaction)
        await interaction.response.send_modal(report_view.report_modal)

class ReportButton(DefaultView):
    def __init__(self,context:Union[discord.Interaction,commands.Context]):
        self.message = context.message        
        super().__init__(context)

        self.is_active = True

        button = DiscordButton(
            function=self.send_modal,
            label=f"Click to Report an Issue",
            )
        self.add_item(button)
    
    async def send_modal(self,interaction:discord.Interaction,button:DiscordButton):
        await interaction.response.send_modal(self.report_modal)
        self.clear_items()        
        await interaction.followup.edit_message(interaction.message.id,view=self)
    
    async def _callback_send_report(self,interaction:discord.Interaction,modal:DiscordModal):
        await interaction.response.defer()

        mesge = await interaction.followup.send(
            content=f"Thanks for the report! I've sent it to the bot owner.",
            wait=True
            )

        channel = interaction.client.get_channel(1161269740594020403)
        summary = modal.children[0].value
        describe = modal.children[1].value

        embed = await clash_embed(
            context=interaction,
            message=f"**Summary:** {summary}"
                + f"\n\n**Description**"
                + f"\n{describe}",
            timestamp=pendulum.now()
            )
        embed.add_field(
            name="User",
            value=f"{interaction.user.mention} ({interaction.user.id})",
            inline=False
            )
        embed.add_field(
            name="Guild",
            value=f"{interaction.guild.name}",
            inline=True
            )
        embed.add_field(
            name="Channel",
            value=f"{interaction.channel.mention}",
            inline=True
            )
        embed.add_field(
            name="Message",
            value=f"{mesge.jump_url}",
            inline=True
            )        
        await channel.send(embed=embed)

    @property
    def report_modal(self):
        modal = DiscordModal(
            function=self._callback_send_report,
            title=f"Create Application Menu",
            )
        summary = discord.ui.TextInput(
            label="Title",
            style=discord.TextStyle.short,
            placeholder="Use this to summarize your report.",
            required=True
            )
        describe = discord.ui.TextInput(
            label="Message",
            style=discord.TextStyle.long,
            placeholder="Provide more details here. The more the better!",
            required=True
            )
        modal.add_item(summary)
        modal.add_item(describe)
        return modal