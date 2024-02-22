import coc
import discord
import pendulum
import random

from redbot.core import commands, app_commands
from redbot.core.bot import Red
from redbot.core.utils import AsyncIter

from coc_main.api_client import BotClashClient, ClashOfClansError
from coc_main.cog_coc_client import ClashOfClansClient

from coc_main.discord.guild import aGuild, ClanGuildLink, aGuildClocks
from coc_main.utils.components import clash_embed
from coc_main.utils.checks import is_admin, has_manage_server, has_manage_threads

from .views.create_recruiting_reminder import CreateRecruitingReminder, RecruitingReminder

bot_client = BotClashClient()

async def autocomplete_guild_recruiting_reminders(interaction:discord.Interaction,current:str):
    try:
        panels = await RecruitingReminder.get_for_guild(interaction.guild.id)

        if current:
            sel_panels = [p for p in panels if current.lower() in str(p).lower()]
        else:
            sel_panels = panels

        return [
            app_commands.Choice(
                name=str(panel),
                value=str(panel.id))
            for panel in random.sample(sel_panels,min(5,len(sel_panels)))
            ]
    except:
        bot_client.coc_main_log.exception(f"Error in autocomplete_guild_recruiting_reminders")

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

    def __init__(self,bot:Red,version:int):
        self.bot = bot

    def format_help_for_context(self, ctx: commands.Context) -> str:
        context = super().format_help_for_context(ctx)
        return f"{context}\n\nAuthor: {self.__author__}\nVersion: {self.__version__}.{self.sub_v}"

    @property
    def bot_client(self) -> BotClashClient:
        return BotClashClient()

    @property
    def client(self) -> ClashOfClansClient:
        return bot_client.bot.get_cog("ClashOfClansClient")
    
    async def cog_command_error(self,ctx,error):
        original = getattr(error,'original',None)
        if isinstance(original,coc.NotFound):
            embed = await clash_embed(
                context=ctx,
                message="The Tag you provided doesn't seem to exist.",
                success=False,
                timestamp=pendulum.now()
                )
            await ctx.send(embed=embed)
            return
        elif isinstance(original,coc.GatewayError) or isinstance(original,coc.Maintenance):
            embed = await clash_embed(
                context=ctx,
                message="The Clash of Clans API is currently unavailable.",
                success=False,
                timestamp=pendulum.now()
                )
            await ctx.send(embed=embed)
            return
        elif isinstance(original,ClashOfClansError):
            embed = await clash_embed(
                context=ctx,
                message=f"{original.message}",
                success=False,
                timestamp=pendulum.now()
                )
            await ctx.send(embed=embed)
            return
        await self.bot.on_command_error(ctx,error,unhandled_by_cog=True)

    async def cog_app_command_error(self,interaction,error):
        original = getattr(error,'original',None)
        embed = None
        if isinstance(original,coc.NotFound):
            embed = await clash_embed(
                context=interaction,
                message="The Tag you provided doesn't seem to exist.",
                success=False,
                timestamp=pendulum.now()
                )            
        elif isinstance(original,coc.GatewayError) or isinstance(original,coc.Maintenance):
            embed = await clash_embed(
                context=interaction,
                message="The Clash of Clans API is currently unavailable.",
                success=False,
                timestamp=pendulum.now()
                )            
        elif isinstance(original,ClashOfClansError):
            embed = await clash_embed(
                context=interaction,
                message=f"{original.message}",
                success=False,
                timestamp=pendulum.now()
                )
        if embed:
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
    ##### - serversetup / create-thread
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
    @commands.group(name="serversetup",aliases=["serverset"])
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

        clan_links = await ClanGuildLink.get_for_guild(ctx.guild.id)
        
        embed = await clash_embed(
            context=ctx,
            title=f"**Linked Clans: {ctx.guild.name}**"
            )
        async for link in AsyncIter(clan_links):
            clan = await bot_client.coc.get_clan(link.tag)
            embed.add_field(
                name=f"**{clan.title}**",
                value=f"Co-Leader Role: {getattr(link.coleader_role,'mention','None')}"
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
        clan_links = await ClanGuildLink.get_for_guild(interaction.guild.id)
        
        embed = await clash_embed(
            context=interaction,
            title=f"**Linked Clans: {interaction.guild.name}**"
            )
        async for link in AsyncIter(clan_links):
            clan = await bot_client.coc.get_clan(link.tag)
            embed.add_field(
                name=f"**{clan.title}**",
                value=f"Co-Leader Role: {getattr(link.coleader_role,'mention','None')}"
                    + f"\nElder Role: {getattr(link.elder_role,'mention','None')}"
                    + f"\nMember Role: {getattr(link.member_role,'mention','None')}",
                inline=False
                )
        await interaction.edit_original_response(embed=embed,view=None)
    
    ##################################################
    ### SERVERSETUP / CREATE-THREAD
    ##################################################    
    @command_group_guildset.command(name="create-thread")
    @commands.check(has_manage_threads)
    @commands.guild_only()
    @commands.guildowner_or_can_manage_channel()
    async def subcommand_group_create_forum_thread(self,ctx,channel:discord.ForumChannel,title:str,message:str):
        """
        Creates a new Forum Thread in the specified Forum Channel.
        """
        thread, msg = await channel.create_thread(
            name=title,
            content=message
            )
        await ctx.reply(f"Thread created: {thread.jump_url}")
    
    @app_command_group_guildset.command(name="create-thread",
        description="Creates a new Forum Thread in the specified Forum Channel.")
    @app_commands.check(has_manage_threads)
    @app_commands.guild_only()
    async def sub_appcommand_create_forum_thread(self,interaction:discord.Interaction,channel:discord.ForumChannel,title:str,message:str):
        
        await interaction.response.defer()
        thread, msg = await channel.create_thread(
            name=title,
            content=message
            )
        await interaction.followup.send(f"Thread created: {thread.jump_url}")
    
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

        clock_config = await aGuildClocks.get_for_guild(ctx.guild.id)
        await clock_config.toggle_events()
        await ctx.reply(
            f"Discord Scheduled Events have been "
            + (f"__enabled__" if clock_config.use_events else f"__disabled__")
            + f" for **{clock_config.guild.name}**."
            )
    
    @app_subcommand_group_clocks.command(name="toggle-events",
        description="Enable/Disable the use of Discord Scheduled Events.")
    @app_commands.check(is_admin)
    @app_commands.guild_only()
    async def sub_appcommand_clock_events(self,interaction:discord.Interaction):
        
        await interaction.response.defer()

        clock_config = await aGuildClocks.get_for_guild(interaction.guild.id)
        await clock_config.toggle_events()
        await interaction.followup.send(
            f"Discord Scheduled Events have been "
            + (f"__enabled__" if clock_config.use_events else f"__disabled__")
            + f" for **{clock_config.guild.name}**."
            )
    
    ##################################################
    ### SERVER SETUP / CLOCKS / CHANNELS
    ##################################################    
    @subcommand_group_clocks.command(name="togglechannels")
    @commands.guild_only()
    @commands.admin()
    async def subcommand_clashset_clocks_channels(self,ctx):
        """Enable/Disable the use of Channel Clocks."""

        clock_config = await aGuildClocks.get_for_guild(ctx.guild.id)
        await clock_config.toggle_channels()
        await ctx.reply(
            f"Channel Clocks have been "
            + (f"__enabled__" if clock_config.use_channels else f"__disabled__")
            + f" for **{clock_config.guild.name}**."
            )
    
    @app_subcommand_group_clocks.command(name="toggle-channels",
        description="Enable/Disable the use of Channel Clocks.")
    @app_commands.check(is_admin)
    @app_commands.guild_only()
    async def sub_appcommand_clock_channels(self,interaction:discord.Interaction):
        
        await interaction.response.defer()

        clock_config = await aGuildClocks.get_for_guild(interaction.guild.id)
        await clock_config.toggle_channels()
        await interaction.followup.send(
            f"Channel Clocks have been "
            + (f"__enabled__" if clock_config.use_channels else f"__disabled__")
            + f" for **{clock_config.guild.name}**."
            )
    
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
        
        all_reminders = await RecruitingReminder.get_for_guild(ctx.guild.id)

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
        
        all_reminders = await RecruitingReminder.get_for_guild(interaction.guild.id)

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
        
        reminder = await RecruitingReminder.get_by_id(reminder_id)
        if not reminder:
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

        get_reminder = await RecruitingReminder.get_by_id(reminder)
        if not get_reminder:
            embed = await clash_embed(
                context=interaction,
                message=f"Reminder with ID `{reminder}` not found.",
                success=False
                )
            return await interaction.edit_original_response(embed=embed,view=None)
        
        await get_reminder.delete()
        embed = await clash_embed(
            context=interaction,
            message=f"Recruiting Reminder deleted.",
            success=True
            )
        await interaction.edit_original_response(embed=embed,view=None)