import discord
import asyncio

from typing import *

from redbot.core import commands
from redbot.core.utils import AsyncIter
from redbot.core.utils import chat_formatting as chat

from coc_main.api_client import CommandUnauthorized

from coc_main.coc_objects.clans.clan import aClan
from coc_main.discord.feeds.clan_feed import ClanDataFeed, feed_description
from coc_main.discord.feeds.member_movement import ClanMemberFeed
from coc_main.discord.feeds.donations import ClanDonationFeed
from coc_main.discord.feeds.raid_results import RaidResultsFeed
from coc_main.discord.feeds.reminders import EventReminder

from coc_main.utils.components import clash_embed, DiscordButton, DiscordSelectMenu, DiscordChannelSelect, DefaultView, DiscordModal

from coc_main.utils.constants.coc_emojis import EmojisTownHall
from coc_main.utils.constants.ui_emojis import EmojisUI

class ClanSettingsMenu(DefaultView):
    def __init__(self,
        context:Union[commands.Context,discord.Interaction],
        clan:aClan):
        
        self.clan = clan
        self.main_menu_options = ['Discord Feed','War Reminders','Raid Reminders']
        if self.clan.is_alliance_clan:
            self.main_menu_options.append('Recruiting')
        
        self.clan_feeds = []
        self.war_reminders = []
        self.raid_reminders = []
            
        super().__init__(context)
    
    ####################################################################################################
    #####
    ##### VIEW HELPERS
    #####
    ####################################################################################################

    ##################################################
    ### START / STOP CALL
    ##################################################
    async def start(self):        
        check_permissions = False
        if (self.user.id == self.clan.leader or self.user.id in self.clan.coleaders):
            check_permissions = True
        if self.user.id in self.bot.owner_ids:
            check_permissions = True
        
        if not check_permissions:
            self.stop_menu()
            raise CommandUnauthorized

        self.load_main_menu_items()
        embed = await self.get_main_embed()

        self.is_active = True
        if isinstance(self.ctx,discord.Interaction):
            await self.ctx.edit_original_response(embed=embed,view=self)
            self.message = await self.ctx.original_response()
        else:
            self.message = await self.ctx.reply(embed=embed,view=self)

    ##################################################
    ### CALLBACK CLOSE
    ##################################################
    async def _close(self,interaction:discord.Interaction,button:DiscordButton):
        self.stop_menu()
        embed = await clash_embed(
            context=self.ctx,
            message=f"**Menu closed**")
        await interaction.response.edit_message(embed=embed,view=None,delete_after=60)

    def home_button(self):
        return DiscordButton(
            function=self._main_menu,
            label="Main Menu",
            emoji=EmojisUI.HOME,
            style=discord.ButtonStyle.blurple,
            row=0
            )
    def close_button(self):
        return DiscordButton(
            function=self._close,
            label="Close",
            emoji=EmojisUI.EXIT,
            style=discord.ButtonStyle.red,
            row=0
            )
    
    ####################################################################################################
    #####
    ##### MAIN MENU
    #####
    ####################################################################################################
    
    ##################################################
    ### MAIN MENU FUNCTIONS
    ##################################################
    async def _main_menu(self,interaction:discord.Interaction,button:Optional[DiscordButton]=None):
        if not interaction.response.is_done():
            await interaction.response.defer()

        self.load_main_menu_items()
        embed = await self.get_main_embed()
        await interaction.edit_original_response(embed=embed,view=self)

    async def _callback_main_menu(self,interaction:discord.Interaction,menu:DiscordSelectMenu):
        if not interaction.response.is_done():
            await interaction.response.defer()

        select_menu = self.main_menu_options[int(menu.values[0])]

        if select_menu == 'Recruiting':
            await self._recruiting_menu(interaction)

        elif select_menu == 'Discord Feed':
            await self._discord_feed_menu(interaction)
            
        elif select_menu == 'War Reminders':
            await self._war_reminder_menu(interaction)

        elif select_menu == 'Raid Reminders':
            await self._raid_reminder_menu(interaction)
        else:
            await self._main_menu(interaction)
    
    ##################################################
    ### MAIN MENU HELPERS
    ##################################################    
    def load_main_menu_items(self):        
        self.clear_items()

        settings_option = [discord.SelectOption(
            label=text,
            value=i)
            for i,text in enumerate(self.main_menu_options)]        

        settings_menu = DiscordSelectMenu(
            function=self._callback_main_menu,
            options=settings_option,
            placeholder="Select a Setting to change.",
            min_values=1,
            max_values=1,
            row=1
            )
        self.add_item(self.home_button())
        self.add_item(self.close_button())
        self.add_item(settings_menu)        

    async def get_main_embed(self):
        embed = await clash_embed(
            context=self.ctx,
            title=f"Clan Settings: {self.clan.title}",
            message=(f"\nClan Leader: <@{self.clan.leader}>\n" if self.clan.leader else "")
                + f"{self.clan.long_description}"
                + f"\n\n**To change Clan Settings, select an option from the dropdown below.**"
                + f"\n\u200b",
            thumbnail=self.clan.badge
            )
        if self.clan.is_alliance_clan:
            embed.add_field(
                name="__**Recruiting**__",
                value=f"Configure a Clan's Recruiting Configuration, such as the recruiting TH Levels, the custom Description and Recruiting instructions.\n\u200b",
                inline=False
                )
        embed.add_field(
            name="__**Discord Feed**__",
            value=f"Configure the automated bot feed in Discord, such as the Donation and Join/Leave log.\n\u200b",
            inline=False
            )        
        embed.add_field(
            name="__**War Reminders**__",
            value=f"Set up Clan War Reminders for this Clan. Reminders are sent to players who have unused attacks during Battle Day.\n\u200b",
            inline=False
            )        
        embed.add_field(
            name="__**Capital Raids**__",
            value=f"Configure Capital Raid Reminders for this Clan. Reminders are sent to players who started but did not finish all their attacks during Raid Weekend.\n\u200b",
            inline=False
            )
        return embed
    
    ####################################################################################################
    #####
    ##### RECRUITING MENU
    #####
    ####################################################################################################

    ##################################################
    ### RECRUITING MENU FUNCTIONS
    ##################################################
    async def _recruiting_menu(self,interaction:discord.Interaction):
        if not interaction.response.is_done():
            await interaction.response.defer()

        self.load_recruiting_menu_items()
        embed = await self.recruiting_menu_embed()
        await interaction.edit_original_response(embed=embed,view=self)

    async def _clan_description_callback(self,interaction:discord.Interaction,button:DiscordButton):
        def response_check(m):
            return m.author.id == self.user.id and m.channel.id == self.channel.id
        
        await interaction.response.defer()
        for item in self.children:
            item.disabled = True

        embed = await self.recruiting_menu_embed()        
        desc_embed = await clash_embed(
            context=interaction,
            message=f"Please enter the new Description for **{self.clan.title}**. To cancel, type `cancel`."
                + "\n\n**Note: When using emojis, please note that only emojis found in this server are usable.**",
            show_author=False)
        await interaction.edit_original_response(embeds=[embed,desc_embed],view=self)

        try:
            self.waiting_for = True
            response_msg = await self.bot.wait_for("message",timeout=180,check=response_check)
        except asyncio.TimeoutError:
            await interaction.followup.send(content=f"Oops! You timed out.",ephemeral=True)
        else:
            if response_msg.content.lower() == "cancel":
                pass
            else:
                await self.clan.set_description(response_msg.content)
            await response_msg.delete()
        finally:
            self.waiting_for = False
            await self._recruiting_menu(interaction)
    
    async def _clan_recr_instruction_callback(self,interaction:discord.Interaction,button:DiscordButton):
        def response_check(m):
            return m.author.id == self.user.id and m.channel.id == self.channel.id
        
        await interaction.response.defer()
        for item in self.children:
            item.disabled = True

        embed = await self.get_main_embed()        
        desc_embed = await clash_embed(
            context=interaction,
            message=f"Please enter the new Recruitment Instruction for **{self.clan.title}**. To cancel, type `cancel`."
                + "\n\n**Note: When using emojis, please note that only emojis found in this server are usable.**",
            show_author=False)
        await interaction.edit_original_response(embeds=[embed,desc_embed],view=self)

        try:
            self.waiting_for = True
            response_msg = await self.bot.wait_for("message",timeout=180,check=response_check)
        except asyncio.TimeoutError:
            await interaction.followup.send(content=f"Oops! You timed out.",ephemeral=True)
        else:
            if response_msg.content.lower() == "cancel":
                pass
            else:
                await self.clan.set_recruitment_info(response_msg.content)
            await response_msg.delete()
        finally:
            self.waiting_for = False
            await self._recruiting_menu(interaction)
            self.load_recruiting_menu_items()
    
    async def _callback_recruitment_level(self,interaction:discord.Interaction,menu:DiscordSelectMenu):
        await interaction.response.defer()        
        menu.disabled = True

        th_values = [int(th) for th in menu.values]
        th_values.sort()
        await self.clan.set_recruitment_level(th_values)

        await self._recruiting_menu(interaction)
    
    ##################################################
    ### RECRUITING MENU HELPERS
    ################################################## 
    def load_recruiting_menu_items(self):
        self.clear_items()

        recruitment_options = [discord.SelectOption(
            label=f"TH{th}",
            value=th,
            emoji=EmojisTownHall.get(th),
            default=th in self.clan.recruitment_level)
            for th in range(16,0,-1)]
        select_recruitment_level = DiscordSelectMenu(
            function=self._callback_recruitment_level,
            options=recruitment_options,
            placeholder="Change the Recruitment TH Levels.",
            min_values=0,
            max_values=16,
            row=2
            )        
        button_clan_description = DiscordButton(
            function=self._clan_description_callback,
            label="Change Clan Description",
            row=1
            )        
        button_rec_instruction = DiscordButton(
            function=self._clan_recr_instruction_callback,
            label="Change Recruiting Instruction",
            row=1
            )
        self.add_item(self.home_button())
        self.add_item(self.close_button())
        self.add_item(button_clan_description)
        self.add_item(button_rec_instruction)        
        self.add_item(select_recruitment_level)        
    
    async def recruiting_menu_embed(self):
        embed = await clash_embed(
            context=self.ctx,
            title=f"Recruiting Settings: {self.clan.title}",
            message=f"**TH Levels:** {self.clan.recruitment_level_emojis}"
                + f"\n*To change the Recruiting THs, select values from the dropdown.*"
                + f"\n\n**Clan Description**"
                + f"\n{self.clan.description}"
                + f"\n\n**Recruiting Instruction**"
                + f"\n{self.clan.recruitment_info}"
                ,
            thumbnail=self.clan.badge
            )
        return embed
    
    ####################################################################################################
    #####
    ##### DISCORD FEED MENU
    #####
    ####################################################################################################

    ##################################################
    ### DISCORD FEED FUNCTIONS
    ##################################################
    async def _discord_feed_menu(self,interaction:discord.Interaction):
        if not interaction.response.is_done():
            await interaction.response.defer()

        self.clan_feeds = [i for i in await ClanDataFeed.feeds_for_clan(self.clan) if i.guild_id == self.guild.id]

        self.load_discordfeed_menu_items()
        embed = await self.discordfeed_embed()
        await interaction.edit_original_response(embed=embed,view=self)
    
    async def _callback_discordfeed_back(self,interaction:discord.Interaction,button:DiscordButton):
        await interaction.response.defer()

        self.feed_type = None
        self.feed_channel = None

        await self._discord_feed_menu(interaction)
    
    async def _callback_add_feed(self,interaction:discord.Interaction,button:DiscordButton):
        await interaction.response.defer()

        self.feed_type = None
        self.feed_channel = None

        self.load_addfeed_menu_items()
        embed = await self.discordfeed_embed()
        embed2 = await self.discordfeed_add_embed()

        await interaction.edit_original_response(embeds=[embed,embed2],view=self)
    
    async def _callback_select_feed_type(self,interaction:discord.Interaction,menu:DiscordSelectMenu):
        await interaction.response.defer()
        self.feed_type = menu.values[0]
        
        self.load_addfeed_menu_items()        
        embed1 = await self.discordfeed_embed()
        embed2 = await self.discordfeed_add_embed()
        await interaction.edit_original_response(embeds=[embed1,embed2],view=self)
    
    async def _callback_select_feed_channel(self,interaction:discord.Interaction,menu:DiscordChannelSelect):
        await interaction.response.defer()
        self.feed_channel = menu.values[0]
        
        self.load_addfeed_menu_items()
        embed1 = await self.discordfeed_embed()
        embed2 = await self.discordfeed_add_embed()
        await interaction.edit_original_response(embeds=[embed1,embed2],view=self)
    
    async def _callback_save_feed(self,interaction:discord.Interaction,button:DiscordButton):
        await interaction.response.defer()

        if self.feed_type == 'Member Join/Leave':
            await ClanMemberFeed.create_feed(self.clan,self.feed_channel)
        
        if self.feed_type == 'Donation Log':
            await ClanDonationFeed.create_feed(self.clan,self.feed_channel)
        
        if self.feed_type == 'Raid Weekend Results':
            await RaidResultsFeed.create_feed(self.clan,self.feed_channel)

        self.feed_type = None
        self.feed_channel = None
        await self._discord_feed_menu(interaction)
        
    async def _callback_delete_feed_start(self,interaction:discord.Interaction,button:DiscordButton):
        await interaction.response.defer()

        self.clan_feeds = [i for i in await ClanDataFeed.feeds_for_clan(self.clan) if i.guild_id == self.guild.id]
        self.load_deletefeed_menu_items()
        embed = await self.discordfeed_embed()
        await interaction.edit_original_response(embeds=[embed],view=self)
    
    async def _callback_delete_feed(self,interaction:discord.Interaction,menu:DiscordSelectMenu):
        await interaction.response.defer()

        a_iter = AsyncIter(menu.values)
        async for i in a_iter:
            feed = await ClanDataFeed.get_by_id(i)
            await feed.delete()

        self.clan_feeds = [i for i in await ClanDataFeed.feeds_for_clan(self.clan) if i.guild_id == self.guild.id]
        self.load_deletefeed_menu_items()
        embed = await self.discordfeed_embed()
        await interaction.edit_original_response(embed=embed,view=self)
    
    ##################################################
    ### DISCORD FEED MENUS
    ##################################################
    def load_discordfeed_menu_items(self):
        self.clear_items()

        add_feed_button = DiscordButton(
            function=self._callback_add_feed,
            emoji=EmojisUI.ADD,
            label="Add Feed",
            row=0
            )
        delete_feed_button = DiscordButton(
            function=self._callback_delete_feed_start,
            emoji=EmojisUI.DELETE,
            label="Delete Feed",
            row=0
            )        
        if len(self.clan_feeds) >= 20:
            add_feed_button.disabled = True        
        if len(self.clan_feeds) == 0:
            delete_feed_button.disabled = True

        self.add_item(self.home_button())
        self.add_item(add_feed_button)
        self.add_item(delete_feed_button)
        self.add_item(self.close_button())
    
    def load_addfeed_menu_items(self):
        self.clear_items()
        back_button = DiscordButton(
            function=self._callback_discordfeed_back,
            emoji=EmojisUI.GREEN_PREVIOUS,
            label="Back",
            row=0
            )
        save_feed_button = DiscordButton(
            function=self._callback_save_feed,
            emoji=EmojisUI.YES,
            label="Save Feed",
            row=0
            )
        if not self.feed_type:
            save_feed_button.disabled = True
        if not self.feed_channel:
            save_feed_button.disabled = True

        type_options = ['Member Join/Leave','Donation Log','Raid Weekend Results']
        select_options = [discord.SelectOption(
            label=text,
            value=text,
            default=text == self.feed_type)
            for i,text in enumerate(type_options)
            ]
        select_feed_type = DiscordSelectMenu(
            function=self._callback_select_feed_type,
            options=select_options,
            placeholder="Select a Feed Type.",
            min_values=1,
            max_values=1,
            row=1
            )
        select_feed_channel = DiscordChannelSelect(
            function=self._callback_select_feed_channel,
            channel_types=[discord.ChannelType.text,discord.ChannelType.public_thread],
            placeholder="Select the Feed Channel...",
            min_values=1,
            max_values=1,
            row=2
            )        
        self.add_item(back_button)
        self.add_item(save_feed_button)
        self.add_item(select_feed_type)
        self.add_item(select_feed_channel)
    
    def load_deletefeed_menu_items(self):
        self.clear_items()        
        back_button = DiscordButton(
            function=self._callback_discordfeed_back,
            emoji=EmojisUI.GREEN_PREVIOUS,
            label="Back",
            row=0
            )
        self.add_item(back_button)

        clan_member_feed_options = [discord.SelectOption(
            label=f"Join/Leave Log: {getattr(feed.channel,'name','Unknown Channel')}",
            value=str(feed._id))
            for feed in self.clan_feeds if feed.type == 1
            ]
        clan_donation_feed_options = [discord.SelectOption(
            label=f"Donation Log: {getattr(feed.channel,'name','Unknown Channel')}",
            value=str(feed._id))
            for feed in self.clan_feeds if feed.type == 2
            ]
        clan_capital_raid_feed_options = [discord.SelectOption(
            label=f"Raid Results: {getattr(feed.channel,'name','Unknown Channel')}",
            value=str(feed._id))
            for feed in self.clan_feeds if feed.type == 3
            ]
        options = clan_member_feed_options + clan_donation_feed_options + clan_capital_raid_feed_options
        
        if len(options) > 0:            
            select_feed_type = DiscordSelectMenu(
                function=self._callback_delete_feed,
                options=options,
                placeholder="Select a Feed to Delete.",
                min_values=1,
                max_values=len(options),
                row=1
                )         
            self.add_item(select_feed_type)
    
    ##################################################
    ### DISCORD FEED EMBEDS
    ##################################################
    async def discordfeed_embed(self):
        embed = await clash_embed(
            context=self.ctx,
            title=f"Discord Feed: {self.clan.title}",
            message=f"**Only Feeds for the current Server are displayed below.**"
                + f"\nAvailable Slots: **{20 - len(self.clan_feeds)}** available (max: 20)"
                + "\n\u200b",
            thumbnail=self.clan.badge
            )
        
        async for feed in AsyncIter(self.clan_feeds):
            embed.add_field(
                name=f"{getattr(feed.channel,'name','Unknown Channel')}",
                value=(f"Channel: {getattr(feed.channel,'mention','')}\n" if feed.channel else "")
                    + f"Type: {feed.description}",
                inline=False
                )
        return embed
    
    async def discordfeed_add_embed(self):
        embed = await clash_embed(
            context=self.ctx,
            message=f"**You are adding a new Clan Feed.**"
                + f"\nSelect a Feed Type and a Channel, then press **Save Feed**."
                + f"\n\nSelected Type: {self.feed_type}"
                + f"\nSelected Channel: {getattr(self.feed_channel,'mention','Not Set')}"
                )
        return embed
    
    ####################################################################################################
    #####
    ##### CLAN WAR REMINDER MENU
    #####
    ####################################################################################################

    ##################################################
    ### CLAN WAR REMINDER FUNCTIONS
    ##################################################
    async def _war_reminder_menu(self,interaction:discord.Interaction):
        if not interaction.response.is_done():
            await interaction.response.defer()

        self.war_reminders = [r for r in await EventReminder.war_reminders_for_clan(self.clan) if r.guild_id == self.guild.id]
        self.load_war_reminder_menu_items()

        embed = await self.war_reminder_embed()
        await interaction.edit_original_response(embed=embed,view=self)

    async def _callback_war_reminder_back(self,interaction:discord.Interaction,button:DiscordButton):
        await interaction.response.defer()

        self.wrem_type = []
        self.wrem_interval = []
        self.wrem_channel = None

        await self._war_reminder_menu(interaction)
    
    async def _callback_add_war_reminder_start(self,interaction:discord.Interaction,button:DiscordButton):
        await interaction.response.defer()

        self.wrem_type = []
        self.wrem_interval = []
        self.wrem_channel = None

        self.war_reminders = [r for r in await EventReminder.war_reminders_for_clan(self.clan) if r.guild_id == self.guild.id]
        self.load_add_war_reminder_menu_items()
        embed = await self.war_reminder_embed()
        embed2 = await self.add_war_reminder_embed()

        await interaction.edit_original_response(embeds=[embed,embed2],view=self)
    
    async def _callback_select_war_reminder_type(self,interaction:discord.Interaction,menu:DiscordSelectMenu):
        await interaction.response.defer()
        self.wrem_type = menu.values
        
        self.load_add_war_reminder_menu_items()
        embed = await self.war_reminder_embed()
        embed2 = await self.add_war_reminder_embed()
        await interaction.edit_original_response(embeds=[embed,embed2],view=self)
    
    async def _callback_select_war_reminder_channel(self,interaction:discord.Interaction,menu:DiscordChannelSelect):
        await interaction.response.defer()
        self.wrem_channel = menu.values[0]
        
        self.load_add_war_reminder_menu_items()
        embed = await self.war_reminder_embed()
        embed2 = await self.add_war_reminder_embed()
        await interaction.edit_original_response(embeds=[embed,embed2],view=self)
    
    async def _callback_war_reminder_interval_modal(self,interaction:discord.Interaction,button:DiscordButton):
        interval_modal = DiscordModal(
            function=self._callback_war_reminder_set_interval,
            title=f"War Reminder Interval",
            )
        interval_modal.add_field(
            label="Reminder Interval (in hours, max: 24)",
            placeholder="Separate reminders with a blank space. Max of 24 hours.",
            required=True
            )
        await interaction.response.send_modal(interval_modal)

    async def _callback_war_reminder_set_interval(self,interaction:discord.Interaction,modal:DiscordModal):
        await interaction.response.defer()

        new_intervals = []
        for i in modal.children[0].value.split():
            try:
                interval = int(i)
            except:
                continue
            if interval > 0 and interval <= 24:
                new_intervals.append(interval)

        self.wrem_interval = sorted(set(list(new_intervals)),reverse=True)
        
        self.load_add_war_reminder_menu_items()
        embed = await self.war_reminder_embed()
        embed2 = await self.add_war_reminder_embed()
        await interaction.edit_original_response(embeds=[embed,embed2],view=self)
    
    async def _callback_save_war_reminder(self,interaction:discord.Interaction,button:DiscordButton):
        await interaction.response.defer()
        await EventReminder.create_war_reminder(
            clan=self.clan,
            channel=self.wrem_channel,
            war_types=self.wrem_type,
            interval=self.wrem_interval
            )        
        self.wrem_type = []
        self.wrem_interval = []
        self.wrem_channel = None

        await self._war_reminder_menu(interaction)
    
    async def _callback_delete_war_reminder_start(self,interaction:discord.Interaction,button:DiscordButton):
        await interaction.response.defer()        

        self.war_reminders = [r for r in await EventReminder.war_reminders_for_clan(self.clan) if r.guild_id == self.guild.id]
        self.load_delete_warreminder_menu_items()
        embed = await self.war_reminder_embed()
        await interaction.edit_original_response(embed=embed,view=self)
    
    async def _callback_delete_war_reminder(self,interaction:discord.Interaction,menu:DiscordSelectMenu):
        await interaction.response.defer()

        for item in menu.values:
            rem = await EventReminder.get_by_id(item)
            await rem.delete()
        
        self.war_reminders = [r for r in await EventReminder.war_reminders_for_clan(self.clan) if r.guild_id == self.guild.id]
        self.load_delete_warreminder_menu_items()
        embed = await self.war_reminder_embed()
        await interaction.edit_original_response(embed=embed,view=self)    
    
    ##################################################
    ### CLAN WAR REMINDER MENUS
    ##################################################
    def load_war_reminder_menu_items(self):
        self.clear_items()
        add_reminder_button = DiscordButton(
            function=self._callback_add_war_reminder_start,
            emoji=EmojisUI.ADD,
            label="Add War Reminder",
            row=0
            )
        delete_reminder_button = DiscordButton(
            function=self._callback_delete_war_reminder_start,
            emoji=EmojisUI.DELETE,
            label="Delete War Reminder",
            row=0
            )
        if len(self.war_reminders) >= 3:
            add_reminder_button.disabled = True
        if len(self.war_reminders) == 0:
            delete_reminder_button.disabled = True

        self.add_item(self.home_button())
        self.add_item(add_reminder_button)
        self.add_item(delete_reminder_button)
        self.add_item(self.close_button())
    
    def load_add_war_reminder_menu_items(self):
        self.clear_items()
        back_button = DiscordButton(
            function=self._callback_war_reminder_back,
            emoji=EmojisUI.GREEN_PREVIOUS,
            label="Back",
            row=0
            )
        save_reminder_button = DiscordButton(
            function=self._callback_save_war_reminder,
            emoji=EmojisUI.YES,
            label="Save Reminder",
            row=0
            )
        change_interval_button = DiscordButton(
            function=self._callback_war_reminder_interval_modal,
            label="Set/Change Reminder Interval",
            row=0
            )
        if not self.wrem_type:
            save_reminder_button.disabled = True
        if not self.wrem_channel:
            save_reminder_button.disabled = True
        if not self.wrem_interval:
            save_reminder_button.disabled = True

        type_options = [
            ('random','Classic Wars'),
            ('cwl','Clan War League'),
            ('friendly','Friendly Wars')
            ]
        select_options = [discord.SelectOption(
            label=text[1],
            description=f"In-Game Label: {text[0]}",
            value=text[0],
            default=text[0] in self.wrem_type
            )
            for text in type_options
            ]
        select_war_type = DiscordSelectMenu(
            function=self._callback_select_war_reminder_type,
            options=select_options,
            placeholder="Select the type of Wars to remind for.",
            min_values=1,
            max_values=3,
            row=1
            )
        select_reminder_channel = DiscordChannelSelect(
            function=self._callback_select_war_reminder_channel,
            channel_types=[discord.ChannelType.text,discord.ChannelType.public_thread],
            placeholder="Select the Channel where Reminders will be sent.",
            min_values=1,
            max_values=1,
            row=2
            )
        self.add_item(back_button)
        self.add_item(save_reminder_button)
        self.add_item(change_interval_button)
        self.add_item(select_war_type)
        self.add_item(select_reminder_channel)        
    
    def load_delete_warreminder_menu_items(self):
        self.clear_items()        
        back_button = DiscordButton(
            function=self._callback_war_reminder_back,
            emoji=EmojisUI.GREEN_PREVIOUS,
            label="Back",
            row=0
            )
        self.add_item(back_button)

        clan_war_reminder_options = [discord.SelectOption(
            label=f"War Reminder: {getattr(reminder.channel,'name','Unknown Channel')}",
            value=str(reminder._id),
            description=f"Type: {chat.humanize_list(reminder.sub_type)}"
            )
            for reminder in self.war_reminders
            ]
        
        if len(clan_war_reminder_options) > 0:            
            select_reminder_delete = DiscordSelectMenu(
                function=self._callback_delete_war_reminder,
                options=clan_war_reminder_options,
                placeholder="Select a Reminder to Delete.",
                min_values=1,
                max_values=len(clan_war_reminder_options),
                row=1
                )         
            self.add_item(select_reminder_delete)

    ##################################################
    ### CLAN WAR REMINDER EMBEDS
    ##################################################
    async def war_reminder_embed(self):
        embed = await clash_embed(
            context=self.ctx,
            title=f"War Reminders: {self.clan.title}",
            message=f"**Only Reminders for the current Server are displayed below.**"
                + f"\nAvailable Slots: **{3 - len(self.war_reminders)}** available (max 3)"
                + "\n\u200b",
            thumbnail=self.clan.badge
            )
        async for reminder in AsyncIter(self.war_reminders):
            if reminder.guild_id != self.guild.id:
                continue
            embed.add_field(
                name=f"{getattr(reminder.channel,'name','Unknown Channel')}",
                value=(f"Channel: {getattr(reminder.channel,'mention','')}\n" if reminder.channel else "")
                    + f"War Types: {chat.humanize_list(reminder.sub_type)}"
                    + f"\nInterval: {chat.humanize_list(sorted(reminder.reminder_interval,reverse=True))} hour(s)"
                    + f"\nCurrent: {chat.humanize_list(reminder.interval_tracker)} hour(s)",
                inline=False
                )        
        return embed

    async def add_war_reminder_embed(self):
        embed = await clash_embed(
            context=self.ctx,
            message=f"**You are adding a new Clan War Reminder.**"
                + f"\nReminders are sent for players who have available attacks to be used in the War."
                + f" Reminders can only be configured for a maximum of 24 hours."
                + f"\n\nSelect the War Type(s), a Channel, and the Reminder Intervals, then press **Save Reminder**."
                + f"\n\nSelected Type(s): {chat.humanize_list(self.wrem_type)}"
                + f"\nSelected Channel: {getattr(self.wrem_channel,'mention','Not Set')}"
                + f"\nSelected Interval(s):"
                )
        for i in self.wrem_interval:
            embed.description += f"\n- {i} hour(s)"
        return embed

    ####################################################################################################
    #####
    ##### RAID WEEKEND REMINDER MENU
    #####
    ####################################################################################################

    ##################################################
    ### RAID WEEKEND REMINDER FUNCTIONS
    ##################################################
    async def _raid_reminder_menu(self,interaction:discord.Interaction):
        if not interaction.response.is_done():
            await interaction.response.defer()

        self.raid_reminders = [r for r in await EventReminder.raid_reminders_for_clan(self.clan) if r.guild_id == self.guild.id]
        self.load_raid_reminder_menu_items()
        embed = await self.raid_reminder_embed()
        await interaction.edit_original_response(embed=embed,view=self)

    async def _callback_raid_reminder_back(self,interaction:discord.Interaction,button:DiscordButton):
        await interaction.response.defer()

        self.rrem_interval = []
        self.rrem_channel = None

        await self._raid_reminder_menu(interaction)
    
    async def _callback_add_raid_reminder_start(self,interaction:discord.Interaction,button:DiscordButton):
        await interaction.response.defer()

        self.rrem_interval = []
        self.rrem_channel = None

        self.raid_reminders = [r for r in await EventReminder.raid_reminders_for_clan(self.clan) if r.guild_id == self.guild.id]
        self.load_add_raid_reminder_menu_items()
        embed = await self.raid_reminder_embed()
        embed2 = await self.add_raid_reminder_embed()

        await interaction.edit_original_response(embeds=[embed,embed2],view=self)

    async def _callback_select_raid_reminder_channel(self,interaction:discord.Interaction,menu:DiscordChannelSelect):
        await interaction.response.defer()
        self.rrem_channel = menu.values[0]
        
        self.load_add_raid_reminder_menu_items()        
        embed = await self.raid_reminder_embed()
        embed2 = await self.add_raid_reminder_embed()
        await interaction.edit_original_response(embeds=[embed,embed2],view=self)

    async def _callback_raid_reminder_interval_modal(self,interaction:discord.Interaction,button:DiscordButton):
        interval_modal = DiscordModal(
            function=self._callback_raid_reminder_set_interval,
            title=f"Raid Reminder Interval",
            )
        interval_modal.add_field(
            label="Reminder Interval (in hours, max: 70)",
            placeholder="Separate reminders with a blank space. Max of 70 hours.",
            required=True
            )
        await interaction.response.send_modal(interval_modal)
    
    async def _callback_raid_reminder_set_interval(self,interaction:discord.Interaction,modal:DiscordModal):
        await interaction.response.defer()

        new_intervals = []
        for i in modal.children[0].value.split():
            try:
                interval = int(i)
            except:
                continue
            if interval > 0 and interval <= 70:
                new_intervals.append(interval)

        self.rrem_interval = sorted(set(list(new_intervals)),reverse=True)
        
        self.load_add_raid_reminder_menu_items()        
        embed = await self.raid_reminder_embed()
        embed2 = await self.add_raid_reminder_embed()
        await interaction.edit_original_response(embeds=[embed,embed2],view=self)
    
    async def _callback_save_raid_reminder(self,interaction:discord.Interaction,button:DiscordButton):
        await interaction.response.defer()
        await EventReminder.create_raid_reminder(
            clan=self.clan,
            channel=self.rrem_channel,
            interval=self.rrem_interval
            )        
        self.rrem_interval = []
        self.rrem_channel = None

        await self._raid_reminder_menu(interaction)
    
    async def _callback_delete_raid_reminder_start(self,interaction:discord.Interaction,button:DiscordButton):
        await interaction.response.defer()        

        self.raid_reminders = [r for r in await EventReminder.raid_reminders_for_clan(self.clan) if r.guild_id == self.guild.id]
        self.load_delete_raidreminder_menu_items()
        embed = await self.raid_reminder_embed()
        await interaction.edit_original_response(embed=embed,view=self)
    
    async def _callback_delete_raid_reminder(self,interaction:discord.Interaction,menu:DiscordSelectMenu):
        await interaction.response.defer()

        for item in menu.values:
            rem = await EventReminder.get_by_id(item)
            await rem.delete()
        
        self.raid_reminders = [r for r in await EventReminder.raid_reminders_for_clan(self.clan) if r.guild_id == self.guild.id]
        self.load_delete_raidreminder_menu_items()
        embed = await self.raid_reminder_embed()
        await interaction.edit_original_response(embed=embed,view=self)

    ##################################################
    ### RAID WEEKEND REMINDER MENU
    ##################################################    
    def load_raid_reminder_menu_items(self):
        self.clear_items()
        add_reminder_button = DiscordButton(
            function=self._callback_add_raid_reminder_start,
            emoji=EmojisUI.ADD,
            label="Add Raid Reminder",
            row=0
            )
        delete_reminder_button = DiscordButton(
            function=self._callback_delete_raid_reminder_start,
            emoji=EmojisUI.DELETE,
            label="Delete Raid Reminder",
            row=0
            )
        if len(self.raid_reminders) >= 3:
            add_reminder_button.disabled = True
        if len(self.raid_reminders) == 0:
            delete_reminder_button.disabled = True
        self.add_item(self.home_button())
        
        self.add_item(add_reminder_button)
        self.add_item(delete_reminder_button)
        self.add_item(self.close_button())
    
    def load_add_raid_reminder_menu_items(self):
        self.clear_items()
        back_button = DiscordButton(
            function=self._callback_raid_reminder_back,
            emoji=EmojisUI.GREEN_PREVIOUS,
            label="Back",
            row=0
            )
        save_reminder_button = DiscordButton(
            function=self._callback_save_raid_reminder,
            emoji=EmojisUI.YES,
            label="Save Reminder",
            row=0
            )
        change_interval_button = DiscordButton(
            function=self._callback_raid_reminder_interval_modal,
            label="Set/Change Reminder Interval",
            row=0
            )
        
        if not self.rrem_channel:
            save_reminder_button.disabled = True
        if not self.rrem_interval:
            save_reminder_button.disabled = True

        select_reminder_channel = DiscordChannelSelect(
            function=self._callback_select_raid_reminder_channel,
            channel_types=[discord.ChannelType.text,discord.ChannelType.public_thread],
            placeholder="Select the Channel where Reminders will be sent.",
            min_values=1,
            max_values=1,
            row=2
            )
        self.add_item(back_button)
        self.add_item(save_reminder_button)
        self.add_item(change_interval_button)
        self.add_item(select_reminder_channel)        
    
    def load_delete_raidreminder_menu_items(self):
        self.clear_items()        
        back_button = DiscordButton(
            function=self._callback_raid_reminder_back,
            emoji=EmojisUI.GREEN_PREVIOUS,
            label="Back",
            row=0
            )
        self.add_item(back_button)

        clan_raid_reminder_options = [discord.SelectOption(
            label=f"Raid Reminder: {getattr(reminder.channel,'name','Unknown Channel')}",
            value=str(reminder._id),
            )
            for reminder in self.raid_reminders
            ]
        if len(clan_raid_reminder_options) > 0:            
            select_reminder_delete = DiscordSelectMenu(
                function=self._callback_delete_raid_reminder,
                options=clan_raid_reminder_options,
                placeholder="Select a Reminder to Delete.",
                min_values=1,
                max_values=len(clan_raid_reminder_options),
                row=1
                )         
            self.add_item(select_reminder_delete)
    
    ##################################################
    ### RAID WEEKEND REMINDER EMBEDS
    ##################################################
    async def raid_reminder_embed(self):
        embed = await clash_embed(
            context=self.ctx,
            title=f"Raid Reminders: {self.clan.title}",
            message=f"**Only Reminders for the current Server are displayed below.**"
                + f"\nAvailable Slots: **{3 - len(self.raid_reminders)}** available (max 3)"
                + "\n\u200b",
            thumbnail=self.clan.badge
            )
        async for reminder in AsyncIter(self.raid_reminders):
            if reminder.guild_id != self.guild.id:
                continue
            embed.add_field(
                name=f"{getattr(reminder.channel,'name','Unknown Channel')}",
                value=(f"Channel: {getattr(reminder.channel,'mention','')}\n" if reminder.channel else "")
                    + f"Interval: {chat.humanize_list(reminder.reminder_interval)} hour(s)"
                    + f"\nCurrent: {chat.humanize_list(reminder.interval_tracker)} hour(s)",
                inline=False
                )        
        return embed

    async def add_raid_reminder_embed(self):
        def convert_hours_to_days(hours:int):
            if hours < 24:
                return f"{hours} hour(s)"
            elif hours == 24:
                return f"1 day"
            else:
                return f"{hours//24} day(s) and {hours%24} hour(s)"
            
        embed = await clash_embed(
            context=self.ctx,
            message=f"**You are adding a new Capital Raid Weekend Reminder.**"
                + f"\nReminders are sent for players who have started their Raid Weekends, but not used all their attacks."
                + f" Reminders can only be configured for up to 70 hours."
                + f"\n\nSelect the Channel and the Reminder Intervals, then press **Save Reminder**."
                + f"\n\nSelected Channel: {getattr(self.rrem_channel,'mention','Not Set')}"
                + f"\nSelected Interval(s): "
                )
        for i in self.rrem_interval:
            embed.description += f"\n- {convert_hours_to_days(i)}"
        return embed