import discord
import pendulum
import random

from redbot.core import commands, app_commands
from redbot.core.bot import Red
from redbot.core.utils import AsyncIter

from coc_main.api_client import BotClashClient, aClashSeason, ClashOfClansError, InvalidAbbreviation, InvalidRole
from coc_main.cog_coc_client import ClashOfClansClient

from coc_main.discord.guild import aGuild
from coc_main.discord.clan_link import ClanGuildLink, db_ClanGuildLink
from coc_main.discord.clan_panel import GuildClanPanel, db_GuildClanPanel
from coc_main.discord.application_panel import GuildApplicationPanel, db_GuildApplyPanel

from coc_main.utils.components import clash_embed
from coc_main.utils.checks import is_admin, has_manage_server

from .views.create_application_panel import CreateApplicationMenu
from .views.create_recruiting_reminder import CreateRecruitingReminder, RecruitingReminder

bot_client = BotClashClient()

async def autocomplete_guild_clan_panels(interaction:discord.Interaction,current:str):
    panels = [GuildClanPanel(db) for db in db_GuildClanPanel.objects(server_id=interaction.guild.id)]
    if current:
        sel_panels = [p for p in panels if current.lower() in str(p).lower()]
    else:
        sel_panels = panels

    return [
        app_commands.Choice(
            name=str(panel),
            value=str(panel.channel_id))
        for panel in random.sample(sel_panels,min(5,len(sel_panels)))
        ]

async def autocomplete_guild_apply_panels(interaction:discord.Interaction,current:str):
    panels = [GuildApplicationPanel(db) for db in db_GuildApplyPanel.objects(server_id=interaction.guild.id)]
    if current:
        sel_panels = [p for p in panels if current.lower() in str(p).lower()]
    else:
        sel_panels = panels

    return [
        app_commands.Choice(
            name=str(panel),
            value=str(panel.channel_id))
        for panel in random.sample(sel_panels,min(5,len(sel_panels)))
        ]

async def autocomplete_guild_recruiting_reminders(interaction:discord.Interaction,current:str):
    panels = RecruitingReminder.get_by_guild(interaction.guild.id)

    if current:
        sel_panels = [p for p in panels if current.lower() in str(p).lower()]
    else:
        sel_panels = panels

    return [
        app_commands.Choice(
            name=str(panel),
            value=str(panel.channel_id))
        for panel in random.sample(sel_panels,min(5,len(sel_panels)))
        ]

############################################################
############################################################
#####
##### CLIENT COG
#####
############################################################
############################################################
class ClashServerConfig(commands.Cog):
    """
    Clash of Clans Server Config.
    """

    __author__ = bot_client.author
    __version__ = bot_client.version

    def __init__(self,bot:Red):
        self.bot = bot

    def format_help_for_context(self, ctx: commands.Context) -> str:
        context = super().format_help_for_context(ctx)
        return f"{context}\n\nAuthor: {self.__author__}\nVersion: {self.__version__}"

    @property
    def bot_client(self) -> BotClashClient:
        return BotClashClient()

    @property
    def client(self) -> ClashOfClansClient:
        return bot_client.bot.get_cog("ClashOfClansClient")
    
    async def cog_command_error(self,ctx,error):
        if isinstance(getattr(error,'original',None),ClashOfClansError):
            embed = await clash_embed(
                context=ctx,
                message=f"{error.original.message}",
                success=False,
                timestamp=pendulum.now()
                )
            await ctx.send(embed=embed)
            return
        await self.bot.on_command_error(ctx,error,unhandled_by_cog=True)

    async def cog_app_command_error(self,interaction,error):
        if isinstance(getattr(error,'original',None),ClashOfClansError):
            embed = await clash_embed(
                context=interaction,
                message=f"{error.original.message}",
                success=False,
                timestamp=pendulum.now()
                )
            if interaction.response.is_done():
                await interaction.edit_original_response(embed=embed,view=None)
            else:
                await interaction.response.send_message(embed=embed,view=None,ephemeral=True)
            return
    
    ############################################################
    ############################################################
    #####
    ##### COMMAND DIRECTORY
    ##### - serversetup
    ##### - serversetup / clans
    ##### - serversetup / panel / list
    ##### - serversetup / panel / create
    ##### - serversetup / panel / delete
    ##### - serversetup / application / list
    ##### - serversetup / application / create
    ##### - serversetup / application / delete
    ##### - serversetup / clocks / toggleevents
    ##### - serversetup / clocks / togglechannels
    ##### - recruiting-reminders / list
    ##### - recruiting-reminders / add
    ##### - recruiting-reminders / edit
    ##### - recruiting-reminders / delete    
    #####
    ############################################################
    ############################################################

    ##################################################
    ### PARENT COMMAND GROUPS
    ##################################################
    @commands.group(name="serversetup")
    @commands.guild_only()
    async def command_group_guildset(self,ctx):
        """
        Group for Server configuration Commands.

        **This is a command group. To use the sub-commands below, follow the syntax: `$serversetup [sub-command]`.**
        """
        if not ctx.invoked_subcommand:
            pass

    app_command_group_guildset = app_commands.Group(
        name="server-setup",
        description="Group for Server configuration commands. Equivalent to [p]serversetup.",
        guild_only=True
        )
    
    ##################################################
    ### SERVERSETUP / CLANS
    ##################################################
    @command_group_guildset.command(name="clans")
    @commands.guild_only()
    @commands.admin()
    async def subcommand_group_list_clans(self,ctx):
        """
        List all Clans linked to this Server.

        To link/unlink clans, use [p]`clanset link` or [p]`clanset unlink`.
        """

        clan_links = [ClanGuildLink(db) for db in db_ClanGuildLink.objects(guild_id=ctx.guild.id)]
        
        embed = await clash_embed(
            context=ctx,
            title=f"**Linked Clans: {ctx.guild.name}**"
            )
        async for link in AsyncIter(clan_links):
            clan = await self.client.fetch_clan(link.tag)
            embed.add_field(
                name=f"**{clan.title}**",
                value=f"CoLeader Role: {getattr(link.coleader_role,'mention','None')}"
                    + f"\nElder Role: {getattr(link.elder_role,'mention','None')}"
                    + f"\nMember Role: {getattr(link.member_role,'mention','None')}",
                inline=False
                )
        await ctx.reply(embed=embed)
    
    @app_command_group_guildset.command(name="clans",
        description="List all Clans linked to this Server.")
    @app_commands.check(is_admin)
    @app_commands.guild_only()
    async def sub_appcommand_list_clans(self,interaction:discord.Interaction):
        
        await interaction.response.defer()
        clan_links = [ClanGuildLink(db) for db in db_ClanGuildLink.objects(guild_id=interaction.guild.id)]
        
        embed = await clash_embed(
            context=interaction,
            title=f"**Linked Clans: {interaction.guild.name}**"
            )
        async for link in AsyncIter(clan_links):
            clan = await self.client.fetch_clan(link.tag)
            embed.add_field(
                name=f"**{clan.title}**",
                value=f"CoLeader Role: {getattr(link.coleader_role,'mention','None')}"
                    + f"\nElder Role: {getattr(link.elder_role,'mention','None')}"
                    + f"\nMember Role: {getattr(link.member_role,'mention','None')}",
                inline=False
                )
        await interaction.edit_original_response(embed=embed,view=None)
    
    ##################################################
    ### SERVERSETUP / PANEL
    ##################################################
    @command_group_guildset.group(name="clanpanel")
    @commands.guild_only()
    @commands.admin()
    async def subcommand_group_panel(self,ctx):
        """
        Setup Clan Panels.

        Clan Panels are a set of auto-updating embeds that display information about Clans linked to this Server.
        """
        if not ctx.invoked_subcommand:
            pass

    app_subcommand_group_panel = app_commands.Group(
        name="clan-panel",
        description="Setup Clan Panels.",
        parent=app_command_group_guildset,
        guild_only=True
        )
    
    ##################################################
    ### SERVERSETUP / PANEL / LIST
    ##################################################
    @subcommand_group_panel.command(name="list")
    @commands.guild_only()
    @commands.admin()
    async def subcommand_group_guildpanel_list(self,ctx):
        """
        List all Clan Panels in this Server.
        """

        embed = await clash_embed(
            context=ctx,
            title="**Clan Panels**"
            )
        clan_panels = [GuildClanPanel(db) for db in db_GuildClanPanel.objects(server_id=ctx.guild.id)]
        for panel in clan_panels:
            embed.add_field(
                name=f"**{getattr(panel.channel,'name','Unknown Channel')}**",
                value=f"Channel: {getattr(panel.channel,'mention','Unknown Channel')}"
                    + f"\nMessage: {getattr(await panel.fetch_message(),'jump_url','')}",
                inline=False
                )
        await ctx.reply(embed=embed)
    
    @app_subcommand_group_panel.command(name="list",
        description="List all Clan Panels in this Server.")
    @app_commands.check(is_admin)
    @app_commands.guild_only()
    async def sub_appcommand_guildpanel_list(self,interaction:discord.Interaction):
        
        await interaction.response.defer()
        
        embed = await clash_embed(
            context=interaction,
            title="**Clan Panels**"
            )
        clan_panels = [GuildClanPanel(db) for db in db_GuildClanPanel.objects(server_id=interaction.guild.id)]
        for panel in clan_panels:
            embed.add_field(
                name=f"**{getattr(panel.channel,'name','Unknown Channel')}**",
                value=f"Channel: {getattr(panel.channel,'mention','Unknown Channel')}"
                    + f"\nMessage: {getattr(await panel.fetch_message(),'jump_url','')}",
                inline=False
                )
        await interaction.edit_original_response(embed=embed,view=None)
    
    ##################################################
    ### SERVERSETUP / PANEL / CREATE
    ##################################################    
    @subcommand_group_panel.command(name="create")
    @commands.guild_only()
    @commands.is_owner()
    async def subcommand_group_guildpanel_create(self,ctx,channel_id:int):
        """
        Create a Clan Panel.
        """
        guild = aGuild(ctx.guild.id)
        channel = ctx.guild.get_channel(channel_id)

        if not isinstance(channel,discord.TextChannel):
            embed = await clash_embed(
                context=ctx,
                message=f"Please specify a valid channel.",
                success=False
                )
            return await ctx.reply(embed=embed)
        
        panel = GuildClanPanel.get_panel(guild_id=ctx.guild.id,channel_id=channel_id)
        if panel:
            embed = await clash_embed(
                context=ctx,
                message=f"A Clan Panel already exists for this channel.",
                success=False
                )
            return await ctx.reply(embed=embed)
        
        await guild.create_clan_panel(channel)
        embed = await clash_embed(
            context=ctx,
            message=f"Clan Panel created.",
            success=True
            )
        await ctx.reply(embed=embed)
    
    @app_subcommand_group_panel.command(name="create",
        description="Create a Clan Panel.")
    @app_commands.check(is_admin)
    @app_commands.guild_only()
    @app_commands.describe(
        channel="The Channel to create the Panel in.")
    async def sub_appcommand_guildpanel_create(self,interaction:discord.Interaction,channel:discord.TextChannel):

        await interaction.response.defer()

        guild = aGuild(interaction.guild.id)
        
        panel = GuildClanPanel.get_panel(guild_id=interaction.guild.id,channel_id=channel.id)
        if panel:
            embed = await clash_embed(
                context=interaction,
                message=f"A Clan Panel already exists for this channel.",
                success=False
                )
            return await interaction.edit_original_response(embed=embed,view=None)
        
        await guild.create_clan_panel(channel)
        embed = await clash_embed(
            context=interaction,
            message=f"Clan Panel created.",
            success=True
            )
        await interaction.edit_original_response(embed=embed,view=None)
    
    ##################################################
    ### SERVERSETUP / PANEL / DELETE
    ##################################################    
    @subcommand_group_panel.command(name="delete")
    @commands.guild_only()
    @commands.is_owner()
    async def subcommand_group_guildpanel_delete(self,ctx,channel_id:int):
        """
        Deletes a Clan Panel.
        """
        guild = aGuild(ctx.guild.id)
        channel = ctx.guild.get_channel(channel_id)

        if not isinstance(channel,discord.TextChannel):
            embed = await clash_embed(
                context=ctx,
                message=f"Please specify a valid channel.",
                success=False
                )
            return await ctx.reply(embed=embed)
        
        panel = GuildClanPanel.get_panel(guild_id=ctx.guild.id,channel_id=channel_id)
        if not panel:
            embed = await clash_embed(
                context=ctx,
                message=f"A Guild Panel does not exist for this channel.",
                success=False
                )
            return await ctx.reply(embed=embed)
                
        await guild.delete_clan_panel(channel)
        embed = await clash_embed(
            context=ctx,
            message=f"Clan Panel deleted.",
            success=True
            )
        await ctx.reply(embed=embed)

    @app_subcommand_group_panel.command(name="delete",
        description="Delete a Clan Panel.")
    @app_commands.check(is_admin)
    @app_commands.guild_only()
    @app_commands.autocomplete(panel=autocomplete_guild_clan_panels)
    @app_commands.describe(
        panel="The Clan Panel to delete.")
    async def sub_appcommand_guildpanel_delete(self,interaction:discord.Interaction,panel:str):

        await interaction.response.defer()
        
        guild = aGuild(interaction.guild.id)
        channel = interaction.guild.get_channel(int(panel))

        await guild.delete_clan_panel(channel)
        embed = await clash_embed(
            context=interaction,
            message=f"Clan Panel deleted.",
            success=True
            )
        await interaction.edit_original_response(embed=embed,view=None)

    ##################################################
    ### SERVER SETUP / APPLICATION
    ##################################################
    @command_group_guildset.group(name="applicationpanel")
    @commands.guild_only()
    async def subcommand_group_application(self,ctx):
        """
        Setup Clan Application Panels.
        """
        if not ctx.invoked_subcommand:
            pass

    app_subcommand_group_application = app_commands.Group(
        name="application-panel",
        description="Setup Clan Applications.",
        parent=app_command_group_guildset,
        guild_only=True
        )
    
    ##################################################
    ### SERVERSETUP / APPLICATION / LIST
    ##################################################
    @subcommand_group_application.command(name="list")
    @commands.guild_only()
    @commands.admin()
    async def subcommand_group_application_list(self,ctx):
        """
        List all Application Panels & Options in this Server.
        """
        
        embed = await clash_embed(
            context=ctx,
            title="**Application Panels**"
            )
        application_panels = [GuildApplicationPanel(db) for db in db_GuildApplyPanel.objects(server_id=ctx.guild.id)]
        for panel in application_panels:
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
    
    @app_subcommand_group_application.command(name="list",
        description="List all Application Panels & Options in this Server.")
    @app_commands.check(is_admin)
    @app_commands.guild_only()
    async def sub_appcommand_application_list(self,interaction:discord.Interaction):
        
        await interaction.response.defer()
        
        embed = await clash_embed(
            context=interaction,
            title="**Application Panels**"
            )
        application_panels = [GuildApplicationPanel(db) for db in db_GuildApplyPanel.objects(server_id=interaction.guild.id)]
        for panel in application_panels:
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
    ### SERVERSETUP / APPLICATION / CREATE
    ##################################################    
    @subcommand_group_application.command(name="create")
    @commands.guild_only()
    @commands.admin()
    async def subcommand_group_application_create(self,ctx,channel_id:int,listener_channel_id:int,can_user_select_clans:bool=True):
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
    
    @app_subcommand_group_application.command(name="create",
        description="Create an Application Panel.")
    @app_commands.check(is_admin)
    @app_commands.guild_only()
    @app_commands.describe(
        channel="The Channel to create the Panel in.",
        listener="The Channel to send Ticket Tool commands in.",
        can_user_select_clans="Can Applicants choose Clans to apply to?")
    async def sub_appcommand_application_create(self,interaction:discord.Interaction,channel:discord.TextChannel,listener:discord.TextChannel,can_user_select_clans:bool=True):
        
        await interaction.response.defer()

        view = CreateApplicationMenu(interaction,channel,listener,can_user_select_clans)    
        await view.start()
    
    ##################################################
    ### SERVERSETUP / APPLICATION / DELETE
    ##################################################    
    @subcommand_group_application.command(name="delete")
    @commands.guild_only()
    @commands.admin()
    async def subcommand_group_application_delete(self,ctx,channel_id:int):
        """
        Delete an Application Panel.
        """
        guild = aGuild(ctx.guild.id)
        channel = ctx.guild.get_channel(channel_id)

        if not isinstance(channel,discord.TextChannel):
            embed = await clash_embed(
                context=ctx,
                message=f"Please specify a valid channel.",
                success=False
                )
            return await ctx.reply(embed=embed)
        
        panel = GuildApplicationPanel.get_panel(guild_id=ctx.guild.id,channel_id=channel_id)        
        if not panel:
            embed = await clash_embed(
                context=ctx,
                message=f"An Application Panel does not exist for this channel.",
                success=False
                )
            return await ctx.reply(embed=embed)
        
        await guild.delete_apply_panel(channel)
        embed = await clash_embed(
            context=ctx,
            message=f"Application Panel deleted.",
            success=True
            )
        await ctx.reply(embed=embed)

    @app_subcommand_group_application.command(name="delete",
        description="Delete an Application Panel.")
    @app_commands.check(is_admin)
    @app_commands.guild_only()
    @app_commands.autocomplete(panel=autocomplete_guild_apply_panels)
    @app_commands.describe(
        panel="The Application Panel to delete.")
    async def sub_appcommand_application_delete(self,interaction:discord.Interaction,panel:str):
        
        await interaction.response.defer()

        guild = aGuild(interaction.guild.id)
        channel = interaction.guild.get_channel(int(panel))

        await guild.delete_apply_panel(channel)
        embed = await clash_embed(
            context=interaction,
            message=f"Application Panel deleted.",
            success=True
            )
        await interaction.edit_original_response(embed=embed,view=None)
    
    ##################################################
    ### SERVER SETUP / CLOCKS
    ##################################################
    @command_group_guildset.group(name="clocks")
    @commands.guild_only()
    async def subcommand_group_clocks(self,ctx):
        """
        Setup Server Event Clocks.
        """
        if not ctx.invoked_subcommand:
            pass

    app_subcommand_group_clocks = app_commands.Group(
        name="clocks",
        description="Setup Server Event Clocks.",
        parent=app_command_group_guildset,
        guild_only=True
        )
    
    ##################################################
    ### SERVER SETUP / CLOCKS / EVENTS
    ##################################################
    @subcommand_group_clocks.command(name="toggleevents")
    @commands.guild_only()
    @commands.admin()
    async def subcommand_clashset_clocks_events(self,ctx):
        """Enable/Disable the use of Discord Scheduled Events."""

        guild = aGuild(ctx.guild.id)
        if not guild.clock_config.use_events:
            guild.clock_config.use_events = True
            await ctx.reply(f"Discord Scheduled Events have been __enabled__ for **{guild.name}**.")        
        else:
            guild.clock_config.use_events = False
            await ctx.reply(f"Discord Scheduled Events have been __disabled__ for **{guild.name}**.")
    
    @app_subcommand_group_clocks.command(name="toggle-events",
        description="Enable/Disable the use of Discord Scheduled Events.")
    @app_commands.check(is_admin)
    @app_commands.guild_only()
    async def sub_appcommand_clock_events(self,interaction:discord.Interaction):
        
        await interaction.response.defer()

        guild = aGuild(interaction.guild.id)        
        if not guild.clock_config.use_events:
            guild.clock_config.use_events = True
            await interaction.edit_original_response(content=f"Discord Scheduled Events have been __enabled__ for **{guild.name}**.",view=None)
        else:
            guild.clock_config.use_events = False
            await interaction.edit_original_response(content=f"Discord Scheduled Events have been __disabled__ for **{guild.name}**.",view=None)
    
    ##################################################
    ### SERVER SETUP / CLOCKS / CHANNELS
    ##################################################    
    @subcommand_group_clocks.command(name="togglechannels")
    @commands.guild_only()
    @commands.admin()
    async def subcommand_clashset_clocks_channels(self,ctx):
        """Enable/Disable the use of Channel Clocks."""

        guild = aGuild(ctx.guild.id)
        if not guild.clock_config.use_channels:
            guild.clock_config.use_channels = True
            await ctx.reply(f"Channel Clocks have been __enabled__ for **{guild.name}**.")        
        else:
            guild.clock_config.use_channels = False
            await ctx.reply(f"Channel Clocks have been __disabled__ for **{guild.name}**.")
    
    @app_subcommand_group_clocks.command(name="toggle-channels",
        description="Enable/Disable the use of Channel Clocks.")
    @app_commands.check(is_admin)
    @app_commands.guild_only()
    async def sub_appcommand_clock_channels(self,interaction:discord.Interaction):
        
        await interaction.response.defer()

        guild = aGuild(interaction.guild.id)        
        if not guild.clock_config.use_channels:
            guild.clock_config.use_channels = True
            await interaction.edit_original_response(content=f"Channel Clocks have been __enabled__ for **{guild.name}**.",view=None)
        else:
            guild.clock_config.use_channels = False
            await interaction.edit_original_response(content=f"Channel Clocks have been __disabled__ for **{guild.name}**.",view=None)
    
    ##################################################
    ### RECRUITING REMINDER COMMAND GROUPS
    ##################################################
    @commands.group(name="recruitreminder")
    @commands.guild_only()
    async def command_group_recruit_reminder(self,ctx):
        """
        Set up Recruiting Reminders.

        **This is a command group. To use the sub-commands below, follow the syntax: `$recruitreminder [sub-command]`.**
        """
        if not ctx.invoked_subcommand:
            pass

    app_command_group_recruit_reminder = app_commands.Group(
        name="recruiting-reminder",
        description="Group to set up Recruiting Reminders. Equivalent to [p]recruitreminder.",
        guild_only=True
        )
    
    ##################################################
    ### RECRUITING REMINDER / LIST
    ##################################################    
    @command_group_recruit_reminder.command(name="list")
    @commands.guild_only()
    @commands.check(has_manage_server)
    async def subcommand_group_recruiting_reminders_list(self,ctx):
        """
        List all Recruiting Reminders in this Server.
        """
        
        all_reminders = RecruitingReminder.get_by_guild(ctx.guild.id)

        embed = await clash_embed(
            context=ctx,
            title=f"**Recruiting Reminders: {ctx.guild.name}**"
            )
        async for reminder in AsyncIter(all_reminders):
            embed.add_field(
                name=f"**{reminder.ad_name}**",
                value=f"Link: {reminder.ad_link}"
                    + f"\nUser: {getattr(reminder.remind_user,'mention','Unknown User')}"
                    + f"\nInterval: {reminder.interval} hour(s)"
                    + f"\nChannel: {getattr(reminder.channel,'mention','Unknown Channel')}"
                    + f"\n\u200b",
                inline=False
                )
        await ctx.reply(embed=embed)
    
    @app_command_group_recruit_reminder.command(name="list",
        description="List all Recruiting Reminders in this Server.")
    @app_commands.check(has_manage_server)
    @app_commands.guild_only()
    async def appcommand_recruiting_reminders_list(self,interaction:discord.Interaction):

        await interaction.response.defer()
        
        all_reminders = RecruitingReminder.get_by_guild(interaction.guild.id)

        embed = await clash_embed(
            context=interaction,
            title=f"**Recruiting Reminders: {interaction.guild.name}**"
            )
        async for reminder in AsyncIter(all_reminders):
            embed.add_field(
                name=f"**{reminder.ad_name}**",
                value=f"ID: {reminder.id}"
                    + f"\nLink: {reminder.ad_link}"
                    + f"\nUser: {getattr(reminder.remind_user,'mention','Unknown User')}"
                    + f"\nInterval: {reminder.interval} hour(s)"
                    + f"\nChannel: {getattr(reminder.channel,'mention','Unknown Channel')}"
                    + f"\n\u200b",
                inline=False
                )
        await interaction.edit_original_response(embed=embed,view=None)
    
    ##################################################
    ### RECRUITING REMINDER / ADD
    ##################################################
    @command_group_recruit_reminder.command(name="create")
    @commands.guild_only()
    @commands.check(has_manage_server)
    async def subcommand_group_recruiting_reminders_create(self,ctx,channel:discord.TextChannel,user_to_remind:discord.Member):
        """
        Create a Recruiting Reminder in this Server.
        """
        
        create_reminder = CreateRecruitingReminder(ctx,channel,user_to_remind)
        await create_reminder.start()
    
    @app_command_group_recruit_reminder.command(name="create",
        description="Create a Recruiting Reminder in this Server.")
    @app_commands.check(has_manage_server)
    @app_commands.guild_only()
    async def appcommand_recruiting_reminders_create(self,interaction:discord.Interaction,channel:discord.TextChannel,user_to_remind:discord.Member):

        await interaction.response.defer()

        create_reminder = CreateRecruitingReminder(interaction,channel,user_to_remind)
        await create_reminder.start()
    
    ##################################################
    ### RECRUITING REMINDER / DELETE
    ##################################################
    @command_group_recruit_reminder.command(name="delete")
    @commands.guild_only()
    @commands.check(has_manage_server)
    async def subcommand_group_recruiting_reminders_delete(self,ctx,reminder_id:str):
        """
        Delete a Recruiting Reminder by ID.
        
        To get the ID of a Leaderboard, use the command [p]`recruitreminder list`.
        """
        
        try:
            reminder = RecruitingReminder(reminder_id)
        except:
            embed = await clash_embed(
                context=ctx,
                message=f"Reminder with ID `{reminder_id}` not found.",
                success=False
                )
            return await ctx.reply(embed=embed)
        
        await reminder.delete()
        embed = await clash_embed(
            context=ctx,
            message=f"Recruiting Reminder deleted.",
            success=True
            )
    
    @app_command_group_recruit_reminder.command(name="delete",
        description="Deletes a Recruiting Reminder.")
    @app_commands.check(has_manage_server)
    @app_commands.guild_only()
    @app_commands.autocomplete(reminder=autocomplete_guild_recruiting_reminders)
    @app_commands.describe(
        reminder="The Reminder to delete.")
    async def appcommand_recruiting_reminders_delete(self,interaction:discord.Interaction,reminder:str):

        await interaction.response.defer()

        try:
            reminder = RecruitingReminder(reminder)
        except:
            embed = await clash_embed(
                context=interaction,
                message=f"Reminder with ID `{reminder}` not found.",
                success=False
                )
            return await interaction.edit_original_response(embed=embed,view=None)
        
        await reminder.delete()
        embed = await clash_embed(
            context=reminder,
            message=f"Recruiting Reminder deleted.",
            success=True
            )
        await interaction.edit_original_response(embed=embed,view=None)