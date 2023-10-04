import discord

from typing import *
from redbot.core import commands

from ..objects.item import ShopItem

from coc_data.utilities.components import *
from coc_data.constants.ui_emojis import *

class StoreManager(DefaultView):
    def __init__(self,
        context:Union[commands.Context,discord.Interaction]):

        super().__init__(context=context,timeout=300)
    
    @property
    def guild_items(self):
        return ShopItem.get_by_guild(self.guild.id)

    ##################################################
    ### VIEW COMPONENTS
    ##################################################
    @property
    def main_menu_button(self):
        return DiscordButton(
            function=self._main_menu,
            #label="Main Menu",
            emoji=EmojisUI.HOME,
            style=discord.ButtonStyle.blurple
            )    
    @property
    def close_button(self):
        return DiscordButton(
            function=self._close,
            #label="Close",
            emoji=EmojisUI.EXIT,
            style=discord.ButtonStyle.red,
            row=0
            )
    
    ##################################################
    ### START / STOP CALL
    ##################################################
    async def start(self):
        self.is_active = True
        await self._main_menu(self.ctx)        
    
    ##################################################
    ### MAIN MENU
    ##################################################
    async def _main_menu(self,interaction:discord.Interaction,button:Optional[DiscordButton]=None):
        if not interaction.response.is_done():
            await interaction.response.defer()

        self.clear_items()
        self.add_item(self.main_menu_button)
        self.add_item(self.add_item_button)
        self.add_item(self.delete_item_button)
        self.add_item(self.close_button)

        embed = await self.main_menu_embed()
        await interaction.edit_original_response(embed=embed,view=self)   
    
    async def main_menu_embed(self):
        embed = await clash_embed(
            context=self.ctx,
            title=f"**Store Manager: {self.guild.name}**"
            )
        embed.add_field(
            name=f"**Overview**",
            value=f"Total Items: `{len(self.guild_items):>3}`"
                + f"\nIn Store: `{len([i for i in self.guild_items if i.show_in_store]):>3}`"
                + f"\nStock Out: `{len([i for i in self.guild_items if i.stock == 0]):>3}`"
                + "\n\u200b",
            inline=False)
        embed.add_field(
            name=f"**Items by Type**",
            value=f"Basic: `{len([i for i in self.guild_items if i.type == 'basic']):>3}`"
                + f"\nRole: `{len([i for i in self.guild_items if i.type == 'role']):>3}`"
                + f"\nRandom: `{len([i for i in self.guild_items if i.type == 'random']):>3}`"
                + f"\nCash: `{len([i for i in self.guild_items if i.type == 'cash']):>3}`"
                + "\n\u200b",
            inline=False)
        embed.add_field(
            name=f"**Needing Restock**",
            value="\n".join([f"{str(i)}" for i in self.guild_items if i.stock == 0])
                + "\n\u200b",
            inline=False)
        return embed
    
    @property
    def add_item_button(self):
        return DiscordButton(
            function=self._add_item,
            label="Add Item",
            style=discord.ButtonStyle.grey,
            )
    @property
    def delete_item_button(self):
        return DiscordButton(
            function=self._delete_item,
            label="Delete Item",
            style=discord.ButtonStyle.grey,
            )
    @property
    def hide_item_button(self):
        return DiscordButton(
            function=self._hide_item,
            label="Hide Item",
            style=discord.ButtonStyle.grey,
            )
    ##################################################
    ### ADD ITEM
    ##################################################
    async def _add_item(self,interaction:discord.Interaction,button:DiscordButton):
        if not interaction.response.is_done():
            await interaction.response.defer()
        
        self.new_item_type = None

        self.clear_items()
        self.add_item(self.main_menu_button)
        self.add_item(self.item_type_basic_button)
        self.add_item(self.item_type_role_button)
        if len(self.guild_items) > 1:
            self.add_item(self.item_type_random_button)
        if self.user.id in self.bot.owner_ids:
            self.add_item(self.item_type_cash_button)
        self.add_item(self.close_button)

        embed = await self.main_menu_embed()
        await interaction.edit_original_response(embed=embed,view=self)
    
    async def _item_type_select(self,interaction:discord.Interaction,button:DiscordButton):
        self.new_item_type = button.reference
        await interaction.response.send_modal(self.create_item_modal)
    
    async def _create_item(self,interaction:discord.Interaction,modal:DiscordModal):
        await interaction.response.defer()

        self.new_item_name = modal.children[0].value
        self.new_item_price = int(modal.children[1].value)
        self.new_item_stock = int(modal.children[2].value)
        self.new_item_description = modal.children[3].value

        embed = await self.add_item_creation_embed()

        if self.new_item_type == "basic":
            await self._create_basic_item(interaction)

        elif self.new_item_type == "role":
            role_select = DiscordRoleSelect(
                function=self._create_role_item,
                placeholder="Select a Role to assign...",
                required=True
                )
            self.clear_items()
            self.add_item(role_select)
            self.add_item(self.close_button)
            await interaction.edit_original_response(embed=embed,view=self)

        elif self.new_item_type == 'random':
            select_options = [discord.SelectOption(
                label=f"{item}",
                value=item.id,
                description=item.description[:30],)
                for item in self.guild_items
                ]
            item_select = DiscordSelectMenu(
                function=self._create_random_item,
                placeholder="Select 2 or more Items to be included.",
                required=True,
                min_values=2,
                max_values=len(select_options),
                )
            self.clear_items()
            self.add_item(item_select)
            self.add_item(self.close_button)
            await interaction.edit_original_response(embed=embed,view=self)

        elif self.new_item_type == 'cash':
            self.clear_items()
            self.add_item(self.close_button)
    
    async def 
    
    async def add_item_embed(self):
        embed = await clash_embed(
            context=self.ctx,
            title=f"**Store Manager: {self.guild.name}**",
            message="```**Add Item**```"
                + "### **Select an Item Type to add below.**"
                + f"\n\n**Basic** items are generic items. When purchased, they are added to the user's inventory. They can be used for anything."
                + f"\n\n**Role** items assign a designated role to a user when purchased."
                + f"\n\n**Random** items contain a pre-selected list of items, and provide one at random when purchased. Probability is determined by the price of the respective items."
                )
        return embed

    async def add_item_creation_embed(self):
        embed = await clash_embed(
            context=self.ctx,
            title=f"**Store Manager: {self.guild.name}**",
            message="```**Add Item**```"
                + "### **You are adding...**"
                + f"\n\n**Type**: `{self.new_item_type}`"
                + f"\n**Name**: `{self.new_item_name}`"
                + f"\n**Price**: `{self.new_item_price}`"
                + f"\n**Stock**: `{self.new_item_stock if self.new_item_stock != -1 else 'Infinite'}`"
                + f"\n**Description**: `{self.new_item_description}`"
                )
        return embed    
    
    @property
    def create_item_modal(self):
        m = DiscordModal(
            function=self._create_item,
            title=f"Create Item",
            )
        name_field = discord.ui.TextInput(
            label="Name",
            placeholder="Name of this Item (max 30 characters).",
            max_length=30,
            style=discord.TextStyle.short,
            required=True
            )
        price_field = discord.ui.TextInput(
            label="Item Price",
            placeholder="Price of this Item (max 9999).",
            style=discord.TextStyle.short,
            max_length=4,
            required=True
            )
        stock_field = discord.ui.TextInput(
            label="Item Stock",
            placeholder="Initial stock of this Item (max 99). -1 for unlimited.",
            style=discord.TextStyle.short,
            max_length=2,
            required=True
            )        
        description_field = discord.ui.TextInput(
            label="Description",
            placeholder="Optional description of this Item (max 100 characters).",
            max_length=100,
            style=discord.TextStyle.short,
            required=False
            )
        m.add_item(name_field)
        m.add_item(price_field)
        m.add_item(stock_field)
        m.add_item(description_field)
        return m
    
    @property
    def item_type_basic_button(self):
        return DiscordButton(
            function=self._item_type_select,
            label="Basic",
            style=discord.ButtonStyle.grey,
            reference="basic",
            )
    @property
    def item_type_role_button(self):
        return DiscordButton(
            function=self._item_type_select,
            label="Role",
            style=discord.ButtonStyle.grey,
            reference="role",
            )
    @property
    def item_type_random_button(self):
        return DiscordButton(
            function=self._item_type_select,
            label="Random",
            style=discord.ButtonStyle.grey,
            reference="random",
            )
    @property
    def item_type_cash_button(self):
        return DiscordButton(
            function=self._item_type_select,
            label="Cash",
            style=discord.ButtonStyle.grey,
            reference="cash",
            )
    
    ##################################################
    ### BUTTON CALLBACKS
    ##################################################
    async def _close(self,interaction:discord.Interaction,button:DiscordButton):
        self.stop_menu()
        embed = await clash_embed(
            context=self.ctx,
            message=f"**CWL Setup Menu closed.**")
        await interaction.response.edit_message(embed=embed,view=None)
    
    async def _open_signups(self,interaction:discord.Interaction,button:DiscordButton):
        await interaction.response.defer()
        
        self.season.cwl_signup_status = True
        embed = await self.get_embed()
        await interaction.edit_original_response(embed=embed,view=self)
    
    async def _close_signups(self,interaction:discord.Interaction,button:DiscordButton):
        await interaction.response.defer()        
        self.season.cwl_signup_status = False
        embed = await self.get_embed()
        await interaction.edit_original_response(embed=embed,view=self)
    
    async def _callback_clan_select(self,interaction:discord.Interaction,select:DiscordSelectMenu):
        await interaction.response.defer()

        for clan in WarLeagueClan.participating_by_season(self.season):
            if clan.tag not in select.values:
                clan.is_participating = False
        
        for clan_tag in select.values:
            clan = await aClan.create(clan_tag)
            clan.cwl_season(self.season).is_participating = True
            
        embed = await self.get_embed()
        self.build_clan_selector()
        await interaction.edit_original_response(embed=embed,view=self)
    
    async def get_embed(self):
        current_signups = WarLeaguePlayer.signups_by_season(self.season)

        all_th = sorted(list(set([p.town_hall for p in current_signups])),reverse=True)

        embed = await clash_embed(
            context=self.ctx,
            title=f"CWL Season Setup: {self.season.description}",
            message=("```**Season Locked**```" if self.season.cwl_signup_lock else "")
                + f"**CWL Starts**: <t:{self.season.cwl_start.int_timestamp}:F>"
                + f"\n**CWL Ends**: <t:{self.season.cwl_end.int_timestamp}:F>"
                + "\n\u200b",
            )        
        embed.add_field(
            name=f"**Player Registration**: `{'OPEN' if self.season.cwl_signup_status else 'CLOSED'}`",
            value=f"**Total:** `{len(current_signups):>3}`"
                + f"\n**Rostered:** `{len([p for p in current_signups if p.roster_clan]):>3}`"
                + f"\u3000**Unrostered:** `{len([p for p in current_signups if not p.roster_clan]):>3}`"
                + '\n'
                + '\u3000'.join([f"{EmojisTownHall.get(th)} `{len([p for p in current_signups if p.town_hall == th]):^3}`" for th in all_th[:5]])
                + ('\n' if len(all_th) > 5 else "")
                + ('\u3000'.join([f"{EmojisTownHall.get(th)} `{len([p for p in current_signups if p.town_hall == th]):^3}`" for th in all_th[5:10]]) if len(all_th) > 5 else "")
                + ('\n' if len(all_th) > 10 else "")
                + ('\u3000'.join([f"{EmojisTownHall.get(th)} `{len([p for p in current_signups if p.town_hall == th]):^3}`" for th in all_th[10:]]) if len(all_th) > 10 else "")
                + '\n> '
                + '\n> '.join([
                    f"{CWLLeagueGroups.get_description(i)}: `{len([p for p in current_signups if p.league_group == i]):>3}`"
                    for i in [1,2,9,99]
                    ])
                + "\n\u200b",
            inline=False
            )
        participating_clans = WarLeagueClan.participating_by_season(self.season)
        for cwl_clan in participating_clans:
            embed.add_field(
                name=f"{EmojisLeagues.get(cwl_clan.clan.war_league.name)} {cwl_clan.clan}",
                value=f"# in Roster: {len(cwl_clan.participants)} (Roster {'Open' if cwl_clan.roster_open else 'Finalized'})"
                    + (f"\nIn War: Round {len(cwl_clan.league_group.rounds)-1} / {cwl_clan.league_group.number_of_rounds}\nPreparation: Round {len(cwl_clan.league_group.rounds)} / {cwl_clan.league_group.number_of_rounds}" if cwl_clan.league_group else "\nCWL Not Started" if self.season.cwl_signup_lock else "")
                    + (f"\nMaster Roster: {len(cwl_clan.master_roster)}" if cwl_clan.league_group else "")
                    + "\n\u200b",
                inline=False
                )
        return embed

    def build_clan_selector(self):
        if self.clan_selector:
            self.remove_item(self.clan_selector)
            self.clan_selector = None

        if not self.season.cwl_signup_lock:
            clan_options = [discord.SelectOption(
                label=str(clan),
                value=clan.tag,
                emoji=EmojisLeagues.get(clan.war_league.name),
                description=f"Level {clan.level} | {clan.war_league.name}",
                default=clan.cwl_season(self.season).is_participating)
                for clan in self.client.cog.get_cwl_clans()]
            
            self.clan_selector = DiscordSelectMenu(
                function=self._callback_clan_select,
                options=clan_options,
                placeholder="Select one or more clan(s) for CWL...",
                min_values=1,
                max_values=len(clan_options)
                )        
            self.clan_selector.disabled = self.season.cwl_signup_lock
            self.add_item(self.clan_selector)