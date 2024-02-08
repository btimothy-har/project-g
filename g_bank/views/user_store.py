import discord
import random
import pendulum

from typing import *
from functools import cached_property

from redbot.core import commands, bank
from coc_main.api_client import BotClashClient
from coc_main.utils.components import DefaultView, DiscordButton, DiscordSelectMenu, clash_embed
from coc_main.utils.constants.ui_emojis import EmojisUI

from ..objects.item import ShopItem
from ..objects.inventory import UserInventory, InventoryItem

bot_client = BotClashClient()

class UserStore(DefaultView):
    def __init__(self,
        context:Union[commands.Context,discord.Interaction]):
        self.current_category = None
        self.current_item = None
        super().__init__(context=context,timeout=300)
    
    @cached_property
    def store_categories(self):
        cat = sorted(list(set([i.category for i in self.store_items])))
        if 'Uncategorized' in cat:
            cat.remove('Uncategorized')
        cat.append('Uncategorized')
        return cat

    ##################################################
    ### VIEW COMPONENTS
    ##################################################
    @property
    def category_select(self):
        if len(self.store_categories) <= 2:
            return None
        
        select_options = [discord.SelectOption(
            default=True if cat == self.current_category else False,
            label=cat,
            value=cat)
            for cat in self.store_categories if len([i for i in self.store_items if i.category == cat]) > 0
            ]
        item_select = DiscordSelectMenu(
            function=self._view_category_callback,
            placeholder="Select a Category to view.",
            options=select_options,
            min_values=1,
            max_values=1,
            row=1
            )        
        return item_select

    @property
    def item_select(self):
        if len(self.store_items) == 0:
            return None
        
        items = sorted(self.store_items,key=lambda x: x.price)
        if self.current_category:
            select_items = [i for i in items if i.category == self.current_category][:25]
        else:
            select_items = [i for i in items if i.type][:25]

        select_options = [discord.SelectOption(
            default=True if item.id == getattr(self.current_item,'id',None) else False,
            label=f"{item.name}",
            value=item.id,
            description=item.description)
            for item in select_items
            ]
        item_select = DiscordSelectMenu(
            function=self._display_item_detail,
            placeholder="Select an Item to view.",
            options=select_options,
            min_values=1,
            max_values=1,
            row=2
            )        
        return item_select

    @property
    def home_button(self):
        return DiscordButton(
            function=self._main_menu,
            label="Home",
            emoji=EmojisUI.HOME,
            style=discord.ButtonStyle.blurple,
            row=0
            )
    
    @property
    def close_button(self):
        return DiscordButton(
            function=self._close,
            label="Exit",
            emoji=EmojisUI.EXIT,
            style=discord.ButtonStyle.red,
            row=0
            )
    
    ##################################################
    ### START / STOP CALL
    ##################################################
    async def start(self):
        guild_items = await ShopItem.get_by_guild(self.guild.id)
        self.store_items = [i for i in guild_items if i.show_in_store]

        self.is_active = True
        await self._main_menu(self.ctx)
    
    async def _close(self,interaction:discord.Interaction,button:DiscordButton):
        self.stop_menu()
        embed = await clash_embed(
            context=self.ctx,
            message=f"**Store Closed**")
        await interaction.response.edit_message(embed=embed,view=None,delete_after=60)
    
    ##################################################
    ### MAIN MENU
    ##################################################
    async def _main_menu(self,interaction:Union[discord.Interaction,commands.Context],button:Optional[DiscordButton]=None):
        
        if isinstance(interaction,discord.Interaction):
            if not interaction.response.is_done():
                await interaction.response.defer()
        
        self.current_category = None
        self.current_item = None

        self.clear_items()
        self.add_item(self.home_button)
        self.add_item(self.close_button)

        if len(self.store_categories) > 2:
            self.add_item(self.category_select)
        
        elif len(self.store_items) >= 1:
            self.add_item(self.item_select)

        embed = await self.main_menu_embed()
        if isinstance(interaction,discord.Interaction):
            await interaction.edit_original_response(embed=embed,view=self)   
        else:
            await interaction.reply(embed=embed,view=self)
    
    async def main_menu_embed(self):
        bal = await bank.get_balance(self.user)

        if len(self.store_items) < 1:
            embed = await clash_embed(
                context=self.ctx,
                title=f"**The Guild Store: {self.guild.name}**",
                message=f"### **Welcome to the Guild Store!**"
                    + f"\nYou have: {bal:,} {await bank.get_currency_name()}"
                    + "\n\nThere are no items available in the Store at this time.",
                thumbnail=self.guild.icon.url
                )        
        elif len(self.store_categories) > 2:
            embed = await clash_embed(
                context=self.ctx,
                title=f"**The Guild Store: {self.guild.name}**",
                message=f"### **Welcome to the Guild Store!**"
                    + f"\nYou have: {bal:,} {await bank.get_currency_name()}"
                    + f"\n\nTo start, select a category from the category drop-down below. This Store has the following categories:\n",
                thumbnail=self.guild.icon.url
                )
            for cat in self.store_categories:
                embed.description += f"\n- **{cat}**: {len([i for i in self.store_items if i.category == cat])} items"
        else:
            embed = await clash_embed(
                context=self.ctx,
                title=f"**The Guild Store: {self.guild.name}**",
                message=f"### **Welcome to the Guild Store!**"
                    + f"\nYou have: {bal:,} {await bank.get_currency_name()}"
                    + f"\n\nTo view or purchase an item, select one from the drop-down below.\n",
                thumbnail=self.guild.icon.url
                )

        # + "\n\n**Standard** items are added to your inventory on purchase. Check your inventory with `/inventory`."
        #         + "\n\n**Role** items grant you the associated role on purchase. If you already have the role, this might remove the role instead."
        #         + "\n\n**Random** items contain a pre-selected list of items. Upon purchase, you get a randomly selected item from the list!"
        return embed

    ##################################################
    ### CATEGORY MAIN
    ##################################################
    async def _view_category_callback(self,interaction:discord.Interaction,menu:DiscordSelectMenu):
        await interaction.response.defer()

        self.current_category = menu.values[0]
        self.current_item = None

        self.clear_items()
        self.add_item(self.home_button)
        self.add_item(self.close_button)

        if len(self.store_categories) > 2:
            self.add_item(self.category_select)

        self.add_item(self.item_select)

        embed = await self.category_main_embed()
        await interaction.edit_original_response(embed=embed,view=self)
    
    async def category_main_embed(self):
        bal = await bank.get_balance(self.user)

        embed = await clash_embed(
            context=self.ctx,
            title=f"**The Guild Store: {self.guild.name}**",
            message=f"### **Currently Viewing: {self.current_category}**"
                + f"\nYou have: {bal:,} {await bank.get_currency_name()}"
                + f"\n\nTo view or purchase an item, select one from the drop-down below."
                + "\n\n**Items in Category**",
            thumbnail=self.guild.icon.url
            )
        
        cat_items = [i for i in self.store_items if i.category == self.current_category][:25]
        
        for item in sorted(cat_items,key=lambda x: x.price):
            embed.description += f"\n\n**{item.name}**: {item.price:,} {await bank.get_currency_name()}"
            embed.description += f"\n{item.description}"

        # + "\n\n**Standard** items are added to your inventory on purchase. Check your inventory with `/inventory`."
        #         + "\n\n**Role** items grant you the associated role on purchase. If you already have the role, this might remove the role instead."
        #         + "\n\n**Random** items contain a pre-selected list of items. Upon purchase, you get a randomly selected item from the list!"
        return embed
    
    ##################################################
    ### SHOW ITEM DETAIL
    ##################################################
    async def _display_item_detail(self,interaction:discord.Interaction,menu:Optional[DiscordSelectMenu]=None):
        if not interaction.response.is_done():
            await interaction.response.defer()
        
        if menu:
            self.current_item = await ShopItem.get_by_id(menu.values[0])
            self.current_item._randomize_stock()

        user = self.guild.get_member(interaction.user.id)

        purchase_button = self.purchase_button
        inventory = await UserInventory(interaction.user)

        if inventory.has_item(self.current_item) and (self.current_item.type in ['cash'] or self.current_item.subscription):
            if self.current_item.type in ['cash']:
                self.current_item._stock = 0

            purchase_button.disabled = True
            purchase_button.label = f"You can only have 1 of this item."
            purchase_button.style = discord.ButtonStyle.grey

        if not purchase_button.disabled:
            can_buy = self.current_item.can_i_buy(self.guild.get_member(interaction.user.id))
            can_spend = await bank.can_spend(user,self.current_item.price)
            
            last_purchase = await InventoryItem.find_last_purchase(user,self.current_item) if self.current_item.type in ['cash'] else None
            within_cooldown = last_purchase and pendulum.now() <= last_purchase.timestamp.add(hours=24)

            if not can_buy or not can_spend or within_cooldown:
                purchase_button.disabled = True
                if not can_spend:
                    purchase_button.label = f"You cannot afford this item."

                elif self.current_item.required_role and self.current_item.required_role.id not in [r.id for r in user.roles]:
                    purchase_button.label = f"You are missing a Required Role for this Item."

                elif isinstance(self.current_item.stock,int) and self.current_item.stock < 1:
                    purchase_button.label = "This item is out of stock."
                
                elif within_cooldown:
                    purchase_button.label = "This item is on cooldown."

                else:
                    purchase_button.label = "You cannot purchase this item."
                purchase_button.style = discord.ButtonStyle.grey

        self.clear_items()
        self.add_item(purchase_button)
        self.add_item(self.home_button)
        self.add_item(self.close_button)

        if len(self.store_categories) > 2:
            self.add_item(self.category_select)
        self.add_item(self.item_select)
        item_embed = await self.get_item_embed()
        await interaction.edit_original_response(embed=item_embed,view=self)
    
    async def _purchase_item(self,interaction:discord.Interaction,button:DiscordButton):
        await interaction.response.defer()
        currency = await bank.get_currency_name()

        item = self.current_item

        if not item.can_i_buy(self.guild.get_member(interaction.user.id)) or not await bank.can_spend(self.guild.get_member(interaction.user.id),item.price):
            embed = await clash_embed(
                context=self.ctx,
                message=f"You cannot purchase **{item.name}**.",
                success=False
                )
            return await interaction.followup.send(embed=embed,ephemeral=True)
        
        user_inv = await UserInventory(interaction.user)
        buy_item = await user_inv.purchase_item(item)

        purchase_msg = f"Congratulations! You spent {item.price} {currency} to purchase 1x **{item.name}**."

        if self.current_item.type == 'random':
            purchase_msg += f"\n\nYou received 1x **{buy_item.name}** from {item.name}."
        
        if buy_item.type == 'role':
            if not buy_item.bidirectional_role:
                purchase_msg += f"\n\nYou received the {buy_item.assigns_role.mention} role."
            else:
                if buy_item.assigns_role.id not in [r.id for r in self.guild.get_member(interaction.user.id).roles]:
                    purchase_msg += f"\n\nThe {buy_item.assigns_role.mention} role was removed."
                else:
                    purchase_msg += f"\n\nYou received the {buy_item.assigns_role.mention} role."
                    
        elif buy_item.type in ['basic','cash']:
            if buy_item.buy_message and len(buy_item.buy_message) > 0:
                purchase_msg += f"\n\nCheck your DMs for additional information."
            else:
                purchase_msg += f"\n\n1x **{buy_item.name}** was added to your inventory."
        
        embed = await clash_embed(
            context=self.ctx,
            message=purchase_msg,
            success=True
            )
                
        await interaction.followup.send(embed=embed,ephemeral=True)
        await self._display_item_detail(interaction)

    async def get_item_embed(self):
        bal = await bank.get_balance(self.user)
        currency = await bank.get_currency_name()
        
        item_embed = await clash_embed(
            context=self.ctx,
            title=f"**The Guild Store: {self.guild.name}**",
            message=f"**You have: {bal:,} {currency}**\n"
                + f"```{self.current_item.name}```"
                )
        
        item_embed.add_field(
            name="Price",
            value=f"{self.current_item.price:,} {currency}",
            inline=True
            )
        item_embed.add_field(
            name="Available Stock",
            value=f"{self.current_item.stock if self.current_item.stock != -1 else 'Infinite'}",
            inline=True
            )
        item_embed.add_field(
            name="Expires",
            value=f"{self.current_item.subscription_duration} day(s)" if self.current_item.subscription else "Never",
            inline=True
            )
        item_embed.add_field(
            name="Category",
            value=f"{self.current_item.category}",
            inline=True
            )      
        item_embed.add_field(
            name="Requires",
            value=f"{self.current_item.required_role.mention if self.current_item.required_role else 'None'}",
            inline=True
            )
          
        item_embed.add_field(
            name="Description",
            value=f"{self.current_item.description}",
            inline=False
            )        
                
        if self.current_item.type in ['basic','cash']:
            item_embed.add_field(
                name=f"{self.current_item.type.capitalize()} Item",
                value=f"When purchased, this item will be added to your inventory. Check your inventory with `/inventory`.",
                inline=False
                )
        
        if self.current_item.type in ['role']:            
            item_embed.add_field(
                name=f"{self.current_item.type.capitalize()} Item",
                value=f"When purchased, this item will assign you the {self.current_item.assigns_role.mention} role. "
                    + ("If you already have the role, it will be removed." if self.current_item.bidirectional_role else "You can't purchase this item if you already have the role."),
                inline=False
                )
        
        if self.current_item.type in ['random']:
            item_embed.add_field(
                name=f"{self.current_item.type.capitalize()} Item",
                value=f"When purchased, this item will give you a random item from the following list:"
                    + '\n- '
                    + '\n- '.join([str(i) for i in self.current_item.grants_items]),
                inline=False
                )
        return item_embed
    
    @property
    def purchase_button(self):
        return DiscordButton(
            function=self._purchase_item,
            label="Purchase Item",
            style=discord.ButtonStyle.green,
            row=0
            )
