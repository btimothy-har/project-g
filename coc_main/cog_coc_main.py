import os
import discord
import pendulum

from typing import *
from mongoengine import *

from redbot.core import commands, app_commands
from redbot.core.data_manager import cog_data_path

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

    This cog also includes support for the Clash DiscordLinks service. If you have a username and password, set them with `[p]set api clashlinks` (parameters: `username` and `password`).

    The use of Clash DiscordLinks is optional.
    """

    __author__ = "bakkutteh"
    __version__ = "2023.10.10"

    def __init__(self,bot):
        self.bot = bot
        self.client = None

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
            
        self.client = await BotClashClient.initialize(self.bot,self.__author__,self.__version__)
    
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