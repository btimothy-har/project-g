import coc
import random
import discord
import asyncio
import hashlib
import pendulum

from typing import *

from discord.ext import tasks

from redbot.core import Config, commands, app_commands
from redbot.core.commands import Context
from redbot.core.utils import AsyncIter, bounded_gather
from redbot.core.bot import Red

from coc_main.api_client import BotClashClient as client
from coc_main.coc_objects.clans.clan import aClan
from coc_main.discord.clan_link import ClanGuildLink
from coc_main.utils.components import clash_embed
from coc_main.utils.checks import is_admin

from .components.application_panel import GuildApplicationPanel, ClanApplyMenu, ClanApplyMenuUser
from .components.create_application_panel import CreateApplicationMenu
from .components.exceptions import InvalidApplicationChannel
from .components.autocomplete import autocomplete_guild_apply_panels

bot_client = client()

class ClanApplications(commands.Cog):
    """Commands & Components to handle Clan Applications."""

    __author__ = bot_client.author
    __version__ = bot_client.version

    def __init__(self,bot:Red):
        self.bot: Red = bot
        self._update_lock = asyncio.Lock()
    
    def format_help_for_context(self, ctx: commands.Context) -> str:
        context = super().format_help_for_context(ctx)
        return f"{context}\n\nAuthor: {self.__author__}\nVersion: {self.__version__}"
    
    ############################################################
    #####
    ##### ASSISTANT FUNCTIONS
    #####
    ############################################################
    @commands.Cog.listener()
    async def on_assistant_cog_add(self,cog:commands.Cog):
        schema = [
            {
                "name": "_assistant_clan_application",
                "description": "Starts the process for a user to apply to or join a Clan in the Alliance. When completed, returns the ticket channel that the application was created in.",
                "parameters": {
                    "type": "object",
                    "properties": {},
                    },
                }
            ]
        await cog.register_functions(cog_name="ClanApplications", schemas=schema)
    
    async def _assistant_clan_application(self,user:discord.User,channel:discord.TextChannel,guild:discord.Guild,*args,**kwargs) -> str:
        if not guild:
            return f"This can only be used from a Guild Channel."
        
        application_id = await ClanApplyMenuUser.assistant_user_application(user,channel)
        
        if not application_id:
            return f"{user.display_name} did not complete the application process."
        
        app_channel = None
        now = pendulum.now()

        while True:
            rt = pendulum.now()
            if rt.int_timestamp - now.int_timestamp > 60:
                break

            application = await bot_client.coc_db.db__clan_application.find_one({'_id':application_id})
            app_channel = guild.get_channel(application.get('ticket_channel',0))
            if app_channel:
                break
            await asyncio.sleep(0.5)
        
        if app_channel:
            ret_channel = {
                'channel_id': app_channel.id,
                'channel_name': app_channel.name,
                'jump_url': app_channel.jump_url
                }
            return f"{user.display_name} completed the application process. Their application ticket is in the channel {ret_channel}"

        return f"{user.display_name} completed the application process, but the ticket channel could not be found."

    ############################################################
    #####
    ##### APPLICATION CHANNEL LISTENER
    #####
    ############################################################
    @commands.Cog.listener("on_guild_channel_create")
    async def recruiting_ticket_listener(self,channel):
        
        await asyncio.sleep(2)
        if isinstance(channel,discord.TextChannel):
            try:
                await ClanApplyMenuUser._listener_user_application(channel)
            except InvalidApplicationChannel:
                return
            except Exception as e:
                bot_client.coc_main_log.exception(f"Error in recruiting_ticket_listener: {e}")
    
    ############################################################
    #####
    ##### COMMAND GROUP: CLAN APPLY
    #####
    ############################################################
    @commands.group(name="clanapply",aliases=["clanapplication"])
    @commands.guild_only()
    async def command_group_clan_application(self,ctx):
        """
        Command group for Clan Applications.
        """
        if not ctx.invoked_subcommand:
            pass

    app_command_group_application = app_commands.Group(
        name="clan-application",
        description="Command group for Clan Applications.",
        guild_only=True
        )
    
    ##################################################
    ### CLANAPPLY / CHECK
    ##################################################    
    @command_group_clan_application.command(name="check")
    @commands.guild_only()
    async def command_subgroup_clan_application_check(self,ctx:commands.Context):
        """
        Checks the current channel for an Application.
        """

        if not isinstance(ctx.channel,discord.TextChannel):
            embed = await clash_embed(
                context=ctx,
                message=f"Please use this command in a Text Channel.",
                success=False
                )
            return await ctx.reply(embed=embed)
        
        try:
            application = await ClanApplyMenuUser._listener_user_application(ctx.channel)
        except InvalidApplicationChannel:
            embed = await clash_embed(
                context=ctx,
                message=f"This doesn't look like a valid Application Channel.",
                success=False
                )
            return await ctx.reply(embed=embed)
        else:
            await ctx.send(f"{application.get('bot_prefix','.')}add <@{application.get('applicant_id',0)}>")
            await ctx.tick()
    
    @app_command_group_application.command(name="check",
        description="Checks the current channel for an Application.")
    @app_commands.guild_only()
    async def app_command_group_application_check(self,interaction:discord.Interaction):
        
        await interaction.response.defer(ephemeral=True)

        if not isinstance(interaction.channel,discord.TextChannel):
            embed = await clash_embed(
                context=interaction,
                message=f"Please use this command in a Text Channel.",
                success=False
                )
            return await interaction.followup.send(embed=embed,ephemeral=True)
        
        try:
            application = await ClanApplyMenuUser._listener_user_application(interaction.channel)

        except InvalidApplicationChannel:
            embed = await clash_embed(
                context=interaction,
                message=f"This doesn't look like a valid Application Channel.",
                success=False
                )
            return await interaction.followup.send(embed=embed,ephemeral=True)
        else:
            await interaction.channel.send(f"{application.get('bot_prefix','.')}add <@{application.get('applicant_id',0)}>")
            embed = await clash_embed(
                context=interaction,
                message=f"Application found. Output generated.",
                success=True
                )
            return await interaction.followup.send(embed=embed,ephemeral=True)
    
    ############################################################
    #####
    ##### COMMAND GROUP: CLAN APPLY / PANELS
    #####
    ############################################################    
    @command_group_clan_application.group(name="panels")
    @commands.guild_only()
    async def command_subgroup_clan_application_panels(self,ctx):
        """
        Configure Application Panels.
        """
        if not ctx.invoked_subcommand:
            pass

    app_command_subgroup_application_panels = app_commands.Group(
        name="panels",
        description="Command group for Clan Applications.",
        parent=app_command_group_application,
        guild_only=True
        )   
    
    ##################################################
    ### CLANAPPLY / PANELS / LIST
    ##################################################
    @command_subgroup_clan_application_panels.command(name="list")
    @commands.guild_only()
    @commands.admin()
    async def command_subgroup_clan_application_panels_list(self,ctx):
        """
        List all Application Panels in this Server.
        """
        
        embed = await clash_embed(
            context=ctx,
            title="**Application Panels**"
            )
        
        application_panels = await GuildApplicationPanel.get_for_guild(ctx.guild.id)
        a_iter = AsyncIter(application_panels)
        async for panel in a_iter:
            embed.add_field(
                name=f"**{getattr(panel.channel,'name','Unknown Channel')}**",
                value=f"\nMessage: {getattr(await panel.fetch_message(),'jump_url','')}"
                    + f"\nTicket Tool Channel {getattr(panel.listener_channel,'mention','Unknown Channel')}"
                    + f"\nTicket Tool Prefix `{panel.tickettool_prefix}`"
                    + f"\nCan Applicants choose Clans? `{panel.can_user_select_clans}`"
                    + f"\n\n__Q1__"
                    + f"\nText: {panel.text_q1}"
                    + f"\nPlaceholder: {panel.placeholder_q1}"
                    + f"\n\n__Q2__"
                    + f"\nText: {panel.text_q2}"
                    + f"\nPlaceholder: {panel.placeholder_q2}"
                    + f"\n\n__Q3__"
                    + f"\nText: {panel.text_q3}"
                    + f"\nPlaceholder: {panel.placeholder_q3}"
                    + f"\n\n__Q4__"
                    + f"\nText: {panel.text_q4}"
                    + f"\nPlaceholder: {panel.placeholder_q4}"
                    + f"\n\u200b",
                inline=False
                )
        await ctx.reply(embed=embed)
    
    @app_command_subgroup_application_panels.command(name="list",
        description="List all Application Panels in this Server.")
    @app_commands.check(is_admin)
    @app_commands.guild_only()
    async def app_command_subgroup_application_panels_list(self,interaction:discord.Interaction):
        
        await interaction.response.defer()
        
        embed = await clash_embed(
            context=interaction,
            title="**Application Panels**"
            )
        
        application_panels = await GuildApplicationPanel.get_for_guild(interaction.guild.id)
        a_iter = AsyncIter(application_panels)
        async for panel in a_iter:
            embed.add_field(
                name=f"**{getattr(panel.channel,'name','Unknown Channel')}**",
                value=f"\nMessage: {getattr(await panel.fetch_message(),'jump_url','')}"
                    + f"\nTicket Tool Channel {getattr(panel.listener_channel,'mention','Unknown Channel')}"
                    + f"\nTicket Tool Prefix `{panel.tickettool_prefix}`"
                    + f"\nCan Applicants choose Clans? `{panel.can_user_select_clans}`"
                    + f"\n\n__Q1__"
                    + f"\nText: {panel.text_q1}"
                    + f"\nPlaceholder: {panel.placeholder_q1}"
                    + f"\n\n__Q2__"
                    + f"\nText: {panel.text_q2}"
                    + f"\nPlaceholder: {panel.placeholder_q2}"
                    + f"\n\n__Q3__"
                    + f"\nText: {panel.text_q3}"
                    + f"\nPlaceholder: {panel.placeholder_q3}"
                    + f"\n\n__Q4__"
                    + f"\nText: {panel.text_q4}"
                    + f"\nPlaceholder: {panel.placeholder_q4}"
                    + f"\n\u200b",
                inline=False
                )
        await interaction.edit_original_response(embed=embed,view=None)
    
    ##################################################
    ### CLANAPPLY / PANELS / CREATE
    ##################################################
    @command_subgroup_clan_application_panels.command(name="create")
    @commands.guild_only()
    @commands.admin()
    async def command_subgroup_clan_application_panels_create(self,
        ctx:commands.Context,
        channel_id:int,
        listener_channel_id:int,
        can_user_select_clans:bool=True):
        """
        Create an Application Panel.
        """

        channel = ctx.guild.get_channel(channel_id)
        listener = ctx.guild.get_channel(listener_channel_id)

        if not isinstance(channel,discord.TextChannel):
            return await ctx.reply(f"Please specify a valid Text Channel.")
        
        if not isinstance(channel,discord.TextChannel):
            return await ctx.reply(f"Please specify a valid Text Channel.")

        view = CreateApplicationMenu(ctx,channel,listener,can_user_select_clans)
        await view.start()
    
    @app_command_subgroup_application_panels.command(name="create",
        description="Create an Application Panel.")
    @app_commands.check(is_admin)
    @app_commands.guild_only()
    @app_commands.describe(
        channel="The Channel to create the Panel in.",
        listener="The Channel to send Ticket Tool commands in.",
        can_user_select_clans="Can Applicants choose Clans to apply to?")
    async def app_command_subgroup_application_panels_create(self,
        interaction:discord.Interaction,
        channel:discord.TextChannel,
        listener:discord.TextChannel,
        can_user_select_clans:bool=True):
        
        await interaction.response.defer()

        view = CreateApplicationMenu(interaction,channel,listener,can_user_select_clans)    
        await view.start()
    
    ##################################################
    ### CLANAPPLY / PANELS / DELETE
    ##################################################
    @command_group_clan_application.command(name="delete")
    @commands.guild_only()
    @commands.admin()
    async def command_group_clan_application_delete(self,ctx,channel_id:int):
        """
        Delete an Application Panel.
        """
        channel = ctx.guild.get_channel(channel_id)

        if not isinstance(channel,discord.TextChannel):
            embed = await clash_embed(
                context=ctx,
                message=f"Please specify a valid channel.",
                success=False
                )
            return await ctx.reply(embed=embed)
        
        panel = await GuildApplicationPanel.get_panel(guild_id=ctx.guild.id,channel_id=channel_id)
        if not panel:
            embed = await clash_embed(
                context=ctx,
                message=f"An Application Panel does not exist for this channel.",
                success=False
                )
            return await ctx.reply(embed=embed)
        
        await panel.delete()
        
        embed = await clash_embed(
            context=ctx,
            message=f"Application Panel deleted.",
            success=True
            )
        await ctx.reply(embed=embed)

    @app_command_subgroup_application_panels.command(name="delete",
        description="Delete an Application Panel.")
    @app_commands.check(is_admin)
    @app_commands.guild_only()
    @app_commands.autocomplete(panel=autocomplete_guild_apply_panels)
    @app_commands.describe(
        panel="The Application Panel to delete.")
    async def app_command_subgroup_application_panels_delete(self,interaction:discord.Interaction,panel:str):
        
        await interaction.response.defer()

        channel = interaction.guild.get_channel(int(panel))

        get_panel = await GuildApplicationPanel.get_panel(guild_id=channel.guild.id,channel_id=channel.id)
        await get_panel.delete()

        embed = await clash_embed(
            context=interaction,
            message=f"Application Panel deleted.",
            success=True
            )
        await interaction.edit_original_response(embed=embed,view=None)
    
    ############################################################
    #####
    ##### BACKGROUND PANEL UPDATES
    #####
    ############################################################
    @tasks.loop(minutes=30)
    async def update_application_panels(self):
        if self._update_lock.locked():
            return
        
        async with self._update_lock:
            guild_iter = AsyncIter(self.bot.guilds)
            tasks = [ClanApplications.update_for_guild(guild) async for guild in guild_iter]
            await bounded_gather(*tasks)

    @staticmethod
    async def update_for_guild(guild:discord.Guild):
        guild_panels = await GuildApplicationPanel.get_for_guild(guild.id)
        linked_clans = await ClanGuildLink.get_for_guild(guild.id)

        if len(guild_panels) == 0 or len(linked_clans) == 0:
            return
        all_clans = [c async for c in bot_client.coc.get_clans([c.tag for c in linked_clans]) if c.is_alliance_clan]

        if len(all_clans) == 0:
            return
        
        if guild.id == 688449973553201335:
            arix_rank = {
                '#20YLR2LUJ':1,
                '#28VUPJRPU':2,
                '#2YL99GC9L':3,
                '#92G9J8CG':4
                }
            clans = sorted(
                all_clans,
                key=lambda c:((arix_rank.get(c.tag,999)*-1),c.level,c.max_recruitment_level,c.capital_points),
                reverse=True
                )
        else:
            clans = sorted(
                all_clans,
                key=lambda c:(c.level,c.max_recruitment_level,c.capital_points),
                reverse=True
                )

        embed = await ClanApplications.guild_application_panel_embed(guild,clans)

        async for panel in AsyncIter(guild_panels):
            panel_view = ClanApplyMenu(
                panel=panel,
                list_of_clans=clans
                )
            await panel.send_to_discord(
                embed=embed,
                view=panel_view
                )
        bot_client.coc_main_log.info(f"Application Panels for {guild.name} ({guild.id}) updated.")

    @staticmethod
    async def guild_application_panel_embed(guild:discord.Guild,clans:List[aClan]) -> discord.Embed:
        if guild.id == 688449973553201335:
            embed = await clash_embed(
                context=bot_client.bot,
                title=f"**Welcome to the AriX Alliance!**",
                message=f"Our clans prioritize a social environment for members that are always ready to try new strategies and constantly improve themselves, "
                    + f"to have good banter, win wars and get the support of a very active community. "
                    + f"Our Clans try to mix the competitiveness of wars with a fun and enjoyable server to keep the game fun overall."
                    + f"\n\nWe hope you'll enjoy your stay! <a:zzzpikachuhello:965872920725426176>"
                    + f"\n\n**Server Link: https://discord.gg/arix **",
                thumbnail=str(guild.icon),
                show_author=False
                )
        else:
            embed = await clash_embed(
                context=bot_client.bot,
                title=f"**Apply to Join!**",
                message=f"Thinking of joining {guild.name}? Get started by picking one or more Clans to apply to."
                    + f"\n\n**Tip:** For a smoother experience, link your Clash accounts with `$profile` before applying."
                    + f"\n\u200b",
                thumbnail=str(guild.icon),
                show_author=False
                )
        async for c in AsyncIter(clans):
            embed.add_field(
                name=f"**{c.title}**",
                value=f"{c.summary_description}"
                    + f"\nRecruiting: {c.recruitment_level_emojis}"
                    + f"\n\u200b",
                inline=False
                )
        return embed