import discord

from redbot.core import commands, app_commands
from redbot.core.bot import Red

from coc_main.client.global_client import GlobalClient
from coc_main.cog_coc_main import ClashOfClansMain as coc_main

from coc_main.discord.guild import aGuildClocks
from coc_main.utils.checks import is_admin, has_manage_threads

# async def autocomplete_guild_recruiting_reminders(interaction:discord.Interaction,current:str):
#     try:
#         panels = await RecruitingReminder.get_for_guild(interaction.guild.id)

#         if current:
#             sel_panels = [p for p in panels if current.lower() in str(p).lower()]
#         else:
#             sel_panels = panels

#         return [
#             app_commands.Choice(
#                 name=str(panel),
#                 value=str(panel.id))
#             for panel in random.sample(sel_panels,min(5,len(sel_panels)))
#             ]
#     except:
#         bot_client.coc_main_log.exception(f"Error in autocomplete_guild_recruiting_reminders")

############################################################
############################################################
#####
##### SERVER CONFIG COG
#####
############################################################
############################################################
class ClashServerConfig(commands.Cog):
    """
    Clash of Clans Server Config.
    """

    __author__ = coc_main.__author__
    __version__ = coc_main.__version__

    def __init__(self):
        pass

    def format_help_for_context(self, ctx: commands.Context) -> str:
        context = super().format_help_for_context(ctx)
        return f"{context}\n\nAuthor: {self.__author__}\nVersion: {self.__version__}"
    
    @property
    def bot(self) -> Red:
        return GlobalClient.bot
    
    async def cog_command_error(self,ctx:commands.Context,error:discord.DiscordException):
        original_exc = getattr(error,'original',error)
        await GlobalClient.handle_command_error(original_exc,ctx)

    async def cog_app_command_error(self,interaction:discord.Interaction,error:discord.DiscordException):
        original_exc = getattr(error,'original',error)
        await GlobalClient.handle_command_error(original_exc,interaction)

    ############################################################
    #####
    ##### COMMAND GROUP: COC CLOCKS
    #####
    ############################################################
    @commands.group(name="clock",aliases=["clocks"])
    @commands.guild_only()
    async def cmdgrp_clocks(self,ctx:commands.Context):
        """
        Set up Clash of Clans Event Clocks.

        **This is a command group. To use the sub-commands below, follow the syntax: `$clocks [sub-command]`.**
        """
        if not ctx.invoked_subcommand:
            pass

    appgrp_clocks = app_commands.Group(
        name="clocks",
        description="Set up Clash of Clans Event Clocks.",
        guild_only=True
        )
    
    ############################################################
    #####
    ##### COMMAND: CLOCK EVENTS
    #####
    ############################################################
    @cmdgrp_clocks.command(name="events")
    @commands.guild_only()
    @commands.admin()
    async def subcmd_clock_events(self,ctx:commands.Context,toggle:bool):
        """
        Enable/Disable the use of Discord Scheduled Events.
        
        True = Enabled
        False = Disabled
        """

        clock_config = await aGuildClocks.get_for_guild(ctx.guild.id)
        await clock_config.toggle_events(toggle)
        await ctx.reply(
            f"Discord Scheduled Events have been "
            + (f"__enabled__" if clock_config.use_events else f"__disabled__")
            + f" for **{clock_config.guild.name}**."
            )
    
    @appgrp_clocks.command(name="events",
        description="Enable/Disable the use of Discord Scheduled Events.")
    @app_commands.describe(
        toggle="Enable Discord Events?"
        )
    @app_commands.check(is_admin)
    @app_commands.guild_only()
    async def appcmd_clock_events(self,interaction:discord.Interaction,toggle:bool):
        
        await interaction.response.defer()

        clock_config = await aGuildClocks.get_for_guild(interaction.guild.id)
        await clock_config.toggle_events(toggle)
        await interaction.followup.send(
            f"Discord Scheduled Events have been "
            + (f"__enabled__" if clock_config.use_events else f"__disabled__")
            + f" for **{clock_config.guild.name}**."
            )
    
    ############################################################
    #####
    ##### COMMAND: CLOCK CHANNELS
    #####
    ############################################################
    @cmdgrp_clocks.command(name="channels")
    @commands.guild_only()
    @commands.admin()
    async def subcmd_clock_channels(self,ctx:commands.Context,toggle:bool):
        """
        Enable/Disable the use of Channel Clocks.
        
        True = Enabled
        False = Disabled
        """

        clock_config = await aGuildClocks.get_for_guild(ctx.guild.id)
        await clock_config.toggle_channels(toggle)
        await ctx.reply(
            f"Channel Clocks have been "
            + (f"__enabled__" if clock_config.use_channels else f"__disabled__")
            + f" for **{clock_config.guild.name}**."
            )
    
    @appgrp_clocks.command(name="channels",
        description="Enable/Disable the use of Channel Clocks.")
    @app_commands.describe(
        toggle="Enable Discord Chanenl Clocks?"
        )
    @app_commands.check(is_admin)
    @app_commands.guild_only()
    async def appcmd_clock_channels(self,interaction:discord.Interaction,toggle:bool):
        
        await interaction.response.defer()

        clock_config = await aGuildClocks.get_for_guild(interaction.guild.id)
        await clock_config.toggle_channels(toggle)
        await interaction.followup.send(
            f"Channel Clocks have been "
            + (f"__enabled__" if clock_config.use_channels else f"__disabled__")
            + f" for **{clock_config.guild.name}**."
            )    
    
    ############################################################
    #####
    ##### COMMAND GROUP: FORUMS
    #####
    ############################################################
    @commands.group(name="forums")
    @commands.guild_only()
    async def cmdgrp_forums(self,ctx:commands.Context):
        """
        Utility commands to manage Forum Channels.

        **This is a command group. To use the sub-commands below, follow the syntax: `$forums [sub-command]`.**
        """
        if not ctx.invoked_subcommand:
            pass

    appgrp_forums = app_commands.Group(
        name="forums",
        description="Utility commands to manage Forum Channels. Equivalent to [p]forums.",
        guild_only=True
        )
    
    @cmdgrp_forums.command(name="create-thread")
    @commands.check(has_manage_threads)
    @commands.guild_only()
    @commands.guildowner_or_can_manage_channel()
    async def subcmd_forums_createthread(self,ctx:commands.Context,channel:discord.ForumChannel,title:str,message:str):
        """
        Creates a new Forum Thread in the specified Forum Channel.
        """
        thread, msg = await channel.create_thread(
            name=title,
            content=message
            )
        await ctx.reply(f"Thread created: {thread.jump_url}")
    
    @appgrp_forums.command(name="create-thread",
        description="Creates a new Forum Thread in the specified Forum Channel.")
    @app_commands.check(has_manage_threads)
    @app_commands.guild_only()
    async def appgrp_forums_createthread(self,interaction:discord.Interaction,channel:discord.ForumChannel,title:str,message:str):
        
        await interaction.response.defer()
        thread, msg = await channel.create_thread(
            name=title,
            content=message
            )
        await interaction.followup.send(f"Thread created: {thread.jump_url}")
    
    
    # ##################################################
    # ### RECRUITING REMINDER COMMAND GROUPS
    # ##################################################
    # @commands.group(name="recruitreminder")
    # @commands.guild_only()
    # async def command_group_recruit_reminder(self,ctx):
    #     """
    #     Set up Recruiting Reminders.

    #     **This is a command group. To use the sub-commands below, follow the syntax: `$recruitreminder [sub-command]`.**
    #     """
    #     if not ctx.invoked_subcommand:
    #         pass

    # app_command_group_recruit_reminder = app_commands.Group(
    #     name="recruiting-reminder",
    #     description="Group to set up Recruiting Reminders. Equivalent to [p]recruitreminder.",
    #     guild_only=True
    #     )
    
    # ##################################################
    # ### RECRUITING REMINDER / LIST
    # ##################################################    
    # @command_group_recruit_reminder.command(name="list")
    # @commands.guild_only()
    # @commands.check(has_manage_server)
    # async def subcommand_group_recruiting_reminders_list(self,ctx):
    #     """
    #     List all Recruiting Reminders in this Server.
    #     """
        
    #     all_reminders = await RecruitingReminder.get_for_guild(ctx.guild.id)

    #     embed = await clash_embed(
    #         context=ctx,
    #         title=f"**Recruiting Reminders: {ctx.guild.name}**"
    #         )
    #     async for reminder in AsyncIter(all_reminders):
    #         embed.add_field(
    #             name=f"**{reminder.ad_name}**",
    #             value=f"Link: {reminder.ad_link}"
    #                 + f"\nUser: {getattr(reminder.remind_user,'mention','Unknown User')}"
    #                 + f"\nInterval: {reminder.interval} hour(s)"
    #                 + f"\nChannel: {getattr(reminder.channel,'mention','Unknown Channel')}"
    #                 + f"\n\u200b",
    #             inline=False
    #             )
    #     await ctx.reply(embed=embed)
    
    # @app_command_group_recruit_reminder.command(name="list",
    #     description="List all Recruiting Reminders in this Server.")
    # @app_commands.check(has_manage_server)
    # @app_commands.guild_only()
    # async def appcommand_recruiting_reminders_list(self,interaction:discord.Interaction):

    #     await interaction.response.defer()
        
    #     all_reminders = await RecruitingReminder.get_for_guild(interaction.guild.id)

    #     embed = await clash_embed(
    #         context=interaction,
    #         title=f"**Recruiting Reminders: {interaction.guild.name}**"
    #         )
    #     async for reminder in AsyncIter(all_reminders):
    #         embed.add_field(
    #             name=f"**{reminder.ad_name}**",
    #             value=f"ID: {reminder.id}"
    #                 + f"\nLink: {reminder.ad_link}"
    #                 + f"\nUser: {getattr(reminder.remind_user,'mention','Unknown User')}"
    #                 + f"\nInterval: {reminder.interval} hour(s)"
    #                 + f"\nChannel: {getattr(reminder.channel,'mention','Unknown Channel')}"
    #                 + f"\n\u200b",
    #             inline=False
    #             )
    #     await interaction.edit_original_response(embed=embed,view=None)
    
    # ##################################################
    # ### RECRUITING REMINDER / ADD
    # ##################################################
    # @command_group_recruit_reminder.command(name="create")
    # @commands.guild_only()
    # @commands.check(has_manage_server)
    # async def subcommand_group_recruiting_reminders_create(self,ctx,channel:discord.TextChannel,user_to_remind:discord.Member):
    #     """
    #     Create a Recruiting Reminder in this Server.
    #     """
        
    #     create_reminder = CreateRecruitingReminder(ctx,channel,user_to_remind)
    #     await create_reminder.start()
    
    # @app_command_group_recruit_reminder.command(name="create",
    #     description="Create a Recruiting Reminder in this Server.")
    # @app_commands.check(has_manage_server)
    # @app_commands.guild_only()
    # async def appcommand_recruiting_reminders_create(self,interaction:discord.Interaction,channel:discord.TextChannel,user_to_remind:discord.Member):

    #     await interaction.response.defer()

    #     create_reminder = CreateRecruitingReminder(interaction,channel,user_to_remind)
    #     await create_reminder.start()
    
    # ##################################################
    # ### RECRUITING REMINDER / DELETE
    # ##################################################
    # @command_group_recruit_reminder.command(name="delete")
    # @commands.guild_only()
    # @commands.check(has_manage_server)
    # async def subcommand_group_recruiting_reminders_delete(self,ctx,reminder_id:str):
    #     """
    #     Delete a Recruiting Reminder by ID.
        
    #     To get the ID of a Leaderboard, use the command [p]`recruitreminder list`.
    #     """
        
    #     reminder = await RecruitingReminder.get_by_id(reminder_id)
    #     if not reminder:
    #         embed = await clash_embed(
    #             context=ctx,
    #             message=f"Reminder with ID `{reminder_id}` not found.",
    #             success=False
    #             )
    #         return await ctx.reply(embed=embed)
        
    #     await reminder.delete()
    #     embed = await clash_embed(
    #         context=ctx,
    #         message=f"Recruiting Reminder deleted.",
    #         success=True
    #         )
    
    # @app_command_group_recruit_reminder.command(name="delete",
    #     description="Deletes a Recruiting Reminder.")
    # @app_commands.check(has_manage_server)
    # @app_commands.guild_only()
    # @app_commands.autocomplete(reminder=autocomplete_guild_recruiting_reminders)
    # @app_commands.describe(
    #     reminder="The Reminder to delete.")
    # async def appcommand_recruiting_reminders_delete(self,interaction:discord.Interaction,reminder:str):

    #     await interaction.response.defer()

    #     get_reminder = await RecruitingReminder.get_by_id(reminder)
    #     if not get_reminder:
    #         embed = await clash_embed(
    #             context=interaction,
    #             message=f"Reminder with ID `{reminder}` not found.",
    #             success=False
    #             )
    #         return await interaction.edit_original_response(embed=embed,view=None)
        
    #     await get_reminder.delete()
    #     embed = await clash_embed(
    #         context=interaction,
    #         message=f"Recruiting Reminder deleted.",
    #         success=True
    #         )
    #     await interaction.edit_original_response(embed=embed,view=None)