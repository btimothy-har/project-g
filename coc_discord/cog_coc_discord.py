import discord
import asyncio
import pendulum
import logging
import os
import coc

from typing import *

from discord.ext import tasks
from collections import defaultdict

from redbot.core import commands, app_commands
from redbot.core.utils import AsyncIter, bounded_gather
from redbot.core.bot import Red
from redbot.core.data_manager import cog_data_path

from coc_main.cog_coc_main import ClashOfClansMain as coc_main
from coc_main.client.global_client import GlobalClient

from coc_main.coc_objects.clans.clan import aClan
from coc_main.discord.clan_link import ClanGuildLink
from coc_main.discord.member import aMember
from coc_main.discord.guild import aGuild

from coc_main.utils.constants.coc_emojis import EmojisClash, EmojisCapitalHall, EmojisLeagues
from coc_main.utils.constants.ui_emojis import EmojisUI
from coc_main.utils.components import clash_embed
from coc_main.utils.checks import is_admin

from coc_data.cog_coc_data import ClashOfClansData
from coc_data.tasks.raid_tasks import ClanRaidLoop

from .panels.application_panel import GuildApplicationPanel, ClanApplyMenu, ClanApplyMenuUser
from .panels.create_application_panel import CreateApplicationMenu
from .panels.clan_panel import GuildClanPanel

from .feeds.tasks import FeedTasks
from .feeds.clan_feed import ClanDataFeed
from .feeds.reminders import EventReminder

from .exceptions import InvalidApplicationChannel
from .autocomplete import autocomplete_guild_apply_panels, autocomplete_guild_clan_panels

LOG = logging.getLogger("coc.discord")

class ClashOfClansDiscord(commands.Cog,GlobalClient):
    """Components to integrate Clash of Clans with Discord."""

    _guild_locks = defaultdict(asyncio.Lock)

    __author__ = coc_main.__author__
    __version__ = coc_main.__version__

    def __init__(self):
        self.loop_update_lock = asyncio.Lock()
        self.war_reminder_lock = asyncio.Lock()
    
    def format_help_for_context(self, ctx: commands.Context) -> str:
        context = super().format_help_for_context(ctx)
        return f"{context}\n\nAuthor: {self.__author__}\nVersion: {self.__version__}"

    @property
    def bot(self) -> Red:
        return GlobalClient.bot
    
    @property
    def coc_data(self) -> ClashOfClansData:
        return self.bot.get_cog("ClashOfClansData")
    
    ############################################################
    #####
    ##### COG LOAD/UNLOAD
    #####
    ############################################################
    async def cog_load(self):
        log_path = f"{cog_data_path(self)}/logs"
        if not os.path.exists(log_path):
            os.makedirs(log_path)

        log_formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s')
        log_handler = logging.handlers.RotatingFileHandler(
            f"{log_path}/coc_discord.log",
            maxBytes=3*1024*1024,
            backupCount=9
            )
        log_handler.setFormatter(log_formatter)
        LOG.addHandler(log_handler)

        self.coc_client.add_events(
            FeedTasks.on_clan_donation_change,
            FeedTasks.on_clan_member_join_feed,
            FeedTasks.on_clan_member_leave_feed,
            FeedTasks.on_clan_member_join_role 
            )
    
        ClanRaidLoop.add_raid_ongoing_event(FeedTasks._setup_raid_reminder)
        ClanRaidLoop.add_raid_end_event(FeedTasks._raid_ended_feed)

        asyncio.create_task(self.start_cog())
    
    async def start_cog(self):
        await self.bot.wait_until_red_ready()

        async def _update_app_panels_start(guild:discord.Guild):
            lock = ClashOfClansDiscord._guild_locks[guild.id]
            async with lock:
                await ClashOfClansDiscord.update_guild_application_panels(guild)

        guild_iter = AsyncIter(self.bot.guilds)
        tasks = [_update_app_panels_start(guild) async for guild in guild_iter]
        await bounded_gather(*tasks)

        self.run_war_reminders.start()
        self.update_application_panels.start()
        self.update_clan_panels.start()
        self.update_guild_clocks.start()
        self.update_clan_loop.start()
        self.save_member_roles.start()        
      
    async def cog_unload(self):
        self.update_application_panels.stop()
        self.update_clan_panels.stop()        
        self.save_member_roles.stop()
        self.update_guild_clocks.stop()
        self.update_clan_loop.stop()
        self.run_war_reminders.stop()

        self.coc_client.remove_events(
            FeedTasks.on_clan_donation_change,
            FeedTasks.on_clan_member_join_feed,
            FeedTasks.on_clan_member_leave_feed,
            FeedTasks.on_clan_member_join_role 
            )
        ClanRaidLoop.remove_raid_ongoing_event(FeedTasks._setup_raid_reminder)
        ClanRaidLoop.remove_raid_end_event(FeedTasks._raid_ended_feed)
        LOG.handlers.clear()
    
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
        await cog.register_functions(cog_name="ClashOfClansDiscord", schemas=schema)
    
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

            application = await self.database.db__clan_application.find_one({'_id':application_id})
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
        if not isinstance(channel, discord.TextChannel):
            return
        
        await asyncio.sleep(2)
        if isinstance(channel,discord.TextChannel):
            try:
                await ClanApplyMenuUser._listener_user_application(channel)
            except InvalidApplicationChannel:
                return
            except Exception as e:
                LOG.exception(f"Error in recruiting_ticket_listener: {e}")
    
    @commands.Cog.listener("on_member_update")
    async def member_role_sync(self,before:discord.Member,after:discord.Member):
        try:
            before_roles = sorted([r.id for r in before.roles])
            after_roles = sorted([r.id for r in after.roles])

            if before_roles != after_roles:                
                member = await aMember(after.id,after.guild.id)
                await member.sync_clan_roles()
        except Exception:
            LOG.exception("Error in member_role_sync.")
    
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

        await view.wait()
        if view.completed:
            await ClashOfClansDiscord.update_guild_application_panels(ctx.guild)
    
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

        await view.wait()
        if view.completed:
            await ClashOfClansDiscord.update_guild_application_panels(interaction.guild)
    
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

    ##################################################
    ### CLANAPPLY / PANELS / RESET
    ##################################################
    @command_group_clan_application.command(name="reset")
    @commands.guild_only()
    @commands.admin()
    async def command_group_clan_application_reset(self,ctx:commands.Context):
        """
        Resets all Application Panels.
        """

        lock = ClashOfClansDiscord._guild_locks[ctx.guild.id]

        async with lock:
            panels = await GuildApplicationPanel.get_for_guild(ctx.guild.id)
            reset_tasks = [panel.reset() for panel in panels]
            await bounded_gather(*reset_tasks)
            await ClashOfClansDiscord.update_guild_application_panels(ctx.guild)
            
            await ctx.reply(f"Application Panels have been reset.")

    @app_command_subgroup_application_panels.command(name="reset",
        description="Resets all Application Panels.")
    @app_commands.check(is_admin)
    @app_commands.guild_only()
    async def app_command_subgroup_application_panels_reset(self,interaction:discord.Interaction):
        
        await interaction.response.defer()

        lock = ClashOfClansDiscord._guild_locks[interaction.guild.id]

        async with lock:
            panels = await GuildApplicationPanel.get_for_guild(interaction.guild.id)
            reset_tasks = [panel.reset() for panel in panels]
            await bounded_gather(*reset_tasks)
            await ClashOfClansDiscord.update_guild_application_panels(interaction.guild)

            await interaction.followup.send(f"Application Panels have been reset.")
    
    ############################################################
    #####
    ##### COMMAND GROUP: CLAN PANELS
    #####
    ############################################################
    @commands.group(name="clanpanel")
    @commands.guild_only()
    @commands.admin()
    async def command_group_clan_panels(self,ctx):
        """
        Command group for Clan Panels.

        Clan Panels are a set of auto-updating embeds that display information about Clans linked to this Server.
        """
        if not ctx.invoked_subcommand:
            pass

    app_command_group_panels = app_commands.Group(
        name="clan-panel",
        description="Command group for Clan Panels.",
        guild_only=True
        )
    
    ##################################################
    ### CLANPANEL / LIST
    ##################################################
    @command_group_clan_panels.command(name="list")
    @commands.guild_only()
    @commands.admin()
    async def command_group_clan_panels_list(self,ctx:commands.Context):
        """
        List all Clan Panels in this Server.
        """

        embed = await clash_embed(
            context=ctx,
            title="**Clan Panels**"
            )
        clan_panels = await GuildClanPanel.get_for_guild(ctx.guild.id)
        a_iter = AsyncIter(clan_panels)
        async for panel in a_iter:
            embed.add_field(
                name=f"**{getattr(panel.channel,'name','Unknown Channel')}**",
                value=f"Channel: {getattr(panel.channel,'mention','Unknown Channel')}"
                    + f"\nMessage: {getattr(await panel.fetch_message(),'jump_url','')}",
                inline=False
                )
        await ctx.reply(embed=embed)
    
    @app_command_group_panels.command(name="list",
        description="List all Clan Panels in this Server.")
    @app_commands.check(is_admin)
    @app_commands.guild_only()
    async def app_command_group_panels_list(self,interaction:discord.Interaction):
        
        await interaction.response.defer()
        
        embed = await clash_embed(
            context=interaction,
            title="**Clan Panels**"
            )
        clan_panels = await GuildClanPanel.get_for_guild(interaction.guild.id)
        a_iter = AsyncIter(clan_panels)
        async for panel in a_iter:
            embed.add_field(
                name=f"**{getattr(panel.channel,'name','Unknown Channel')}**",
                value=f"Channel: {getattr(panel.channel,'mention','Unknown Channel')}"
                    + f"\nMessage: {getattr(await panel.fetch_message(),'jump_url','')}",
                inline=False
                )
        await interaction.edit_original_response(embed=embed,view=None)
    
    ##################################################
    ### CLANPANEL / CREATE
    ##################################################
    @command_group_clan_panels.command(name="create")
    @commands.guild_only()
    @commands.admin()
    async def command_group_clan_panels_create(self,ctx:commands.Context,channel_id:int):
        """
        Create a Clan Panel.
        """
        channel = ctx.guild.get_channel(channel_id)

        if not isinstance(channel,discord.TextChannel):
            embed = await clash_embed(
                context=ctx,
                message=f"Please specify a valid channel.",
                success=False
                )
            return await ctx.reply(embed=embed)
        
        panel = await GuildClanPanel.get_panel(guild_id=ctx.guild.id,channel_id=channel_id)
        if panel:
            embed = await clash_embed(
                context=ctx,
                message=f"A Clan Panel already exists for this channel.",
                success=False
                )
            return await ctx.reply(embed=embed)
        
        await GuildClanPanel.create(guild_id=channel.guild.id,channel_id=channel.id)
        embed = await clash_embed(
            context=ctx,
            message=f"Clan Panel created.",
            success=True
            )
        await ctx.reply(embed=embed)
        await ClashOfClansDiscord.update_guild_clan_panels(ctx.guild)
    
    @app_command_group_panels.command(name="create",
        description="Create a Clan Panel.")
    @app_commands.check(is_admin)
    @app_commands.guild_only()
    @app_commands.describe(
        channel="The Channel to create the Panel in.")
    async def app_command_group_panels_create(self,interaction:discord.Interaction,channel:discord.TextChannel):

        await interaction.response.defer()
        
        panel = await GuildClanPanel.get_panel(guild_id=interaction.guild.id,channel_id=channel.id)
        if panel:
            embed = await clash_embed(
                context=interaction,
                message=f"A Clan Panel already exists for this channel.",
                success=False
                )
            return await interaction.edit_original_response(embed=embed,view=None)
        
        await GuildClanPanel.create(guild_id=channel.guild.id,channel_id=channel.id)
        embed = await clash_embed(
            context=interaction,
            message=f"Clan Panel created.",
            success=True
            )
        await interaction.edit_original_response(embed=embed,view=None)
        await ClashOfClansDiscord.update_guild_clan_panels(interaction.guild)
    
    ##################################################
    ### CLANPANEL / DELETE
    ##################################################
    @command_group_clan_panels.command(name="delete")
    @commands.guild_only()
    @commands.admin()
    async def command_group_clan_panels_delete(self,ctx:commands.Context,channel_id:int):
        """
        Deletes a Clan Panel.
        """
        channel = ctx.guild.get_channel(channel_id)

        if not isinstance(channel,discord.TextChannel):
            embed = await clash_embed(
                context=ctx,
                message=f"Please specify a valid channel.",
                success=False
                )
            return await ctx.reply(embed=embed)
        
        panel = await GuildClanPanel.get_panel(guild_id=ctx.guild.id,channel_id=channel.id)
        if not panel:
            embed = await clash_embed(
                context=ctx,
                message=f"A Guild Panel does not exist for this channel.",
                success=False
                )
            return await ctx.reply(embed=embed)
                
        await panel.delete()
        embed = await clash_embed(
            context=ctx,
            message=f"Clan Panel deleted.",
            success=True
            )
        await ctx.reply(embed=embed)
        await ClashOfClansDiscord.update_guild_clan_panels(ctx.guild)

    @app_command_group_panels.command(name="delete",
        description="Delete a Clan Panel.")
    @app_commands.check(is_admin)
    @app_commands.guild_only()
    @app_commands.autocomplete(panel=autocomplete_guild_clan_panels)
    @app_commands.describe(
        panel="The Clan Panel to delete.")
    async def app_command_group_panels_delete(self,interaction:discord.Interaction,panel:str):

        await interaction.response.defer()
        
        channel = interaction.guild.get_channel(int(panel))

        get_panel = await GuildClanPanel.get_panel(guild_id=channel.guild.id,channel_id=channel.id)

        await get_panel.delete()
        embed = await clash_embed(
            context=interaction,
            message=f"Clan Panel deleted.",
            success=True
            )
        await interaction.edit_original_response(embed=embed,view=None)
        await ClashOfClansDiscord.update_guild_clan_panels(interaction.guild)
    
    ##################################################
    ### CLANPANEL / RESET
    ##################################################
    @command_group_clan_panels.command(name="reset")
    @commands.guild_only()
    @commands.admin()
    async def command_group_clan_panels_reset(self,ctx:commands.Context):
        """
        Resets all Clan Panels.
        """

        lock = ClashOfClansDiscord._guild_locks[ctx.guild.id]
        
        async with lock:
            panels = await GuildClanPanel.get_for_guild(ctx.guild.id)

            reset_tasks = [panel.reset() for panel in panels]
            await bounded_gather(*reset_tasks)
            await ClashOfClansDiscord.update_guild_clan_panels(ctx.guild)

            await ctx.reply(f"Clan Panels have been reset.")

    @app_command_group_panels.command(name="reset",
        description="Resets all Clan Panels.")
    @app_commands.check(is_admin)
    @app_commands.guild_only()
    async def app_command_group_panels_reset(self,interaction:discord.Interaction):
        await interaction.response.defer()

        lock = ClashOfClansDiscord._guild_locks[interaction.guild.id]

        async with lock:        
            panels = await GuildClanPanel.get_for_guild(interaction.guild.id)

            reset_tasks = [panel.reset() for panel in panels]
            await bounded_gather(*reset_tasks)
            await ClashOfClansDiscord.update_guild_clan_panels(interaction.guild)

            await interaction.followup.send(f"Clan Panels have been reset.")
    
    ############################################################
    #####
    ##### BACKGROUND UPDATES: CLAN LOOP
    #####
    ############################################################
    @tasks.loop(minutes=1)
    async def update_clan_loop(self):
        if self.loop_update_lock.locked():
            return        
        async with self.loop_update_lock:
            if self.coc_client.maintenance:
                return
            
            tags = []
            guild_iter = AsyncIter(self.bot.guilds)
            async for guild in guild_iter:
                links = await ClanGuildLink.get_for_guild(guild.id)
                tags.extend([link.tag for link in links])

            feeds = await ClanDataFeed.get_all()
            tags.extend([feed.tag for feed in feeds])

            reminders = await EventReminder.get_all()
            tags.extend([reminder.tag for reminder in reminders])

            loop_tags = list(set(tags))
            self.coc_client.add_clan_updates(*loop_tags)
            self.coc_data._war_loop.add_to_loop(*loop_tags)
            self.coc_data._raid_loop.add_to_loop(*loop_tags)
    
    ############################################################
    #####
    ##### BACKGROUND UPDATES: CLAN LOOP
    #####
    ############################################################
    @tasks.loop(minutes=10)
    async def update_clan_loop(self):
        if self.loop_update_lock.locked():
            return        
        async with self.loop_update_lock:
            if self.coc_client.maintenance:
                return
            
            tags = []
            guild_iter = AsyncIter(self.bot.guilds)
            async for guild in guild_iter:
                links = await ClanGuildLink.get_for_guild(guild.id)
                tags.extend([link.tag for link in links])

            feeds = await ClanDataFeed.get_all()
            tags.extend([feed.tag for feed in feeds])

            reminders = await EventReminder.get_all()
            tags.extend([reminder.tag for reminder in reminders])

            loop_tags = list(set(tags))
            self.coc_client.add_clan_updates(*loop_tags)
            self.coc_client.add_war_updates(*[reminder.tag for reminder in reminders])
            self.coc_data._raid_loop.add_to_loop(*loop_tags)
    
    @tasks.loop(minutes=1)
    async def run_war_reminders(self):
        if self.war_reminder_lock.locked():
            return
        
        async with self.war_reminder_lock:
            reminders = await EventReminder.get_war_reminders()
            a_iter = AsyncIter(reminders)
            async for reminder in a_iter:
                try:
                    try:
                        war = await self.coc_client.get_current_war(reminder.tag)
                    except (coc.Maintenance,coc.NotFound,coc.GatewayError):
                        continue
                    else:
                        if war.type in reminder.sub_type:
                            war_clan = war.get_clan(reminder.tag)
                            remind_members = [m for m in war_clan.members if m.unused_attacks > 0]
                            await reminder.send_reminder(war,*remind_members)
                except Exception:
                    LOG.exception(f"Error sending War Reminder for {reminder.tag}")
    
    @tasks.loop(minutes=5)
    async def save_member_roles(self):
        async def _save_for_guild(guild:discord.Guild):
            lock = ClashOfClansDiscord._guild_locks[guild.id]
            async with lock:
                try:
                    a_iter = AsyncIter(guild.members)
                    tasks = [aMember.save_user_roles(member.id,guild.id) async for member in a_iter if not member.bot]
                    await bounded_gather(*tasks,limit=10)

                except coc.ClashOfClansException:
                    pass
                except Exception:
                    LOG.exception(f"{guild.id} {guild.name}: Error saving Member roles.")
                
        guild_iter = AsyncIter(self.bot.guilds)
        tasks = [_save_for_guild(guild) async for guild in guild_iter]
        await bounded_gather(*tasks)
    
    @tasks.loop(minutes=5)
    async def update_guild_clocks(self):
        async def _update_clocks_for_guild(guild:discord.Guild):
            lock = ClashOfClansDiscord._guild_locks[guild.id]
            async with lock:
                try:
                    m_guild = aGuild(guild.id)
                    await m_guild.update_clocks()
                except Exception:
                    LOG.exception(f"{guild.id} {guild.name}: Error updating Guild Clocks.")
        
        guild_iter = AsyncIter(self.bot.guilds)
        tasks = [_update_clocks_for_guild(guild) async for guild in guild_iter]
        await bounded_gather(*tasks)
    
    ############################################################
    #####
    ##### BACKGROUND UPDATES: APPLICATION PANELS
    #####
    ############################################################
    @tasks.loop(minutes=30)
    async def update_application_panels(self):

        async def _start_update(guild:discord.Guild):
            lock = ClashOfClansDiscord._guild_locks[guild.id]
            async with lock:
                await ClashOfClansDiscord.update_guild_application_panels(guild)

        guild_iter = AsyncIter(self.bot.guilds)
        tasks = [_start_update(guild) async for guild in guild_iter]
        await bounded_gather(*tasks)

    @staticmethod
    async def update_guild_application_panels(guild:discord.Guild):
        
        guild_panels = await GuildApplicationPanel.get_for_guild(guild.id)
        linked_clans = await ClanGuildLink.get_for_guild(guild.id)

        if len(guild_panels) == 0 or len(linked_clans) == 0:
            return
        all_clans = [c async for c in GlobalClient.coc_client.get_clans([c.tag for c in linked_clans]) if c.is_alliance_clan]

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

        embed = await ClashOfClansDiscord.guild_application_panel_embed(guild,clans)

        async for panel in AsyncIter(guild_panels):
            panel_view = ClanApplyMenu(
                panel=panel,
                list_of_clans=clans
                )
            await panel.send_to_discord(
                embed=embed,
                view=panel_view
                )
        LOG.info(f"Application Panels for {guild.name} ({guild.id}) updated.")

    @staticmethod
    async def guild_application_panel_embed(guild:discord.Guild,clans:List[aClan]) -> discord.Embed:
        if guild.id == 688449973553201335:
            embed = await clash_embed(
                context=GlobalClient.bot,
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
                context=GlobalClient.bot,
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
    
    ############################################################
    #####
    ##### BACKGROUND UPDATES: CLAN PANELS
    #####
    ############################################################
    @tasks.loop(minutes=30)
    async def update_clan_panels(self):

        async def _start_update(guild:discord.Guild):
            lock = ClashOfClansDiscord._guild_locks[guild.id]
            async with lock:
                await ClashOfClansDiscord.update_guild_clan_panels(guild)

        guild_iter = AsyncIter(self.bot.guilds)
        
        tasks = [_start_update(guild) async for guild in guild_iter]
        await bounded_gather(*tasks)
    
    @staticmethod
    async def update_guild_clan_panels(guild:discord.Guild):
        guild_panels = await GuildClanPanel.get_for_guild(guild.id)
        linked_clans = await ClanGuildLink.get_for_guild(guild.id)

        if len(guild_panels) == 0 or len(linked_clans) == 0:
            return
        linked_clans = [c async for c in GlobalClient.coc_client.get_clans([c.tag for c in linked_clans]) if c.is_alliance_clan]

        if len(linked_clans) == 0:
            return
        
        embeds = []
        if guild.id == 688449973553201335:
            arix_rank = {
                '#20YLR2LUJ':1,
                '#28VUPJRPU':2,
                '#2YL99GC9L':3,
                '#92G9J8CG':4
                }
            clans = sorted(
                linked_clans,
                key=lambda c:((arix_rank.get(c.tag,999)*-1),c.level,c.max_recruitment_level,c.capital_points),
                reverse=True
                )
        else:
            clans = sorted(
                linked_clans,
                key=lambda c:(c.level,c.max_recruitment_level,c.capital_points),
                reverse=True
                )
        
        async for clan in AsyncIter(clans):
            embed = await ClashOfClansDiscord.guild_clan_panel_embed(clan=clan)
            embeds.append({
                'clan':clan,
                'embed':embed
                }
            )
        # Overwrite for Alliance Home Server
        if guild.id in [1132581106571550831,680798075685699691]:
            family_clans = await GlobalClient.coc_client.get_alliance_clans()
            async for clan in AsyncIter(family_clans):
                if clan.tag not in [c.tag for c in clans]:
                    linked_servers = await ClanGuildLink.get_links_for_clan(clan.tag)
                    if len(linked_servers) == 0:
                        continue
                    embed = await ClashOfClansDiscord.guild_clan_panel_embed(
                        clan=clan,
                        guild=linked_servers[0].guild
                        )
                    embeds.append({
                        'clan':clan,
                        'embed':embed
                        }
                    )                
        async for panel in AsyncIter(guild_panels):
            await panel.send_to_discord(embeds)
        LOG.info(f"Clan Panels for {guild.name} ({guild.id}) updated.")
    
    @staticmethod
    async def guild_clan_panel_embed(clan:aClan,guild:Optional[discord.Guild]=None) -> discord.Embed:
        if guild:
            if guild.vanity_url:
                invite = await guild.vanity_invite()                        
            else:
                normal_invites = await guild.invites()
                if len(normal_invites) > 0:
                    invite = normal_invites[0]
                else:
                    invite = await guild.channels[0].create_invite()

        embed = await clash_embed(
            context=GlobalClient.bot,
            title=f"**{clan.title}**",
            message=f"{EmojisClash.CLAN} Level {clan.level}\u3000"
                + f"{EmojisUI.MEMBERS}" + (f" {clan.alliance_member_count}" if clan.is_alliance_clan else f" {clan.member_count}") + "\u3000"
                + f"{EmojisUI.GLOBE} {clan.location.name}\n"
                + (f"{EmojisClash.CLANWAR} W{clan.war_wins}/D{clan.war_ties}/L{clan.war_losses} (Streak: {clan.war_win_streak})\n" if clan.public_war_log else "")
                + f"{EmojisClash.WARLEAGUES}" + (f"{EmojisLeagues.get(clan.war_league.name)} {clan.war_league.name}\n" if clan.war_league else "Unranked\n")
                + f"{EmojisCapitalHall.get(clan.capital_hall)} CH {clan.capital_hall}\u3000"
                + f"{EmojisClash.CAPITALTROPHY} {clan.capital_points}\u3000"
                + (f"{EmojisLeagues.get(clan.capital_league.name)} {clan.capital_league}" if clan.capital_league else f"{EmojisLeagues.UNRANKED} Unranked") #+ "\n"
                + (f"\n\n**Join this Clan at: [{guild.name}]({str(invite)})**" if guild and invite else "")
                + f"\n\n{clan.description}"
                + f"\n\n**Recruiting**"
                + f"\nTownhalls: {clan.recruitment_level_emojis}"
                + (f"\n\n{clan.recruitment_info}" if len(clan.recruitment_info) > 0 else ""),
            thumbnail=clan.badge,
            show_author=False
            )
        return embed