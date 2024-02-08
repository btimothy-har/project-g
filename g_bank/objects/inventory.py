import asyncio
import bson
import discord
import pendulum

from typing import *
from async_property import AwaitLoader
from collections import defaultdict

from redbot.core import bank, commands
from redbot.core.utils import AsyncIter, bounded_gather

from coc_main.api_client import BotClashClient
from coc_main.utils.components import clash_embed

from .item import ShopItem

bot_client = BotClashClient()

# db__user_inventory = {
#   '_id': user_id,    
#   'inventory': {}
#   }

# db__user_item = {
#  'user': user_id,
#  'timestamp': now,
#  'in_inventory': True,
#  'item': {}
#   }

class InventoryItem(ShopItem):

    @classmethod
    async def get_by_id(cls,item_id:str) -> Optional['InventoryItem']:
        query = await bot_client.coc_db.db__user_item.find_one({'_id':bson.ObjectId(item_id)})
        if query:
            return cls(query)
        return None

    @classmethod
    async def get_for_user(cls,user:Union[discord.Member,discord.User]) -> List['InventoryItem']:
        if getattr(user,'guild',None):
            filter_criteria = {
                'user':user.id,
                'in_inventory':True,
                }
        else:
            filter_criteria = {
                'user':user.id,
                'in_inventory':True,
                'item.guild_id':user.guild.id
                }
        query = bot_client.coc_db.db__user_item.find(filter_criteria)
        items = [cls(item) async for item in query]
        return items

    @classmethod
    async def get_expiring_items(cls) -> List['InventoryItem']:
        filter_criteria = {
            'in_inventory':True,
            'item.subscription_duration':{'$gt':0},
            }
        query = bot_client.coc_db.db__user_item.find(filter_criteria)
        items = [cls(item) async for item in query]
        return items
    
    def __init__(self,item_dict:dict):
        self.user = item_dict['user']
        self.timestamp = pendulum.from_timestamp(item_dict['timestamp'])
        self.in_inventory = item_dict['in_inventory']

        self._inv_id = item_dict['_id']
        self._is_legacy = item_dict.get('legacy_migration',False)
        super().__init__(item_dict['item'])

    # def to_json(self) -> dict:
    #     return {
    #         '_id': self.id,
    #         'name': self.name,
    #         'description': self.description,
    #         'type': self.type,
    #         'inventory_quantity': self.quantity,
    #         }
    
    @property
    def expiration(self) -> Optional[pendulum.DateTime]:
        if not self.subscription:
            return None
    
        if bot_client.bot.user.id == 828838353977868368:
            expiry_time = self.timestamp.add(minutes=self.subscription_duration)
        else:
            expiry_time = self.timestamp.add(days=self.subscription_duration)
        return expiry_time   
    
    async def _update_timestamp(self,timestamp:pendulum.DateTime):
        await bot_client.coc_db.db__user_item.update_one(
            {'_id':self._id},
            {'$set':{'timestamp':timestamp.int_timestamp}}
            )
        self.timestamp = timestamp

    async def remove_from_inventory(self):
        self.in_inventory = False
        await bot_client.coc_db.db__user_item.update_one(
            {'_id':self._id},
            {'$set':{'in_inventory':False}}
            )
        if self.assigns_role:
            member = self.guild.get_member(self.user)
            if member and self.assigns_role in member.roles:
                try:
                    await member.remove_roles(
                        self.assigns_role,
                        reason=f"Removed from inventory {self.id} {self.name}."
                        )
                except:
                    pass
        bot_client.coc_main_log.info(f"{self.id} {self.name} removed from {self.user.id} {self.user.name}.")

    @classmethod
    async def add_for_user(cls,user:discord.Member,item:ShopItem,is_migration:bool=False) -> 'InventoryItem':
        new_item = await bot_client.coc_db.db__user_item.insert_one(
            {
                'user':user.id,
                'timestamp':pendulum.now().int_timestamp,
                'in_inventory':True,
                'item':item.db_json(),
                'legacy_migration':is_migration
                }
            )        
        bot_client.coc_main_log.info(f"{item.id} {item.name} added to {user.id} {user.name}.")
        return await cls.get_by_id(str(new_item.inserted_id))
    
class UserInventory(AwaitLoader):
    _locks = defaultdict(asyncio.Lock)
    __slots__ = [
        'user',
        'items'
        ]        

    def __init__(self,discord_user:Union[discord.User,discord.Member]):
        self.user = discord_user
        self.guild = getattr(discord_user,'guild',None)
        self.items = []
    
    def _assistant_json(self) -> List[dict]:
        return [i.to_json() for i in self.inventory if i.type in ['cash']]
    
    async def load(self):
        self.items = await InventoryItem.get_for_user(self.user)
    
    @property
    def lock(self):
        return self._locks[self.user.id]
    
    def get_item(self,item:ShopItem) -> List[Optional[InventoryItem]]:
        find_item = [i for i in self.items if i.id == item.id]
        if len(find_item) == 0:
            return None
        return sorted(
            find_item,
            key=lambda x: x.timestamp.int_timestamp
            )
    
    def has_item(self,item:ShopItem,quantity:int=1):
        i = self.get_item(item)
        if not i:
            return False
        if len(i) <= quantity:
            return False
        return True
    
    async def add_item_to_inventory(self,item:ShopItem) -> InventoryItem:
        new_item = await InventoryItem.add_for_user(self.user,item)

        if new_item.type in ['random']:
            await new_item.remove_from_inventory()
            new_item = await item.random_select()
            new_item = await self.add_item_to_inventory(new_item)
        
        if new_item.type in ['basic','cash']:
            if new_item.buy_message and len(new_item.buy_message) > 0:
                member = new_item.guild.get_member(self.user.id)
                await member.send(new_item.buy_message)
        
        if new_item.type in ['role']:
            member = new_item.guild.get_member(self.user.id)

            if new_item.bidirectional_role:                
                if new_item.assigns_role in member.roles:
                    await new_item.remove_from_inventory()
                else:
                    await member.add_roles(item.assigns_role)

            else:
                if new_item.exclusive_role:
                    if new_item.category == 'Uncategorized':
                        similar_items = [i for i in self.items if i.guild_id == new_item.guild_id and i.id != new_item.id]
                    else:
                        similar_items = [i for i in self.items if i.guild_id == new_item.guild_id and i.category == new_item.category and i.id != new_item.id]
                    
                    i_iter = AsyncIter([i for i in similar_items if i.assigns_role])
                    await bounded_gather(*[i.remove_from_inventory() async for i in i_iter])
                
                await member.add_roles(item.assigns_role)        
        return new_item

    async def purchase_item(self,item:ShopItem):
        member = item.guild.get_member(self.user.id)
        await item.purchase(member)
        item = await self.add_item_to_inventory(item)
        
        await bank.withdraw_credits(self.user,item.price)
        return item

    async def get_embed(self,ctx):
        inventory_text = ""
        user = None
        if isinstance(ctx,commands.Context):
            user = ctx.author
        if isinstance(ctx,discord.Interaction):
            user = ctx.user
        
        if len(self.items) > 0:
            a_iter = AsyncIter(self.items)
            async for item in a_iter:
                inventory_text += f"\n\n**{item.name}**"
                inventory_text += (f"\n{item.description}" if len(item.description) > 0 else "")
                if getattr(user,'id',None) == self.user.id:
                    if item.type in ['basic']:
                        inventory_text += f"\nPurchased from: {item.guild.name}"
                    if item.type in ['cash']:
                        inventory_text += f"\nRedeem this by talking to <@{bot_client.bot.user.id}>."
                    if item.type in ['role']:
                        inventory_text += f"\nGrants: {getattr(item.assigns_role,'mention','Unknown')}"
                    if item.subscription and item.expiration:
                        inventory_text += f"\nExpires: <t:{item.expiration.int_timestamp}:R>"                            

        embed = await clash_embed(
            context=ctx,
            title=f"{self.user.display_name}'s Inventory",
            message=f"**Total Items:** {len(self.items)}"
                + inventory_text
                + f"\n\u200b",
            thumbnail=self.user.display_avatar.with_static_format('png'),
            timestamp=pendulum.now()
            )
        return embed