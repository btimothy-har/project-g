import discord
import copy
import pendulum
import asyncio

from typing import *
from mongoengine import *

from redbot.core import bank
from redbot.core.utils import AsyncIter

from .item import ShopItem, db_ShopItem

from coc_main.api_client import BotClashClient
from coc_main.utils.components import clash_embed

bot_client = BotClashClient()

class db_UserInventory(Document):
    user_id = IntField(required=True,primary_key=True)
    inventory = DictField(default={})

class InventoryItem(ShopItem):
    def __init__(self,item:db_ShopItem,quantity:int):        
        self.quantity = quantity
        super().__init__(item)
    
    @classmethod
    async def get(cls,item_id:str,quantity:int):
        def _db_query():
            try:
                item = db_ShopItem.objects.get(id=item_id)
            except DoesNotExist:
                return None
            return item
        
        item = await bot_client.run_in_thread(_db_query)
        if item is None:
            return None
        return cls(item,quantity)
    
class UserInventory():
    _locks = {}

    @classmethod
    async def get_by_user_id(cls,user_id:int):
        def _query_db():
            try:
                inv = db_UserInventory.objects.get(user_id=user.id)
            except DoesNotExist:
                inv = db_UserInventory(user_id=user.id)
                inv.save()
            return inv
        
        user = bot_client.bot.get_user(user_id)
        if not user:
            return None
        inv = await bot_client.run_in_thread(_query_db)
        inventory = copy.copy(inv.inventory)

        items = [await InventoryItem.get(item_id,quantity) for item_id,quantity in inventory.items() if quantity > 0]
        return UserInventory(user,items)

    def __init__(self,discord_user:Union[discord.User,discord.Member],inventory:List[InventoryItem]=[]):
        self.user = discord_user
        self.inventory = inventory
    
    @property
    def lock(self):
        try:
            lock = UserInventory._locks[self.user.id]
        except KeyError:
            UserInventory._locks[self.user.id] = lock = asyncio.Lock()
        return lock
    
    async def save(self):
        def _save_to_db():
            db_inv = db_UserInventory(
                user_id=self.user.id,
                inventory=inventory_dict
                )
            db_inv.save()
            
        inventory_dict = {item.id:item.quantity for item in self.inventory if item.quantity > 0}
        await bot_client.run_in_thread(_save_to_db)
    
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
            get_item.quantity -= quantity
            await self.save()
            return True
    
    async def add_item_to_inventory(self,item:ShopItem,quantity:int=1):
        async with self.lock:
            get_item = self.get_item(item)
            if not get_item:
                inv_item = await InventoryItem.get(item.id,quantity)
                self.inventory.append(inv_item)
            else:
                get_item.quantity += quantity
            await self.save()

    async def purchase_item(self,item:ShopItem):
        await item.purchase(self.user)
        if item.type in ['random']:
            item = await item.random_select()

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
                        similar_items = await ShopItem.get_by_guild(item.guild_id)
                    else:
                        similar_items = await ShopItem.get_by_guild_category(item.guild_id,item.category)

                    roles_from_similar_items = [i.assigns_role for i in similar_items if i.assigns_role]

                    #remove_role_from_user
                    async for role in AsyncIter(roles_from_similar_items):
                        if role in self.user.roles:
                            await self.user.remove_roles(role)
                
                await self.user.add_roles(item.assigns_role)
        
        await bank.withdraw_credits(self.user,item.price)
        return item

    async def gift_item(self,item:InventoryItem,recipient:discord.Member):        
        remove_item = await self.remove_item_from_inventory(item)
        if not remove_item:
            return False

        r_inv = await UserInventory.get_by_user_id(recipient.id)
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
        