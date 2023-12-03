import discord
import random
import asyncio

from typing import *

from redbot.core import commands
from redbot.core.utils import AsyncIter

from ..objects.item import ShopItem, NewShopItem

from coc_main.utils.components import DefaultView, DiscordButton, DiscordSelectMenu, DiscordModal, DiscordRoleSelect, clash_embed
from coc_main.utils.constants.ui_emojis import EmojisUI

class AddItem(DefaultView):
    def __init__(self,context:Union[commands.Context,discord.Interaction]):

        self.guild_items = []
        super().__init__(context=context,timeout=300)

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
        self.add_item(self.add_basic_item_button)
        self.add_item(self.add_random_item_button)
        
        if self.user.id in self.bot.owner_ids:
            self.add_item(self.add_cash_item_button)
        
        self.add_item(self.add_roleadd_item_button)
        self.add_item(self.add_roleex_item_button)
        self.add_item(self.add_rolebi_item_button)

        embed = await self.start_embed()

        if isinstance(self.ctx,discord.Interaction):
            await self.ctx.edit_original_response(embed=embed,view=self)
        else:
            await self.ctx.reply(embed=embed,view=self)
    
    async def _close(self,interaction:discord.Interaction,button:DiscordButton):
        self.stop_menu()
        embed = await clash_embed(
            context=self.ctx,
            message=f"**Store Manager Closed**")
        await interaction.response.edit_message(embed=embed,view=None,delete_after=60)

    async def start_embed(self):
        embed = await clash_embed(
            context=self.ctx,
            message="Choose an item type that you wish to create.",
            show_author=False
            )
        embed.add_field(
            name=f"**Basic**",
            value="Adds an item to a User's Inventory on purchase.",
            inline=True
            )
        embed.add_field(
            name=f"**Random**",
            value="Provides a random item from selected list on purchase.",
            inline=True
            )
        embed.add_field(
            name=f"**Cash**",
            value="Special Guild-only item.",
            inline=True
            )
        embed.add_field(
            name=f"**Role (Add-Only)**",
            value="Assigns a Role on purchase.",
            inline=True
            )
        embed.add_field(
            name=f"**Role (Exclusive)**",
            value="Assigns a Role on purchase, and removes any other Roles granted by items in the same category.",
            inline=True
            )
        embed.add_field(
            name=f"**Role (Bi-Directional)**",
            value="Assigns a Role on purchase, or removes it if the user already has the role.",
            inline=True
            )
        return embed

    @property
    def start_over_add(self):
        return DiscordButton(
            function=self._add_item_start,
            label="Start Over",
            emoji=EmojisUI.REFRESH,
            style=discord.ButtonStyle.grey,
            reference='startover'
            )
    
    @property
    def add_basic_item_button(self):
        return DiscordButton(
            function=self._add_item_start,
            label="Basic",
            style=discord.ButtonStyle.grey,
            row=0,
            reference='basic'
            )
    
    @property
    def add_random_item_button(self):
        return DiscordButton(
            function=self._add_item_start,
            label="Random",
            style=discord.ButtonStyle.grey,
            row=0,
            reference='random'
            )
    @property
    def add_cash_item_button(self):
        return DiscordButton(
            function=self._add_item_start,
            label="Cash",
            style=discord.ButtonStyle.grey,
            row=0,
            reference='cash'
            )
    @property
    def add_roleadd_item_button(self):
        return DiscordButton(
            function=self._add_item_start,
            label="Role (Add-Only)",
            style=discord.ButtonStyle.grey,
            row=1,
            reference='roleadd'
            )
    @property
    def add_roleex_item_button(self):
        return DiscordButton(
            function=self._add_item_start,
            label="Role (Exclusive)",
            style=discord.ButtonStyle.grey,
            row=1,
            reference='roleexclusive'
            )
    @property
    def add_rolebi_item_button(self):
        return DiscordButton(
            function=self._add_item_start,
            label="Role (Bi-Directional)",
            style=discord.ButtonStyle.grey,
            row=1,
            reference='rolebi'
            )
    
    ##################################################
    ### ADD ITEM
    ##################################################    
    async def _add_item_start(self,interaction:discord.Interaction,button:DiscordButton):        
        self.new_item = NewShopItem(interaction.guild.id)

        if button.reference == 'startover':    
            await interaction.response.defer()

            self.clear_items()            
            
            self.add_item(self.add_basic_item_button)
            self.add_item(self.add_random_item_button)
            
            if self.user.id in self.bot.owner_ids:
                self.add_item(self.add_cash_item_button)
            
            self.add_item(self.add_roleadd_item_button)
            self.add_item(self.add_roleex_item_button)
            self.add_item(self.add_rolebi_item_button)

            embed = await self.start_embed()
            await interaction.edit_original_response(embed=embed,view=self)
        
        else:
            await interaction.response.send_modal(self.create_item_modal)

            if button.reference == 'roleadd':
                self.new_item.type = 'role'
                
            elif button.reference == 'roleexclusive':
                self.new_item.type = 'role'
                self.new_item.exclusive = True

            elif button.reference == 'rolebi':
                self.new_item.type = 'role'
                self.new_item.bidirectional = True

            else:
                self.new_item.type = button.reference

    async def _create_item_modal_callback(self,interaction:discord.Interaction,modal:DiscordModal):
        await interaction.response.defer()

        self.new_item.name = modal.children[0].value
        self.new_item.price = int(modal.children[1].value)
        self.new_item.stock = int(modal.children[2].value)
        self.new_item.category = modal.children[3].value
        self.new_item.description = modal.children[4].value

        await self._add_item_main(interaction,modal)
    
    async def _add_item_main(self,interaction:discord.Interaction,component:Union[DiscordButton,DiscordSelectMenu,DiscordModal]):
        if not interaction.response.is_done():
            await interaction.response.defer()
        
        self.guild_items = await ShopItem.get_by_guild(self.guild.id)

        if getattr(component,'reference',None) == 'requiredrole':
            self.new_item.required_role = component.values[0]

        if getattr(component,'reference',None) == 'associatedrole':
            self.new_item.associated_role = component.values[0]

        if getattr(component,'reference',None) == 'randomitems':
            self.new_item.random_items = component.values
        
        self.clear_items()
        save_button = self.save_item_button
        if not self.new_item.ready_to_save:
            save_button.disabled = True
        
        self.add_item(self.start_over_add)
        self.add_item(save_button)
        self.add_item(self.close_button)
        
        self.add_item(self.required_role_selector)

        # if self.new_item.type in ['cash','basic']:
        #     self.add_item(self.buy_message_button)

        if self.new_item.type in ['role']:
            self.add_item(self.associated_role_selector)
        
        if self.new_item.type == 'random':
            self.add_item(self.random_item_selector)

        embed = await self.add_item_creation_embed()
        await interaction.edit_original_response(embed=embed,view=self)
    
    # async def _send_buy_message_modal(self,interaction:discord.Interaction,button:DiscordButton):        
    #     self.new_item = NewShopItem(interaction.guild_id)
    #     await interaction.response.send_modal(self.buy_message_modal)
    
    # async def _buy_message_modal_callback(self,interaction:discord.Interaction,modal:DiscordModal):
    #     await interaction.response.defer()
    #     self.new_item.buy_message = modal.children[0].value
    #     await self._add_item_main(interaction,modal)
    
    async def _save_item(self,interaction:discord.Interaction,button:DiscordButton):
        await interaction.response.defer()

        item = await self.new_item.save_item()
        embed = await clash_embed(
            context=self.ctx,
            title=f"**Add Item: {self.guild.name}**",
            message="```Item Added```"
                + f"\n\n**Type**: `{item.type}`"
                + (f"\n**Add-only**: `{True if not item.bidirectional else False}`" if item.type in ['role'] else "")
                + (f"\n**Exclusive**: `{item.exclusive_role}`" if item.type in ['role'] else "")
                + f"\n\n**Name**: `{item.name}`"
                + f"\n**Price**: `{item.price:,}`"
                + f"\n**Stock**: `{item.stock}`"
                + f"\n**Category**: `{item.category}`"
                + f"\n**Description**: `{item.description}`"
                + f"\n**Buy Message**: `{item.buy_message}`"
                )

        self.clear_items()
        self.stop()
        await interaction.edit_original_response(embed=embed,view=None)

    async def add_item_creation_embed(self):
        embed = await clash_embed(
            context=self.ctx,
            title=f"**Add Item: {self.guild.name}**",
            message="```You are adding...```"
                + f"\n\n`{'Type:':<15}` {self.new_item.type}"
                + f"\n\n`{'Name:':<15}` {self.new_item.name}"
                + f"\n`{'Price:':<15}` {self.new_item.price:,}"
                + f"\n`{'Stock:':<15}` {self.new_item.stock if self.new_item.stock != -1 else 'Infinite'}"
                + f"\n`{'Requires:':<15}` {getattr(self.new_item.required_role,'mention',None)}"
                + f"\n`{'Category:':<15}` {self.new_item.category}"
                + f"\n`{'Description:':<15}` {self.new_item.description}"
                + (f"\n\n`{'Buy Message:':<15}` {self.new_item.buy_message}" if self.new_item.type in ['cash','basic'] else "")
                + (f"\n\n`{'Assigns Role:':<15}` {getattr(self.new_item.associated_role,'mention',None)}" if self.new_item.type in ['role'] else "")
                + (f"\n`{'Add-only:':<15}` {True if not self.new_item.bidirectional else False}" if self.new_item.type in ['role'] else "")
                + (f"\n`{'Exclusive:':<15}` {self.new_item.exclusive}" if self.new_item.type in ['role'] else "")
                )
        
        if self.new_item.exclusive:
            embed.description += f"\n\nNote: You are recommended to specify a Category, otherwise this will remove **ALL** Roles granted via the Shop."

        if self.new_item.type == 'random':
            item_msg = f"\n\n`{'Contains Items':<30}`"
            if self.new_item.random_items is not None:
                items = await asyncio.gather(*(ShopItem.get_by_id(i) for i in self.new_item.random_items))
                if len(self.new_item.random_items) > 0:
                    item_msg += '\n- '
                    item_msg += '\n- '.join([f"{i}" for i in items])
            embed.description += item_msg
            embed.description += f"\n\nNote: Random Items will not change the stock values of its component items."
            
        return embed
    
    @property
    def create_item_modal(self):
        m = DiscordModal(
            function=self._create_item_modal_callback,
            title=f"Create New Item",
            )
        name_field = discord.ui.TextInput(
            label="Name",
            placeholder="Max 30 characters",
            max_length=30,
            style=discord.TextStyle.short,
            required=True
            )
        price_field = discord.ui.TextInput(
            label="Price",
            placeholder="Max 7 digits, numbers only please.",
            style=discord.TextStyle.short,
            max_length=7,
            required=True
            )
        stock_field = discord.ui.TextInput(
            label="Stock",
            placeholder="Initial stock of this Item (max 99). -1 for unlimited.",
            style=discord.TextStyle.short,
            max_length=2,
            required=True
            )
        category_field = discord.ui.TextInput(
            label="Category",
            placeholder="Optional. Used when displaying the item in the store.",
            max_length=100,
            style=discord.TextStyle.short,
            required=False
            )
        description_field = discord.ui.TextInput(
            label="Description",
            placeholder="Optional. Used when displaying the item in the store.",
            max_length=100,
            style=discord.TextStyle.short,
            required=False
            )
        m.add_item(name_field)
        m.add_item(price_field)
        m.add_item(stock_field)
        m.add_item(category_field)
        m.add_item(description_field)        
        return m   

    @property
    def save_item_button(self):
        return DiscordButton(
            function=self._save_item,
            label="Save Item",
            emoji=EmojisUI.TASK_CHECK,
            style=discord.ButtonStyle.grey,
            reference='saveitem'
            )

    # @property
    # def buy_message_button(self):
    #     return DiscordButton(
    #         function=self._send_buy_message_modal,
    #         label="Set Buy Message",
    #         style=discord.ButtonStyle.grey,
    #         )

    # @property
    # def buy_message_modal(self):
    #     m = DiscordModal(
    #         function=self._buy_message_modal_callback,
    #         title=f"Set Buy Message",
    #         )
    #     name_field = discord.ui.TextInput(
    #         label="Set Message",
    #         placeholder="The Buy Message is sent to the user when they purchase this item.",
    #         style=discord.TextStyle.short,
    #         required=True
    #         )
    #     m.add_item(name_field)   
        return m

    @property
    def required_role_selector(self):
        role_select = DiscordRoleSelect(
            function=self._add_item_main,
            placeholder="Optional: Select a Role required to purchase this item.",
            min_values=0,
            max_values=1,
            row=4
            )
        role_select.reference = 'requiredrole'
        return role_select

    @property
    def associated_role_selector(self):
        role_select = DiscordRoleSelect(
            function=self._add_item_main,
            placeholder="Select a Role to grant on purchase.",
            min_values=1,
            max_values=1,
            row=1
            )
        role_select.reference = 'associatedrole'
        return role_select

    @property
    def random_item_selector(self):
        eligible_items = [i for i in self.guild_items if i.type not in ['random']]

        select_options = [discord.SelectOption(
            default=True if isinstance(self.new_item.random_items,list) and item.id in self.new_item.random_items else False,
            label=f"{item}",
            value=item.id,
            description=item.description,)
            for item in random.sample(eligible_items,25)
            ]
        item_select = DiscordSelectMenu(
            function=self._add_item_main,
            placeholder="Select 2 or more Items to be included.",
            options=select_options,
            min_values=2,
            max_values=len(select_options),
            row=1,
            reference='randomitems'
            )
        return item_select
    
    ##################################################
    ### MAIN MENU
    ##################################################
    async def _main_menu(self,interaction:Union[commands.Context,discord.Interaction],button:Optional[DiscordButton]=None):
        if isinstance(interaction,discord.Interaction):
            if not interaction.response.is_done():
                await interaction.response.defer()

        self.clear_items()
        self.guild_items = await ShopItem.get_by_guild(self.guild.id)

        self.add_item(self.main_menu_button)
        self.add_item(self.add_item_button)
        
        restock_one = self.auto_restock_one_button
        if len([i for i in self.guild_items if i.stock == 0]) == 0:
            restock_one.disabled = True
        self.add_item(restock_one)

        restock_five = self.auto_restock_five_button
        if len([i for i in self.guild_items if i.stock == 0]) == 0:
            restock_five.disabled = True
        self.add_item(restock_five)
        
        if self.show_item_select:
            self.add_item(self.show_item_select)
        if self.hide_item_select:
            self.add_item(self.hide_item_select)
        self.add_item(self.close_button)

        embed = await self.main_menu_embed()
        if isinstance(interaction,discord.Interaction):
            await interaction.edit_original_response(embed=embed,view=self)
        else:
            await interaction.reply(embed=embed,view=self)
    
    async def main_menu_embed(self):
        embed = await clash_embed(
            context=self.ctx,
            title=f"**Store Manager: {self.guild.name}**",
            message=f"**Welcome to the Store Manager!**"
                + f"\nHere, Server Administrators are able to add and manage items in their Server Store."
                + f"\n\n**Adding Items**"
                + f"\n- Items by default are hidden from view in the Store. To make them viewable, use the appropriate dropdown below."
                + f"\n\n**Editing Items**"
                + f"\n- Stock can be edited using the `/manage-store restock` command."
                + f"\n- Once added, items cannot be edited (except for Stock and Visibility). To edit other values, delete and add them using new values."
                + f"\n\n**Deleted Items**"
                + f"\n- Use the `/manage-store delete-item` command to delete items from the Store."
                + f"\n- Once deleted, items cannot be recovered. Please be careful when deleting items."
                + f"\n- Deleting does not affect already-purchased items."
                + f"\n\u200b"
                )
        embed.add_field(
            name=f"**Overview**",
            value="```ini"
                + f"\n{'[Total Items]':<15} {len(self.guild_items):>3}"
                + f"\n{'[In Store]':<15} {len([i for i in self.guild_items if i.show_in_store]):>3}"
                + f"\n{'[Stock Out]':<15} {len([i for i in self.guild_items if i.stock == 0]):>3}"
                + "```",
            inline=True)
        embed.add_field(
            name=f"**Items by Type (In Store / Total)**",
            value="```ini"
                + f"\n{'[Basic]':<10} {len([i for i in self.guild_items if i.type == 'basic' and i.show_in_store]):^4}/{len([i for i in self.guild_items if i.type == 'basic']):^4}"
                + f"\n{'[Role]':<10} {len([i for i in self.guild_items if i.type == 'role' and i.show_in_store]):^4}/{len([i for i in self.guild_items if i.type == 'role']):^4}"
                + f"\n{'[Random]':<10} {len([i for i in self.guild_items if i.type == 'random' and i.show_in_store]):^4}/{len([i for i in self.guild_items if i.type == 'random']):^4}"
                + f"\n{'[Cash]':<10} {len([i for i in self.guild_items if i.type == 'cash' and i.show_in_store]):^4}/{len([i for i in self.guild_items if i.type == 'cash']):^4}"
                + "```",
            inline=True)
        if len([i for i in self.guild_items if i.stock == 0]) > 0:
            embed.add_field(
                name=f"**Needing Restock**",
                value=f"Use the `/manage-store restock` command to restock items."
                    + "\n- "
                    + "\n- ".join([f"{str(i)}" for i in self.guild_items if i.stock == 0])
                    + "\n\u200b",
                inline=False)
        return embed
    
    
    @property
    def show_item_select(self):
        if len([i for i in self.guild_items if not i.show_in_store]) == 0:
            return None
        select_options = [discord.SelectOption(
            label=f"{str(item)}",
            value=item.id,
            description=item.description,)
            for item in [i for i in self.guild_items if not i.show_in_store][:25]
            ]
        item_select = DiscordSelectMenu(
            function=self._show_selected_items,
            placeholder="Select items to be shown in Store.",
            options=select_options,
            min_values=1,
            max_values=len(select_options),
            row=2
            )
        return item_select
    @property
    def hide_item_select(self):
        if len([i for i in self.guild_items if i.show_in_store]) == 0:
            return None
        select_options = [discord.SelectOption(
            label=f"{item}",
            value=item.id,
            description=item.description,)
            for item in [i for i in self.guild_items if i.show_in_store][:25]
            ]
        item_select = DiscordSelectMenu(
            function=self._hide_selected_items,
            placeholder="Select items to be hidden from the Store.",
            options=select_options,
            min_values=1,
            max_values=len(select_options),
            row=3
            )
        return item_select
    
    
    ##################################################
    ### SHOW ITEM
    ##################################################
    async def _show_selected_items(self,interaction:discord.Interaction,select:DiscordSelectMenu):
        await interaction.response.defer()

        count = 0
        self.clear_items()
        embed = await clash_embed(
            context=self.ctx,
            message=f"{EmojisUI.LOADING} Please wait...",
            )
        await interaction.edit_original_response(embed=embed,view=self)

        async for item_id in AsyncIter(select.values):
            item = ShopItem.get_by_id(item_id)
            if item:
                count += 1
                await item.unhide()
        
        embed = await clash_embed(
            context=self.ctx,
            message=f"**{count} items added to the Store.**",
            show_author=False)
        
        await interaction.followup.send(embed=embed,ephemeral=True)
        await self._main_menu(interaction)    

    ##################################################
    ### HIDE ITEM
    ##################################################
    async def _hide_selected_items(self,interaction:discord.Interaction,select:DiscordSelectMenu):
        await interaction.response.defer()

        count = 0
        self.clear_items()
        embed = await clash_embed(
            context=self.ctx,
            message=f"{EmojisUI.LOADING} Please wait...",
            )
        await interaction.edit_original_response(embed=embed,view=self)

        async for item_id in AsyncIter(select.values):
            item = ShopItem.get_by_id(item_id)
            if item:
                count += 1
                await item.hide()
        
        embed = await clash_embed(
            context=self.ctx,
            message=f"**{count} items removed from the Store.**",
            show_author=False)
        await interaction.followup.send(embed=embed,ephemeral=True)
        await self._main_menu(interaction)
    
    ##################################################
    ### AUTO RESTOCK ONE
    ##################################################
    async def _restock_one_callback(self,interaction:discord.Interaction,select:DiscordSelectMenu):
        await interaction.response.defer()

        count = 0
        self.clear_items()
        embed = await clash_embed(
            context=self.ctx,
            message=f"{EmojisUI.LOADING} Please wait...",
            )
        await interaction.edit_original_response(embed=embed,view=self)

        async for i in AsyncIter([i for i in self.guild_items if i.stock == 0]):
            count += 1
            i.stock += 1
        
        embed = await clash_embed(
            context=self.ctx,
            message=f"**{count} items restocked by 1.**",
            show_author=False)
        await interaction.followup.send(embed=embed,ephemeral=True)
        await self._main_menu(interaction)
    
    ##################################################
    ### AUTO RESTOCK FIVE
    ##################################################
    async def _restock_five_callback(self,interaction:discord.Interaction,select:DiscordSelectMenu):
        await interaction.response.defer()

        count = 0
        self.clear_items()
        embed = await clash_embed(
            context=self.ctx,
            message=f"{EmojisUI.LOADING} Please wait...",
            )
        await interaction.edit_original_response(embed=embed,view=self)

        async for i in AsyncIter([i for i in self.guild_items if i.stock == 0]):
            count += 1
            i.stock += 5
        
        embed = await clash_embed(
            context=self.ctx,
            message=f"**{count} items restocked by 5.**",
            show_author=False)
        await interaction.followup.send(embed=embed,ephemeral=True)
        await self._main_menu(interaction)