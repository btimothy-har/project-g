import asyncio
import bson
import discord
import pendulum

from typing import *
from async_property import AwaitLoader
from collections import defaultdict

from redbot.core import bank, commands
from redbot.core.utils import AsyncIter

from coc_main.api_client import BotClashClient
from coc_main.utils.components import clash_embed

from .item import ShopItem

bot_client = BotClashClient()

# db__user_inventory = {
#   '_id': user_id,    
#   'inventory': {}
#   }

class InventoryItem(ShopItem):
    def __init__(self,item:dict,quantity:int):        
        self.quantity = quantity
        super().__init__(item)

    def to_json(self) -> dict:
        return {
            '_id': self.id,
            'name': self.name,
            'description': self.description,
            'type': self.type,
            'inventory_quantity': self.quantity,
            }
    
    @classmethod
    async def get(cls,item_id:str,quantity:int):
        query = await bot_client.coc_db.db__shop_item.find_one({'_id':bson.ObjectId(item_id)})
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
    
    def _assistant_json(self) -> List[dict]:
        return [i.to_json() for i in self.inventory if i.type in ['cash']]
    
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
                },
                upsert=True
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
                },
                upsert=True
            )
            await self.load()

    async def purchase_item(self,item:ShopItem,free_purchase:bool=False):
        member = item.guild.get_member(self.user.id)
        await item.purchase(member,free_purchase=free_purchase)

        if item.type in ['random']:
            item = await item.random_select()

        if item.type in ['basic','cash']:
            if item.buy_message and len(item.buy_message) > 0:
                await member.send(item.buy_message)
            else:
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
                    r_iter = AsyncIter(roles_from_similar_items)
                    async for role in r_iter:
                        if role in member.roles:
                            await member.remove_roles(role)
                
                await member.add_roles(item.assigns_role)
        
        if free_purchase:
            return item
        await bank.withdraw_credits(self.user,item.price)
        return item

    async def gift_item(self,item:InventoryItem,recipient:discord.Member):        
        remove_item = await self.remove_item_from_inventory(item)
        if not remove_item:
            return False

        r_inv = await UserInventory(recipient)
        if r_inv.has_item(item):
            return False
        await r_inv.add_item_to_inventory(item)
        return item        

    async def get_embed(self,ctx):
        inventory_text = ""
        user = None
        if isinstance(ctx,commands.Context):
            user = ctx.author
        if isinstance(ctx,discord.Interaction):
            user = ctx.user
        
        if len(self.inventory) > 0:
            for item in self.inventory:
                inventory_text += f"\n\n**{item.name}** x{item.quantity}"
                inventory_text += (f"\n{item.description}" if len(item.description) > 0 else "")
                if getattr(user,'id',None) == self.user.id:
                    if item.type in ['basic']:
                        inventory_text += f"\nPurchased from: {item.guild.name}"
                    if item.type in ['cash']:
                        inventory_text += f"\nRedeem this in: The Assassins Guild"
                    if item.subscription:
                        expiry = await item.compute_user_expiry(self.user.id)
                        if expiry:
                            inventory_text += f"\nExpires: <t:{expiry.int_timestamp}:R>"

        embed = await clash_embed(
            context=ctx,
            title=f"{self.user.display_name}'s Inventory",
            message=f"**Total Items:** {len(self.inventory)}"
                + inventory_text
                + f"\n\u200b",
            thumbnail=self.user.display_avatar.with_static_format('png'),
            timestamp=pendulum.now()
            )
        
        subscribed_roles = await ShopItem.get_subscribed_roles_for_user(self.user.id)
        if len(subscribed_roles) > 0:
            text = ""
            r_iter = AsyncIter(subscribed_roles)
            async for role in r_iter:
                expiry = await role.compute_user_expiry(self.user.id)
                text += f"\n**{role.name}**"
                text += f"\nGrants: {getattr(role.assigns_role,'mention','Unknown')}"
                text += f"\nExpires: <t:{expiry.int_timestamp}:R>"
                text += "\n\u200b"
            embed.add_field(
                name="You are also subscribed to the following roles.",
                value=text,
                )
        return embed