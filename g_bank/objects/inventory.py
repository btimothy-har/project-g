import discord
import copy
import pendulum

from typing import *
from mongoengine import *

from redbot.core import bank
from redbot.core.utils import AsyncIter

from .item import ShopItem

from coc_main.utils.components import clash_embed

class db_UserInventory(Document):
    user_id = IntField(required=True,primary_key=True)
    inventory = DictField(default={})

class InventoryItem(ShopItem):
    def __init__(self,item_id:str,quantity:int):        
        self.quantity = quantity
        item = ShopItem.get_by_id(item_id)
        super().__init__(item)        

class UserInventory():
    def __init__(self,discord_user:Union[discord.User,discord.Member]):
        self.user = discord_user

        try:
            inv = db_UserInventory.objects.get(user_id=self.user.id)
        except DoesNotExist:
            inv = db_UserInventory(user_id=self.user.id).save()

        self._inventory = copy.copy(inv.inventory)
    
    def save(self):
        db_inv = db_UserInventory(
            user_id=self.user.id,
            inventory=self._inventory
            )
        db_inv.save()
    
    def has_item(self,item:ShopItem,quantity:int=1):
        if item.id not in self._inventory:
            return False
        if self._inventory[item.id] < quantity:
            return False
        return True
    
    @property
    def inventory(self):
        return [InventoryItem(item_id,quantity) for item_id,quantity in self._inventory.items() if quantity > 0]
    
    async def remove_item_from_inventory(self,item:ShopItem,quantity:int=1):
        if item.id not in self._inventory:
            return False
        if self._inventory[item.id] < quantity:
            return False
        self._inventory[item.id] -= quantity
        if self._inventory[item.id] < 1:
            del self._inventory[item.id]
        self.save()
        return True
    
    async def add_item_to_inventory(self,item:ShopItem,quantity:int=1):
        if item.id not in self._inventory:
            self._inventory[item.id] = 0
        self._inventory[item.id] += quantity
        self.save()

    async def purchase_item(self,item:ShopItem):
        await bank.withdraw_credits(self.user,item.price)

        if isinstance(item.stock,int) and item.stock > 0:
            item.stock -= 1
            item.save()

        if item.type in ['random']:
            item = item.random_select()

        if item.type in ['basic','cash']:
            await self.add_item_to_inventory(item)
        
        if item.type in ['role']:
            if item.bidirectional_role:
                if item.assigns_role in self.user.roles:
                    await self.user.remove_roles(item.assigns_role)
                else:
                    await self.user.add_roles(item.assigns_role)
            else:
                if item.exclusive_role:
                    if item.category == 'Uncategorized':
                        similar_items = ShopItem.get_by_guild(item.guild_id)
                    else:
                        similar_items = ShopItem.get_by_category(item.guild_id,item.category)

                    roles_from_similar_items = [i.assigns_role for i in similar_items if i.assigns_role]

                    #remove_role_from_user
                    async for role in AsyncIter(roles_from_similar_items):
                        if role in self.user.roles:
                            await self.user.remove_roles(role)
                
                await self.user.add_roles(item.assigns_role)
        return item

    async def gift_item(self,item:InventoryItem,recipient:discord.Member):        
        remove_item = await self.remove_item_from_inventory(item)
        if not remove_item:
            return False

        r_inv = UserInventory(recipient)
        await r_inv.add_item_to_inventory(item)
        return item        

    async def get_embed(self,ctx):
        inventory_text = ""
        if len(self.inventory) > 0:
            for item in self.inventory:
                inventory_text += f"\n\n**{item.name}** x{item.quantity}"
                inventory_text += f"\nRedeem this in: {item.guild.name}"
                inventory_text += f"\n{item.description}"

        embed = await clash_embed(
            context=ctx,
            title=f"{self.user.display_name}'s Inventory",
            message=f"**Total Items:** {len(self.inventory)}"
                + inventory_text,
            thumbnail=self.user.display_avatar.with_static_format('png'),
            timestamp=pendulum.now()
            )
        return embed
        