import asyncio
import pendulum
import bson
import discord

from typing import *

from redbot.core import commands
from pymongo import ReturnDocument
from collections import defaultdict
from coc_main.api_client import BotClashClient
from coc_main.cog_coc_client import ClashOfClansClient

from coc_main.utils.components import clash_embed
from coc_main.utils.constants.coc_emojis import EmojisClash

from .inventory import InventoryItem
from .item import ShopItem

# db__redemption = {
#   '_id': ObjectId(),
#   'user_id': int,
#   'item_id': str,
#   'goldpass_tag': str,
#   'open_timestamp': int,
#   'close_user': int,
#   'close_timestamp': int,
#   }

bot_client = BotClashClient()

class RedemptionTicket():
    _locks = defaultdict(asyncio.Lock)
    __slots__ = [
        '_id',
        'id',
        'channel_id',
        'user_id',
        'item_id',
        'goldpass_tag',
        'open_timestamp',
        'close_user',
        'close_timestamp',
        ]
    
    @property
    def coc_client(self) -> ClashOfClansClient:
        return bot_client.bot.get_cog("ClashOfClansClient")
    
    @classmethod
    async def get_by_id(cls,ticket_id:str) -> Optional['RedemptionTicket']:        
        query = await bot_client.coc_db.db__redemption.find_one({'_id':bson.ObjectId(ticket_id)})
        if query:
            return cls(query)
        return None
    
    def __init__(self,database_entry:dict):
        self._id = database_entry['_id']
        self.id = str(database_entry['_id'])

        self.user_id = database_entry['user_id']
        self.item_id = database_entry['item_id']

        self.channel_id = database_entry.get('channel_id',None)
        self.goldpass_tag = database_entry.get('goldpass_tag',None)

        self.open_timestamp = pendulum.from_timestamp(database_entry['open_timestamp'])
        
        ct = database_entry.get('close_timestamp',None)
        self.close_timestamp = pendulum.from_timestamp(ct) if ct else None

        self.close_user = database_entry.get('close_user',None)
    
    @property
    def lock(self) -> asyncio.Lock:
        return self._locks[self.id]
    
    @property
    def bank_cog(self) -> commands.Cog:
        return bot_client.bot.get_cog("Bank")
    
    @property
    def user(self) -> Optional[discord.Member]:
        return self.bank_cog.bank_guild.get_member(self.user_id)
    
    @property
    def channel(self) -> Optional[discord.TextChannel]:
        return self.bank_cog.bank_guild.get_channel(self.channel_id)
    
    @classmethod
    async def create(cls,cog:commands.Cog,user_id:int,item_id:str,goldpass_tag:str=None):
        query = {
            'user_id': user_id,
            'item_id': item_id,
            'goldpass_tag': goldpass_tag,
            'open_timestamp': pendulum.now().int_timestamp,
            }
        new_ticket = await bot_client.coc_db.db__redemption.insert_one(query)

        ticket_id = str(new_ticket.inserted_id)
        await cog.redemption_log_channel.send(f"--ticket {ticket_id} {user_id}")

        count = 0
        while True:
            count += 1
            await asyncio.sleep(0.2)
            ticket = await RedemptionTicket.get_by_id(ticket_id)
            if ticket.channel:
                break
            if count > 20:
                break
        bot_client.coc_main_log.info(f"New redemption ticket: {ticket.id}")
        return ticket

    async def update_channel(self,channel_id:int):
        async with self.lock:
            await bot_client.coc_db.db__redemption.update_one(
                {'_id':self._id},
                {'$set':{'channel_id': channel_id}},
                )
            self.channel_id = channel_id
    
    async def complete_redemption(self,user_id:int) -> 'RedemptionTicket':
        async with self.lock:
            ticket = await RedemptionTicket.get_by_id(self.id)

            if not ticket.close_user:
                new_doc = await bot_client.coc_db.db__redemption.find_one_and_update(
                    {'_id':self._id},
                    {'$set':{
                        'close_user': user_id,
                        'close_timestamp': pendulum.now().int_timestamp,
                        }},
                    return_document=ReturnDocument.AFTER
                    )
                self.close_user = new_doc['close_user']
                self.close_timestamp = pendulum.from_timestamp(new_doc['close_timestamp'])        

            item = await self.get_item()
            await item.remove_from_inventory()
        return self
    
    async def reverse_redemption(self) -> 'RedemptionTicket':
        async with self.lock:
            ticket = await RedemptionTicket.get_by_id(self.id)
            
            if ticket.close_user:
                await bot_client.coc_db.db__redemption.update_one(
                    {'_id':self._id},
                    {'$set':{
                        'close_user': None,
                        'close_timestamp': None,
                        }},
                    )
                self.close_user = None
                self.close_timestamp = None
                
            item = await self.get_item()
            await item.reinstate()
        return self
    
    async def get_item(self) -> Optional[InventoryItem]:
        return await InventoryItem.get_by_id(self.item_id)
    
    async def get_embed(self):
        gp_account = await self.coc_client.fetch_player(self.goldpass_tag) if self.goldpass_tag else None
        item = await self.get_item()

        embed = await clash_embed(
            context=bot_client.bot,
            title=f"Redemption: {getattr(self.user,'display_name','Unknown User')}",
            message=f"Ticket ID: `{self.id}`"
                + f"\nUser: {getattr(self.user,'mention','Unknown User')}"
                + (f"\n{EmojisClash.GOLDPASS} [{gp_account.title}]({gp_account.share_link})" if gp_account else ""),
            timestamp=self.open_timestamp,
            )
        embed.add_field(
            name=f"Redeeming: {item.name}",
            value=f"`{self.item_id}`"
                + f"\n{item.description}",
            inline=True,
            )
        return embed