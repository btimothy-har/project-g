import discord
import copy
import pendulum
import asyncio

from typing import *
from mongoengine import *

from redbot.core import bank
from redbot.core.utils import AsyncIter,bounded_gather
from async_property import AwaitLoader

from collections import defaultdict

from .item import ShopItem
from bson.int64 import Int64

from coc_main.api_client import BotClashClient
from coc_main.utils.components import clash_embed

bot_client = BotClashClient()

class db_UserInventory(Document):
    user_id = IntField(required=True,primary_key=True)
    inventory = DictField(default={})

class InventoryItem(ShopItem):
    def __init__(self,item:dict,quantity:int):        
        self.quantity = quantity
        super().__init__(item)
    
    @classmethod
    async def get(cls,item_id:str,quantity:int):
        query = await bot_client.coc_db.db__shop_item.find_one({'_id':item_id})
        if query:
            return cls(query,quantity)
        return None
    
class UserInventory(AwaitLoader):
    _locks = defaultdict(asyncio.Lock)
    __slots__ = [
        'user',
        'inventory'
        ]        

    def __init__(self,discord_user:Union[discord.User,discord.Member]):
        self.user = discord_user
        self.inventory = []
    
    async def load(self):
        query = await bot_client.coc_db.db__user_inventory.find_one({'_id':self.user.id})        
        if query:
            inventory = query.get('inventory',{})
            get_items = await asyncio.gather(*(InventoryItem.get(item_id,quantity) for item_id,quantity in inventory.items() if quantity > 0))
            self.inventory = [i for i in get_items if isinstance(i,InventoryItem)]
    
    @property
    def lock(self):
        return self._locks[self.user.id]
    
    def get_item(self,item:ShopItem) -> Optional[InventoryItem]:
        find_item = [i for i in self.inventory if i.id == item.id]
        if len(find_item) == 0:
            return None
        return find_item[0]
    
    def has_item(self,item:ShopItem,quantity:int=1):
        i = self.get_item(item)
        if not i:
            return False
        if i.quantity < quantity:
            return False
        return True
    
    async def remove_item_from_inventory(self,item:ShopItem,quantity:int=1):
        async with self.lock:
            get_item = self.get_item(item)
            if not get_item:
                return False
            if get_item.quantity < quantity:
                return False
            await bot_client.coc_db.db__user_inventory.update_one(
                {'_id':self.user.id},
                {'$inc': {
                    f'inventory.{item.id}': -quantity
                    }
                }
            )
            await self.load()
            return True
    
    async def add_item_to_inventory(self,item:ShopItem,quantity:int=1):
        async with self.lock:
            await bot_client.coc_db.db__user_inventory.update_one(
                {'_id':self.user.id},
                {'$inc': {
                    f'inventory.{item.id}': quantity
                    }
                }
            )
            await self.load()

    async def purchase_item(self,item:ShopItem):
        member = item.guild.get_member(self.user.id)
        await item.purchase(member)

        if item.type in ['random']:
            item = await item.random_select()

        if item.type in ['basic','cash']:
            await self.add_item_to_inventory(item)
        
        if item.type in ['role']:
            if item.bidirectional_role:
                if item.assigns_role in member.roles:
                    await member.remove_roles(item.assigns_role)
                else:
                    await member.add_roles(item.assigns_role)
            else:
                if item.exclusive_role:
                    if item.category == 'Uncategorized':
                        similar_items = await ShopItem.get_by_guild(item.guild_id)
                    else:
                        similar_items = await ShopItem.get_by_guild_category(item.guild_id,item.category)

                    roles_from_similar_items = [i.assigns_role for i in similar_items if i.assigns_role]

                    #remove_role_from_user
                    async for role in AsyncIter(roles_from_similar_items):
                        if role in member.roles:
                            await member.remove_roles(role)
                
                await member.add_roles(item.assigns_role)
        
        await bank.withdraw_credits(self.user,item.price)
        return item

    async def gift_item(self,item:InventoryItem,recipient:discord.Member):        
        remove_item = await self.remove_item_from_inventory(item)
        if not remove_item:
            return False

        r_inv = await UserInventory(recipient)
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
        