import asyncio
import discord
import pendulum

from typing import *

from redbot.core import Config, commands, app_commands, bank
from redbot.core.utils import AsyncIter
from redbot.core.bot import Red

from coc_main.api_client import BotClashClient as client
from coc_main.utils.components import clash_embed, MenuConfirmation

from .checks import is_events_admin
from .autocomplete import autocomplete_active_events, autocomplete_user_players
from .components.event import Event
from .components.export import generate_event_export

from .exceptions import EventClosed, AlreadyRegistered, NotEligible

bot_client = client()

class Events(commands.Cog):
    """Events Management module for Guild Events."""

    __author__ = bot_client.author
    __version__ = bot_client.version

    def __init__(self,bot:Red):
        self.bot: Red = bot

        self.ticket_prefix = "--"
        self._ticket_listener = 0        
        self._events_guild = 0
        self._events_role = 0
        self._admin_role = 0

        default_global = {
            "ticket_prefix": "--",
            "ticket_listener": 0,            
            "master_guild": 0,
            "master_role": 0,
            "admin_role": 0
            }
        self.config = Config.get_conf(self,identifier=644530507505336330,force_registration=True)        
        self.config.register_global(**default_global)
    
    def format_help_for_context(self, ctx: commands.Context) -> str:
        context = super().format_help_for_context(ctx)
        return f"{context}\n\nAuthor: {self.__author__}\nVersion: {self.__version__}"
    
    async def cog_load(self):
        self.ticket_prefix = await self.config.ticket_prefix()
        self._ticket_listener = await self.config.ticket_listener()
        self._events_guild = await self.config.master_guild()
        self._events_role = await self.config.master_role()
        self._admin_role = await self.config.admin_role()

    async def cog_unload(self):
        return
            
    @property
    def events_guild(self) -> Optional[discord.Guild]:
        return self.bot.get_guild(self._events_guild)    
    @property
    def events_role(self) -> Optional[discord.Role]:
        return self.events_guild.get_role(self._events_role)
    @property
    def ticket_listener(self) -> Optional[discord.TextChannel]:
        if self.events_guild:
            return self.events_guild.get_channel(self._ticket_listener)
        return None
    @property
    def admin_role(self) -> Optional[discord.Role]:
        if self.events_guild:
            return self.events_guild.get_role(self._admin_role)
        return None
    
    @commands.Cog.listener("on_guild_channel_create")
    async def event_channel_ticket_create_listener(self,channel:discord.TextChannel):
        event_id = None
        await asyncio.sleep(1)
        
        async for message in channel.history(limit=1,oldest_first=True):
            for embed in message.embeds:
                if embed.footer.text == "Event ID":
                    event_id = embed.description
                    break

        if not event_id:
            return
        
        event = await Event.get_event(event_id)
        role = await event.create_discord_role()

        await channel.edit(name=f"{event.name}")
        await event.set_discord_channel(channel)
        await channel.send(f"{self.ticket_prefix}add {role.id}")
    
    @commands.Cog.listener("on_guild_channel_delete")
    async def event_channel_ticket_delete_listener(self,channel:discord.TextChannel):
        event = await Event.get_by_channel(channel.id)
        if event:
            role = await channel.guild.get_role(event.role_id)
            if role:
                await role.delete(reason="Event Channel Deleted.")
    
    ############################################################
    #####
    ##### ASSISTANT FUNCTIONS
    #####
    ############################################################
    @commands.Cog.listener()
    async def on_assistant_cog_add(self,cog:commands.Cog):
        return
        # schema = [
        #     {
        #         "name": "_assistant_clan_application",
        #         "description": "Starts the process for a user to apply to or join a Clan in the Alliance. When completed, returns the ticket channel that the application was created in.",
        #         "parameters": {
        #             "type": "object",
        #             "properties": {},
        #             },
        #         }
        #     ]
        # await cog.register_functions(cog_name="DiscordPanels", schemas=schema)
    
    ############################################################
    #####
    ##### COMMAND GROUP: SET EVENTS
    ##### Only available as text command
    ############################################################
    @commands.group(name="eventset")
    @commands.is_owner()
    @commands.guild_only()
    async def command_group_events_set(self,ctx:commands.Context):
        """
        Command group for setting up the Events Module.
        """
        if not ctx.invoked_subcommand:
            pass
    
    ##################################################
    ### EVENTSET / GUILD
    ##################################################    
    @command_group_events_set.command(name="guild")
    @commands.is_owner()
    @commands.guild_only()
    async def subcommand_events_set_guild(self,ctx:commands.Context,guild_id:int):
        """
        Set the Master Guild for the Events Module.
        """

        guild = self.bot.get_guild(guild_id)
        if not guild:
            return await ctx.reply(f"Guild not found.")
        
        await self.config.master_guild.set(guild_id)
        self._events_guild = guild_id
        await ctx.reply(f"Master Guild set to {guild.name}.")
    
    ##################################################
    ### EVENTSET / ROLE
    ##################################################    
    @command_group_events_set.command(name="role")
    @commands.is_owner()
    @commands.guild_only()
    async def subcommand_events_set_role(self,ctx:commands.Context,role_id:int):
        """
        Set the Master Role for the Events Module.

        All roles created for events will be created under this role.
        """

        if not self.events_guild:
            return await ctx.reply(f"Master Guild not set.")
        
        role = self.events_guild.get_role(role_id)
        if not role:
            return await ctx.reply(f"Role not found.")
        
        await self.config.master_role.set(role_id)
        self._events_role = role_id
        await ctx.reply(f"Master Role set to {role.name}.")
    
    ##################################################
    ### EVENTSET / ROLE
    ##################################################    
    @command_group_events_set.command(name="admin")
    @commands.is_owner()
    @commands.guild_only()
    async def subcommand_events_set_admin(self,ctx:commands.Context,role_id:int):
        """
        Set the Admin Role for the Events Module.
        """

        if not self.events_guild:
            return await ctx.reply(f"Master Guild not set.")

        role = self.events_guild.get_role(role_id)
        if not role:
            return await ctx.reply(f"Role not found.")
        
        await self.config.admin_role.set(role_id)
        self._admin_role = role_id
        await ctx.reply(f"Admin Role set to {role.name}.")
    
    ##################################################
    ### EVENTSET / LISTENER
    ##################################################    
    @command_group_events_set.command(name="listener")
    @commands.is_owner()
    @commands.guild_only()
    async def subcommand_events_set_listener(self,ctx:commands.Context,channel_id:int):
        """
        Set the Admin Role for the Events Module.
        """

        if not self.events_guild:
            return await ctx.reply(f"Master Guild not set.")

        channel = self.events_guild.get_channel(channel_id)
        if not channel:
            return await ctx.reply(f"Channel not found.")
        
        await self.config.ticket_listener.set(channel_id)
        self._ticket_listener = channel_id
        await ctx.reply(f"Ticket Listener set to {channel.name}.")
    
    ############################################################
    #####
    ##### COMMAND GROUP: EVENT ADMIN
    ##### 
    ############################################################
    @commands.group(name="eventadmin")
    @commands.check(is_events_admin)
    @commands.guild_only()
    async def command_group_event_admin(self,ctx:commands.Context):
        """
        Command group for setting up/managing Events.
        """
        if not ctx.invoked_subcommand:
            pass        

    appcommand_group_event_admin = app_commands.Group(
        name="event-admin",
        description="Commands for setting up/managing Events.",
        guild_only=True
        )
    
    ##################################################
    ### EVENTADMIN / LIST
    ##################################################    
    @command_group_event_admin.command(name="list")
    @commands.check(is_events_admin)
    @commands.guild_only()
    async def subcommand_event_admin_list(self,ctx:commands.Context):
        """
        Lists all active Events.
        """

        all_events = await Event.get_all_active()

        if len(all_events) == 0:
            embed = await clash_embed(
                context=ctx,
                message=f"No active Events found.",
                success=False
                )
            return await ctx.reply(embed=embed)
        
        all_events.sort(key=lambda x: x.start_time.int_timestamp)

        embed = await clash_embed(
            context=ctx,
            message=f"**Total Active Events: {len(all_events)}**\n\u200b"
            )
        e_iter = AsyncIter(all_events)
        async for event in e_iter:
            embed.add_field(
                name=f"{event.name}",
                value=f"Start Time: <t:{event.start_time.int_timestamp}:F>"
                    + f"\nDuration: {event.duration} hours"
                    + f"\nMax Participants: {event.max_participants}"
                    + f"\nTags per Participant: {event.tags_per_participant}"
                    + f"\nPrize Pool: {event.prize_pool}"
                    + f"\n\u200b"
                )        
        return await ctx.reply(embed=embed)
    
    @appcommand_group_event_admin.command(name="list",
        description="Lists all active Events.")
    @app_commands.check(is_events_admin)
    @app_commands.guild_only()
    async def appsubcommand_event_admin_list(self,interaction:discord.Interaction):
        
        await interaction.response.defer()

        all_events = await Event.get_all_active()

        if len(all_events) == 0:
            embed = await clash_embed(
                context=interaction,
                message=f"No active Events found.",
                success=False
                )
            return await interaction.followup.send(embed=embed)
        
        all_events.sort(key=lambda x: x.start_time.int_timestamp)

        embed = await clash_embed(
            context=interaction,
            message=f"**Total Active Events: {len(all_events)}**\n\u200b"
            )
        e_iter = AsyncIter(all_events)
        async for event in e_iter:
            embed.add_field(
                name=f"{event.name}",
                value=f"Start Time: <t:{event.start_time.int_timestamp}:F>"
                    + f"\nDuration: {event.duration} hours"
                    + f"\nMax Participants: {event.max_participants}"
                    + f"\nTags per Participant: {event.tags_per_participant}"
                    + f"\nPrize Pool: {event.prize_pool}"
                    + f"\n\u200b"
                )        
        return await interaction.followup.send(embed=embed)
    
    ##################################################
    ### EVENTADMIN / CREATE
    ##################################################    
    @command_group_event_admin.command(name="create")
    @commands.check(is_events_admin)
    @commands.guild_only()
    async def subcommand_event_admin_create(self,ctx:commands.Context):
        """
        Create a new Event.
        """
        return await ctx.reply(f"Please use the Slash Command `/event-admin create` for this.")
    
    @appcommand_group_event_admin.command(name="create",
        description="Create a new Event.")
    @app_commands.describe(
        name="Name of the Event.",
        description="Optional description of the Event.",
        max_participants="Maximum number of participants for this Event.",
        tags_per_participant="Number of accounts allowed per participant. Defaults to 1.",
        members_only="Restrict participation to Guild Clan Members. Defaults to False.",
        start_time="Start time for this Event in UTC. Format: YYYY-MM-DD HH:MM:SS",
        duration="Duration of the Event in hours. Defaults to 24.",
        prize_pool="Prize Pool for the Event. 0 for no prize pool.")
    @app_commands.check(is_events_admin)
    @app_commands.guild_only()
    async def appsubcommand_event_admin_create(self,
        interaction:discord.Interaction,
        name:str,
        max_participants:int,
        start_time:str,
        description:str='',
        tags_per_participant:int=1,
        members_only:bool=False,
        duration:int=24,
        prize_pool:int=0):
        
        await interaction.response.defer()

        try:
            st_time = pendulum.parse(start_time)
        except:
            embed = await clash_embed(
                context=interaction,
                message=f"Invalid Start Time format. Please use `YYYY-MM-DD HH:MM:SS`.",
                success=False
                )
            return await interaction.followup.send(embed=embed)
        
        embed = await clash_embed(
            context=interaction,
            title=f"Create Event: {name}",
            message=f"`{'Start Time:':<25}` <t:{st_time.int_timestamp}:F>"
                + f"\n`{'Duration:':<25}` {duration} hours"
                + f"\n`{'Max Participants:':<25}` {max_participants}"
                + f"\n`{'Members Only:':<25}` {members_only}"
                + f"\n`{'Tags per Participant:':<25}` {tags_per_participant}"                
                + f"\n`{'Prize Pool:':<25}` {prize_pool:,} {await bank.get_currency_name()}"
                + f"\n\u200b"
            )
        embed.add_field(
            name="Description",
            value=description
            )
        confirm_view = MenuConfirmation(interaction)

        await interaction.edit_original_response(embed=embed,view=confirm_view)
        confirmation_timed_out = await confirm_view.wait()

        if confirmation_timed_out:
            embed = await clash_embed(
                context=interaction,
                message=f"Event creation timed out.",
                success=False
                )
            return await interaction.edit_original_response(embed=embed,view=None)
        
        if not confirm_view.confirmation:
            embed = await clash_embed(
                context=interaction,
                message=f"Event creation cancelled.",
                success=False
                )
            return await interaction.edit_original_response(embed=embed,view=None)

        if confirm_view.confirmation:
            event = await Event.create(
                name=name,
                max_participants=max_participants,
                start_time=st_time,
                description=description,
                tags_per_participant=tags_per_participant,
                members_only=members_only,
                duration=duration,
                prize_pool=prize_pool
                )
            embed = await clash_embed(
                context=interaction,
                title=f"Event Created: {event.name}",
                message=f"`{'Start Time:':<25}` <t:{st_time.int_timestamp}:F>"
                    + f"\n`{'Duration:':<25}` {duration} hours"
                    + f"\n`{'Max Participants:':<25}` {max_participants}"
                    + f"\n`{'Members Only:':<25}` {members_only}"
                    + f"\n`{'Tags per Participant:':<25}` {tags_per_participant}"                
                    + f"\n`{'Prize Pool:':<25}` {prize_pool:,} {await bank.get_currency_name()}"
                    + f"\n\u200b",
                success=True
                )
            return await interaction.edit_original_response(embed=embed,view=None)
    
    ##################################################
    ### EVENTADMIN / EDIT
    ##################################################    
    @command_group_event_admin.command(name="edit")
    @commands.check(is_events_admin)
    @commands.guild_only()
    async def subcommand_event_admin_edit(self,ctx:commands.Context):
        """
        Edits an Event.
        """
        return await ctx.reply(f"Please use the Slash Command `/event-admin edit` for this.")
    
    @appcommand_group_event_admin.command(name="edit",
        description="Edit an existing Event.")
    @app_commands.describe(
        event="The Event to edit.",
        name="New name for the Event.",
        description="New description for the Event.",
        max_participants="Maximum number of participants for this Event.",
        tags_per_participant="Number of accounts allowed per participant.",
        members_only="Restrict participation to Guild Clan Members.",
        start_time="Start time for this Event in UTC. Format: YYYY-MM-DD HH:MM:SS",
        duration="Duration of the Event in hours. Defaults to 24.",
        prize_pool="Prize Pool for the Event. 0 for no prize pool.")
    @app_commands.check(is_events_admin)
    @app_commands.guild_only()
    @app_commands.autocomplete(event=autocomplete_active_events)
    async def appsubcommand_event_admin_edit(self,
        interaction:discord.Interaction,
        event:str,
        name:str=None,
        max_participants:int=None,
        start_time:str=None,
        description:str=None,
        tags_per_participant:int=None,
        members_only:bool=None,
        duration:int=None,
        prize_pool:int=None):
        
        await interaction.response.defer()

        get_event = await Event.get_event(event)
        if not get_event:
            embed = await clash_embed(
                context=interaction,
                message=f"Event not found.",
                success=False
                )
            return await interaction.followup.send(embed=embed)
        
        embed = await clash_embed(
            context=interaction,
            title=f"Edit Event: {get_event.name}",
            message=f"Please confirm the following changes:"
            )
        
        new_values = {}
        if name:
            new_values['name'] = name
            embed.add_field(
                name="Name",
                value=name,
                inline=True
                )
        if description:
            new_values['description'] = description
            embed.add_field(
                name="Description",
                value=description,
                inline=True
                )
        if max_participants:
            new_values['max_participants'] = max_participants
            embed.add_field(
                name="Max Participants",
                value=max_participants,
                inline=True
                )
        if tags_per_participant:
            new_values['tags_per_participant'] = tags_per_participant
            embed.add_field(
                name="Tags per Participant",
                value=tags_per_participant,
                inline=True
                )
        if isinstance(members_only,bool):
            new_values['members_only'] = members_only
            embed.add_field(
                name="Members Only",
                value=members_only,
                inline=True
                )
        if start_time:
            try:
                st_time = pendulum.parse(start_time)
            except:
                embed = await clash_embed(
                    context=interaction,
                    message=f"Invalid Start Time format. Please use `YYYY-MM-DD HH:MM:SS`.",
                    success=False
                    )
                return await interaction.followup.send(embed=embed)
            new_values['start_time'] = st_time.int_timestamp
            embed.add_field(
                name="Start Time",
                value=f"<t:{st_time.int_timestamp}:F>",
                inline=True
                )
        if duration:
            new_values['duration'] = duration
            embed.add_field(
                name="Duration",
                value=duration,
                inline=True
                )
        if prize_pool:
            new_values['prize_pool'] = prize_pool
            embed.add_field(
                name="Prize Pool",
                value=prize_pool,
                inline=True
                )
        
        confirm_view = MenuConfirmation(interaction)
        await interaction.edit_original_response(embed=embed,view=confirm_view)

        confirmation_timed_out = await confirm_view.wait()

        if confirmation_timed_out:
            embed = await clash_embed(
                context=interaction,
                message=f"Event edit timed out.",
                success=False
                )
            return await interaction.edit_original_response(embed=embed,view=None)
        
        if not confirm_view.confirmation:
            embed = await clash_embed(
                context=interaction,
                message=f"Event edit cancelled.",
                success=False
                )
            return await interaction.edit_original_response(embed=embed,view=None)

        if confirm_view.confirmation:
            new_event = await get_event.edit(**new_values)

            embed = await clash_embed(
                context=interaction,
                title=f"Event Edited: {new_event.name}",
                message=f"`{'Event ID:':<25}` {new_event.id}"
                    + f"\n`{'Start Time:':<25}` <t:{new_event.start_time.int_timestamp}:F>"
                    + f"\n`{'Duration:':<25}` {new_event.duration} hours"
                    + f"\n`{'Max Participants:':<25}` {new_event.max_participants}"
                    + f"\n`{'Members Only:':<25}` {new_event.members_only}"
                    + f"\n`{'Tags per Participant:':<25}` {new_event.tags_per_participant}"
                    + f"\n`{'Prize Pool:':<25}` {new_event.prize_pool}",
                success=True
                )
            return await interaction.edit_original_response(embed=embed,view=None)
    
    ##################################################
    ### EVENTADMIN / DELETE
    ##################################################    
    @command_group_event_admin.command(name="delete")
    @commands.check(is_events_admin)
    @commands.guild_only()
    async def subcommand_event_admin_delete(self,ctx:commands.Context):
        """
        Deletes an Event.

        This action is irreversible.
        """
        return await ctx.reply(f"Please use the Slash Command `/event-admin delete` for this.")
    
    @appcommand_group_event_admin.command(name="delete",
        description="Deletes an Event. This action is irreversible.")
    @app_commands.check(is_events_admin)
    @app_commands.guild_only()
    @app_commands.describe(event="The Event to delete.")
    @app_commands.autocomplete(event=autocomplete_active_events)    
    async def appsubcommand_event_admin_delete(self,interaction:discord.Interaction,event:str):

        await interaction.response.defer()

        get_event = await Event.get_event(event)

        if not get_event:
            embed = await clash_embed(
                context=interaction,
                message=f"Event not found.",
                success=False
                )
            return await interaction.followup.send(embed=embed)
        
        embed = await clash_embed(
            context=interaction,
            title=f"Delete Event: {get_event.name}",
            message=f"Are you sure you want to delete this Event?"
            )
        confirm_view = MenuConfirmation(interaction)
        await interaction.edit_original_response(embed=embed,view=confirm_view)
        confirmation_timed_out = await confirm_view.wait()

        if confirmation_timed_out:
            embed = await clash_embed(
                context=interaction,
                message=f"Event deletion timed out.",
                success=False
                )
            return await interaction.edit_original_response(embed=embed,view=None)
        
        if not confirm_view.confirmation:
            embed = await clash_embed(
                context=interaction,
                message=f"Event deletion cancelled.",
                success=False
                )
            return await interaction.edit_original_response(embed=embed,view=None)

        if confirm_view.confirmation:
            await get_event.delete()
            
            embed = await clash_embed(
                context=interaction,
                message=f"Event deleted.",
                success=True
                )
            return await interaction.edit_original_response(embed=embed,view=None)
    
    ##################################################
    ### EVENTADMIN / OPEN
    ##################################################    
    @command_group_event_admin.command(name="open")
    @commands.check(is_events_admin)
    @commands.guild_only()
    async def subcommand_event_admin_open(self,ctx:commands.Context):
        """
        Opens an Event for registration.
        """
        return await ctx.reply(f"Please use the Slash Command `/event-admin open` for this.")
    
    @appcommand_group_event_admin.command(name="open",
        description="Opens an Event for registration.")
    @app_commands.check(is_events_admin)
    @app_commands.guild_only()
    @app_commands.describe(event="The Event to open.")
    @app_commands.autocomplete(event=autocomplete_active_events)    
    async def appsubcommand_event_admin_open(self,interaction:discord.Interaction,event:str):

        await interaction.response.defer()

        get_event = await Event.get_event(event)
        if not get_event:
            embed = await clash_embed(
                context=interaction,
                message=f"Event not found.",
                success=False
                )
            return await interaction.followup.send(embed=embed)
        
        await get_event.open_event()
        embed = await clash_embed(
            context=interaction,
            message=f"Event {get_event.name} opened for registration.",
            success=True
            )
        return await interaction.followup.send(embed=embed)

    ##################################################
    ### EVENTADMIN / CLOSE
    ##################################################    
    @command_group_event_admin.command(name="close")
    @commands.check(is_events_admin)
    @commands.guild_only()
    async def subcommand_event_admin_close(self,ctx:commands.Context):
        """
        Closes an Event and stops new registrations.
        """
        return await ctx.reply(f"Please use the Slash Command `/event-admin close` for this.")
    
    @appcommand_group_event_admin.command(name="close",
        description="Closes an Event and stops new registrations.")
    @app_commands.check(is_events_admin)
    @app_commands.guild_only()
    @app_commands.describe(event="The Event to close.")
    @app_commands.autocomplete(event=autocomplete_active_events)    
    async def appsubcommand_event_admin_close(self,interaction:discord.Interaction,event:str):

        await interaction.response.defer()

        get_event = await Event.get_event(event)
        if not get_event:
            embed = await clash_embed(
                context=interaction,
                message=f"Event not found.",
                success=False
                )
            return await interaction.followup.send(embed=embed,view=None)
        
        await get_event.close_event()
        embed = await clash_embed(
            context=interaction,
            message=f"Event {get_event.name} closed for registration.",
            success=True
            )
        return await interaction.followup.send(embed=embed)

    ##################################################
    ### EVENTADMIN / LINK
    ##################################################    
    @command_group_event_admin.command(name="link")
    @commands.check(is_events_admin)
    @commands.guild_only()
    async def subcommand_event_admin_link(self,ctx:commands.Context):
        """
        Links an Event to Discord, with optional parameters.
        """
        return await ctx.reply(f"Please use the Slash Command `/event-admin link` for this.")
    
    @appcommand_group_event_admin.command(name="link",
        description="Links an Event to Discord, with optional parameters.")
    @app_commands.check(is_events_admin)
    @app_commands.guild_only()
    @app_commands.describe(
        event="The Event to link.",
        discord_event="Create the Event as a Discord Event.",
        discord_channel="Create a Discord Channel for Event participants. Also creates a Discord Role.")
    @app_commands.autocomplete(event=autocomplete_active_events)    
    async def appsubcommand_event_admin_link(self,
        interaction:discord.Interaction,
        event:str,
        discord_event:bool=False,
        discord_channel:bool=False):

        await interaction.response.defer()

        get_event = await Event.get_event(event)
        if not get_event:
            embed = await clash_embed(
                context=interaction,
                message=f"Event not found.",
                success=False
                )
            return await interaction.followup.send(embed=embed)
        
        put_discord_event = None
        if discord_event:
            put_discord_event = await get_event.create_discord_event()
        
        if discord_channel:
            await self.ticket_listener.send(f"{self.ticket_prefix}ticket {interaction.user.id} {get_event.id}")

            while True:
                get_event = await Event.get_event(event)
                if get_event.event_channel and get_event.discord_role:
                    break
                await asyncio.sleep(1)
        
        embed = await clash_embed(
            context=interaction,
            title=f"Event Linked: {get_event.name}",
            message=f"Discord Event: {getattr(put_discord_event,'name','Not Linked')}"
                + f"\nDiscord Role: {getattr(get_event.event_role,'mention','Not Linked')}"
                + f"\nDiscord Channel: {getattr(get_event.event_channel,'mention','Not Linked')}",
            success=True
            )
        return await interaction.followup.send(embed=embed)

    ##################################################
    ### EVENTADMIN / SYNC-ROLE
    ##################################################    
    @command_group_event_admin.command(name="syncrole")
    @commands.check(is_events_admin)
    @commands.guild_only()
    async def subcommand_event_admin_syncrole(self,ctx:commands.Context):
        """
        Syncs the Event Role with the Event Participants.
        """
        return await ctx.reply(f"Please use the Slash Command `/event-admin syncrole` for this.")
    
    @appcommand_group_event_admin.command(name="sync-role",
        description="Syncs the Event Role with the Event Participants.")
    @app_commands.check(is_events_admin)
    @app_commands.guild_only()
    @app_commands.describe(event="The Event to sync.")
    @app_commands.autocomplete(event=autocomplete_active_events)    
    async def appsubcommand_event_admin_syncrole(self,interaction:discord.Interaction,event:str):

        await interaction.response.defer()

        get_event = await Event.get_event(event)
        if not get_event:
            embed = await clash_embed(
                context=interaction,
                message=f"Event not found.",
                success=False
                )
            return await interaction.followup.send(embed=embed)
        
        if not get_event.event_role:
            embed = await clash_embed(
                context=interaction,
                message=f"Event Role not found.",
                success=False
                )
            return await interaction.followup.send(embed=embed)
        
        await get_event.sync_role()

        embed = await clash_embed(
            context=interaction,
            message=f"Event Role synced with Participants.",
            success=True
            )
        return await interaction.followup.send(embed=embed)

    ##################################################
    ### EVENTADMIN / EXPORT
    ##################################################    
    @command_group_event_admin.command(name="export")
    @commands.check(is_events_admin)
    @commands.guild_only()
    async def subcommand_event_admin_export(self,ctx:commands.Context):
        """
        Exports the Event Participants to Excel.
        """
        return await ctx.reply(f"Please use the Slash Command `/event-admin export` for this.")
    
    @appcommand_group_event_admin.command(name="export",
        description="Exports the Event Participants to Excel.")
    @app_commands.check(is_events_admin)
    @app_commands.guild_only()
    @app_commands.describe(event="The Event to export.")
    @app_commands.autocomplete(event=autocomplete_active_events)    
    async def appsubcommand_event_admin_export(self,interaction:discord.Interaction,event:str):

        await interaction.response.defer()

        get_event = await Event.get_event(event)
        if not get_event:
            embed = await clash_embed(
                context=interaction,
                message=f"Event not found.",
                success=False
                )
            return await interaction.followup.send(embed=embed)
        
        await interaction.edit_original_response("Exporting Event Participants... please wait.")
        rp_file = await generate_event_export(get_event)

        if not rp_file:
            await interaction.edit_original_response("Error exporting Event Participants.")
        
        await interaction.edit_original_response(
            content="Event Participants for {get_event.name} exported.",
            file=discord.File(rp_file)
            )
    
    ############################################################
    #####
    ##### COMMAND GROUP: EVENT
    ##### 
    ############################################################
    @commands.group(name="event")
    @commands.guild_only()
    async def command_group_event(self,ctx:commands.Context):
        """
        Register/Withdraw from Events.
        """
        if not ctx.invoked_subcommand:
            pass        

    appcommand_group_event = app_commands.Group(
        name="event",
        description="Register/Withdraw from Events.",
        guild_only=True
        )
    
    ##################################################
    ### EVENT / REGISTER
    ##################################################    
    @command_group_event.command(name="register")
    @commands.guild_only()
    async def subcommand_event_register(self,ctx:commands.Context):
        """
        Register for an Event.
        """
        return await ctx.reply(f"Please use the Slash Command `/event register` for this.")
    
    @appcommand_group_event.command(name="register",
        description="Register for an Event.")
    @app_commands.guild_only()
    @app_commands.describe(
        event="The Event to register for.",
        account="The account to register with for the Event.",
        discord_user="For Events Admin use only. The Discord User to register for.")
    @app_commands.autocomplete(
        event=autocomplete_active_events,
        account=autocomplete_user_players)
    async def appsubcommand_event_register(self,
        interaction:discord.Interaction,
        event:str,
        account:str,
        discord_user:discord.Member=None):

        await interaction.response.defer()

        get_event = await Event.get_event(event)
        if not get_event:
            embed = await clash_embed(
                context=interaction,
                message=f"Event not found.",
                success=False
                )
            return await interaction.followup.send(embed=embed)
        
        if is_events_admin(interaction) and discord_user:
            user = discord_user
        else:
            user = interaction.user
        
        account = await bot_client.coc.get_player(account)
        if account.discord_user != user.id and not is_events_admin(interaction):
            embed = await clash_embed(
                context=interaction,
                message=f"Invalid account. You can only register with your own linked accounts.",
                success=False
                )
            return await interaction.followup.send(embed=embed)

        try:
            participant = await get_event.register_participant(account.tag,user.id)
        except EventClosed:
            embed = await clash_embed(
                context=interaction,
                message=f"The Event you are registering for is not open for registration.",
                success=False
                )
            return await interaction.followup.send(embed=embed)
        except NotEligible:
            embed = await clash_embed(
                context=interaction,
                message=f"This is a Members-only Event. You are not eligible to register.",
                success=False
                )
            return await interaction.followup.send(embed=embed)
        except AlreadyRegistered:
            embed = await clash_embed(
                context=interaction,
                message=f"You have already reached the maximum registrations allowed for this event.",
                success=False
                )
            return await interaction.followup.send(embed=embed)

        if interaction.user.id == user.id:
            embed = await clash_embed(
                context=interaction,
                message=f"You have registered for **{get_event.name}** with the account **{participant.title}**.",
                success=True
                )
            return await interaction.followup.send(embed=embed)
        else:
            embed = await clash_embed(
                context=interaction,
                message=f"{user.display_name} has been registered for **{get_event.name}** with the account **{participant.title}**.",
                success=True
                )
            return await interaction.followup.send(embed=embed)
    
    ##################################################
    ### EVENT / WITHDRAW
    ##################################################    
    @command_group_event.command(name="withdraw")
    @commands.guild_only()
    async def subcommand_event_withdraw(self,ctx:commands.Context):
        """
        Withdraw from an Event.
        """
        return await ctx.reply(f"Please use the Slash Command `/event withdraw` for this.")
    
    @appcommand_group_event.command(name="withdraw",
        description="Withdraw from an Event.")
    @app_commands.guild_only()
    @app_commands.describe(
        event="The Event to withdraw from.",
        account="The account to withdraw from the Event.")
    @app_commands.autocomplete(
        event=autocomplete_active_events,
        account=autocomplete_user_players)
    async def appsubcommand_event_withdraw(self,
        interaction:discord.Interaction,
        event:str,
        account:str):

        await interaction.response.defer()

        get_event = await Event.get_event(event)
        if not get_event:
            embed = await clash_embed(
                context=interaction,
                message=f"Event not found.",
                success=False
                )
            return await interaction.followup.send(embed=embed)
        
        participant = await get_event.get_participant(account)
        if not participant:
            embed = await clash_embed(
                context=interaction,
                message=f"This account is not registered for the Event.",
                success=False
                )
            return await interaction.followup.send(embed=embed)
        
        if participant.participant_id != interaction.user.id and not is_events_admin(interaction):
            embed = await clash_embed(
                context=interaction,
                message=f"You can only withdraw your own registrations.",
                success=False
                )
            return await interaction.followup.send(embed=embed)
        
        try:
            await get_event.withdraw_participant(participant.tag)
        except EventClosed:
            embed = await clash_embed(
                context=interaction,
                message=f"The Event you are withdrawing from is not open for registration.",
                success=False
                )
            return await interaction.followup.send(embed=embed)
        
        embed = await clash_embed(
            context=interaction,
            message=f"The account {participant.title} is withdrawn from {get_event.name}.",
            success=True
            )
        return await interaction.followup.send(embed=embed)
    
    ##################################################
    ### EVENT / MYSIGNUPS
    ##################################################    
    @command_group_event.command(name="mysignups")
    @commands.guild_only()
    async def subcommand_event_mysignups(self,ctx:commands.Context):
        """
        Lists all your registrations for Events.
        """
        return await ctx.reply(f"Please use the Slash Command `/event my-signups` for this.")
    
    @appcommand_group_event.command(name="my-signups",
        description="Lists all your registrations for Events.")
    @app_commands.guild_only()
    async def appsubcommand_event_mysignups(self,interaction:discord.Interaction):

        await interaction.response.defer()

        participating_events = await Event.get_participating_for_user(interaction.user.id)

        if len(participating_events) == 0:
            embed = await clash_embed(
                context=interaction,
                message=f"You are currently not registered for any Events.",
                success=False
                )
            return await interaction.followup.send(embed=embed)

        embed = await clash_embed(
            context=interaction,
            message=f"You are registered for the following Events:",
            thumbnail=getattr(interaction.user.avatar,'url','')
            )
        e_iter = AsyncIter(participating_events)
        async for event in e_iter:
            accounts = await event.get_participants_for_user(interaction.user.id)
            embed.add_field(
                name=f"{event.name}",
                value=f"Start Time: <t:{event.start_time.int_timestamp}:F>\n"
                    + '\n'.join([f"- {p.title}" for p in accounts])
                    + f"\n\u200b",
                inline=False
                )
        return await interaction.followup.send(embed=embed)

    ##################################################
    ### EVENT / INFO
    ##################################################    
    @command_group_event.command(name="info")
    @commands.guild_only()
    async def subcommand_event_info(self,ctx:commands.Context):
        """
        Displays information about an Event.
        """
        return await ctx.reply(f"Please use the Slash Command `/event info` for this.")
    
    @appcommand_group_event.command(name="info",
        description="Displays information about an Event.")
    @app_commands.guild_only()
    @app_commands.describe(event="The Event to get information for.")
    @app_commands.autocomplete(event=autocomplete_active_events)
    async def appsubcommand_event_info(self,interaction:discord.Interaction,event:str):

        await interaction.response.defer()

        get_event = await Event.get_event(event)
        if not get_event:
            embed = await clash_embed(
                context=interaction,
                message=f"Event not found.",
                success=False
                )
            return await interaction.followup.send(embed=embed)
        
        count = await get_event.get_participant_count()
        currency = await bank.get_currency_name()

        embed = await clash_embed(
            context=interaction,
            title=f"{get_event.name}",
            message=f"{get_event.description}"
                + f"\n\n`{'Start Time:':<15}` <t:{get_event.start_time.int_timestamp}:F>"
                + f"\n`{'End Time:':<15}` <t:{get_event.end_time.int_timestamp}:F>"
                + f"\n`{'Prize Pool:':<15}` {get_event.prize_pool} {currency}"
                + f"\n## Registration"
                + f"\n`{'Status:':<15}` {get_event.status}"
                + f"\n`{'Available:':<15}` {get_event.max_participants - count}/{get_event.max_participants}"
                + f"\n`{'Max per User:':<15}` {get_event.tags_per_participant}"
                + f"\n`{'Members Only:':<15}` {get_event.members_only}"
            )
        return await interaction.followup.send(embed=embed)