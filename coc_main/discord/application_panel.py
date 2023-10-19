import discord

from typing import *
from mongoengine import *

from ..cog_coc_client import ClashOfClansClient
from ..api_client import BotClashClient as client

from ..coc_objects.clans.clan import aClan

from .mongo_discord import db_GuildApplyPanel
from .user_application import ClanApplyMenuUser

from ..utils.components import DiscordButton, DiscordSelectMenu

bot_client = client()

##################################################
#####
##### APPLICATION PANEL
#####
##################################################
class GuildApplicationPanel():
    
    @classmethod
    def get_from_id(cls,panel_id:dict):
        try:
            panel = db_GuildApplyPanel.objects.get(panel_id=panel_id)
        except DoesNotExist:
            return None
        return cls(panel)
    
    @classmethod
    def get_panel(cls,guild_id:int,channel_id:int):
        try:
            panel = db_GuildApplyPanel.objects.get(
                server_id=guild_id,
                channel_id=channel_id
                )
        except DoesNotExist:
            return None
        return cls(panel)

    # @classmethod
    # async def get_guild_panels(cls,guild_id:int):
    #     return [cls(link) for link in db_GuildApplyPanel.objects(server_id=guild_id)]    

    def __init__(self,database_entry:db_GuildApplyPanel):        
        self.id = database_entry.panel_id
        
        self.guild_id = database_entry.server_id
        self.channel_id = database_entry.channel_id
        self.message_id = database_entry.message_id

        self.can_user_select_clans = database_entry.select_clans

        self.tickettool_prefix = database_entry.ticket_prefix
        self._tickettool_channel = database_entry.listener_channel

        self.text_q1 = database_entry.text_q1
        self.placeholder_q1 = database_entry.placeholder_q1
        self.text_q2 = database_entry.text_q2
        self.placeholder_q2 = database_entry.placeholder_q2
        self.text_q3 = database_entry.text_q3
        self.placeholder_q3 = database_entry.placeholder_q3
        self.text_q4 = database_entry.text_q4
        self.placeholder_q4 = database_entry.placeholder_q4
    
    def __str__(self):
        return f"Application Panel (Channel: {getattr(self.channel,'name','Unknown Channel')})"
    
    @classmethod
    async def create(cls,guild_id:int,channel_id:int):
        panel_id = {'guild':guild_id,'channel':channel_id}

        try:
            panel = db_GuildApplyPanel.objects.get(
                server_id=guild_id,
                channel_id=channel_id
                )
        except DoesNotExist:
            panel = db_GuildApplyPanel(
                panel_id = panel_id,
                server_id = guild_id,
                channel_id = channel_id
                )
            panel.save()
        return cls(panel)

    async def delete(self):
        db_GuildApplyPanel.objects(panel_id=self.id).delete()
        message = await self.fetch_message()
        if message:
            await message.delete()
    
    def save(self):
        db_panel = db_GuildApplyPanel(
            panel_id = self.id,
            server_id = self.guild_id,
            channel_id = self.channel_id,
            message_id = self.message_id,
            select_clans = self.can_user_select_clans,
            ticket_prefix = self.tickettool_prefix,
            listener_channel = self._tickettool_channel,
            text_q1 = self.text_q1,
            placeholder_q1 = self.placeholder_q1,
            text_q2 = self.text_q2,
            placeholder_q2 = self.placeholder_q2,
            text_q3 = self.text_q3,
            placeholder_q3 = self.placeholder_q3,
            text_q4 = self.text_q4,
            placeholder_q4 = self.placeholder_q4
            )
        db_panel.save()

    @property
    def guild(self) -> Optional[discord.Guild]:
        return bot_client.bot.get_guild(self.guild_id)
    
    @property
    def channel(self) -> Optional[discord.TextChannel]:
        if not self.guild:
            return None
        return self.guild.get_channel(self.channel_id)

    @property
    def listener_channel(self) -> Optional[discord.TextChannel]:
        return self.guild.get_channel(self._tickettool_channel)
    
    async def fetch_message(self) -> Optional[discord.Message]:
        if self.channel:
            try:
                return await self.channel.fetch_message(self.message_id)
            except discord.NotFound:
                pass
        return None
    
    async def send_to_discord(self,embed:discord.Embed,view:discord.ui.View):
        try:
            if not self.channel:
                await self.delete()
                return
            
            message = await self.fetch_message()
            if not message:
                message = await self.channel.send(
                    embed=embed,
                    view=view
                    )
                db_GuildApplyPanel.objects(panel_id=self.id).update_one(set__message_id=message.id)
            else:
                message = await message.edit(
                    embed=embed,
                    view=view
                    )
        
        except Exception as exc:
            bot_client.coc_main_log.exception(
                f"Error sending Application Panel to Discord: {self.guild.name} {getattr(self.channel,'name','Unknown Channel')}. {exc}"
                )

##################################################
#####
##### VIEW FOR APPLICATION PANEL
#####
##################################################
class ClanApplyMenu(discord.ui.View):
    def __init__(self,panel:GuildApplicationPanel,list_of_clans:List[aClan]):
        
        self.panel = panel
        self.clans = list_of_clans
        super().__init__(timeout=None)

        if self.panel.can_user_select_clans:
            self.add_item(self.select_menu())
        else:
            self.add_item(self.apply_button())
    
    @property
    def coc_client(self) -> ClashOfClansClient:
        return bot_client.bot.get_cog("ClashOfClansClient")

    async def on_timeout(self):
        pass

    def select_menu(self):
        dropdown_options = [discord.SelectOption(
            label=f"{clan.name}" + " | " + f"{clan.tag}",
            value=clan.tag,
            emoji=clan.emoji
            )
            for clan in self.clans
            ]
        # if self.panel.guild_id == 1132581106571550831:
        #     dropdown_options.append(discord.SelectOption(
        #         label=f"I am an existing member of WOL/RTD.",
        #         value="rtd_onboarding"
        #         ))
        dropdown_menu = DiscordSelectMenu(
            function=self._callback_select_clan,
            options=dropdown_options,
            placeholder="Select one or more Clan(s) to apply to.",
            min_values=1,
            max_values=len(dropdown_options)
            )
        return dropdown_menu

    async def _callback_select_clan(self,interaction:discord.Interaction,select:discord.ui.Select):
        await interaction.response.defer(ephemeral=True)

        self.clear_items()
        if self.panel.can_user_select_clans:
            self.add_item(self.select_menu())
        else:
            self.add_item(self.apply_button())
        await interaction.followup.edit_message(interaction.message.id,view=self)

        await ClanApplyMenuUser.start_user_application(interaction,select.values)
    
    def apply_button(self):
        apply_button = DiscordButton(
            function=self._callback_apply,
            label="Click here to apply to any of our Clans!",
            style=discord.ButtonStyle.blurple
            )
        return apply_button
    
    async def _callback_apply(self,interaction:discord.Interaction,select:discord.ui.Button):
        await interaction.response.defer(ephemeral=True)

        self.clear_items()
        if self.panel.can_user_select_clans:
            self.add_item(self.select_menu())
        else:
            self.add_item(self.apply_button())
        await interaction.followup.edit_message(interaction.message.id,view=self)

        await ClanApplyMenuUser.start_user_application(interaction)