import asyncio
import discord
import hashlib
import logging

from typing import *
from collections import defaultdict

from redbot.core.bot import Red
from redbot.core.utils import AsyncIter
from coc_main.client.global_client import GlobalClient
from coc_main.utils.components import ClanLinkMenu

LOG = logging.getLogger("coc.discord")

class GuildClanPanel(GlobalClient):
    _locks = defaultdict(asyncio.Lock)

    @classmethod
    async def get_for_guild(cls,guild_id:int) -> List['GuildClanPanel']:
        query = GlobalClient.database.db__guild_clan_panel.find({'server_id':guild_id})
        return [cls(panel) async for panel in query]

    @classmethod
    async def get_panel(cls,guild_id:int,channel_id:int) -> Optional['GuildClanPanel']:
        query = await GlobalClient.database.db__guild_clan_panel.find_one({'server_id':guild_id,'channel_id':channel_id})
        if query:
            return cls(query)
        return None
    
    def __init__(self,database_entry:dict):        
        self.id = database_entry.get('_id',None)
        self.guild_id = database_entry.get('server_id',0)
        self.channel_id = database_entry.get('channel_id',0)
        self.message_id = database_entry.get('message_id',0)
        self.long_message_ids = database_entry.get('long_message_ids',[])
        self.embeds = []
    
    def __str__(self):
        return f"Clan Panel (Channel: {getattr(self.channel,'name','Unknown Channel')})"
    
    @property
    def bot(self) -> Red:
        return GlobalClient.bot
    
    @classmethod
    async def create(cls,guild_id:int,channel_id:int):        
        await GlobalClient.database.db__guild_clan_panel.insert_one(
            {
                '_id':{'guild':guild_id,'channel':channel_id},
                'server_id':guild_id,
                'channel_id':channel_id
            }
        )
        return await cls.get_panel(guild_id,channel_id)
    
    async def delete(self):        
        await self.database.db__guild_clan_panel.delete_one({'_id':self.id})
        async for m_id in AsyncIter(self.long_message_ids):
            try:
                message = await self.channel.fetch_message(m_id)
            except discord.NotFound:
                pass
            else:
                await message.delete()
    @property
    def lock(self) -> asyncio.Lock:
        _id = f"{self.guild_id}-{self.channel_id}"
        h = hashlib.sha256(_id.encode()).hexdigest()
        return self._locks[h]
    @property
    def guild(self):
        return self.bot.get_guild(self.guild_id)    
    @property
    def channel(self):
        return self.bot.get_channel(self.channel_id)
    
    async def fetch_message(self):
        if self.channel:
            try:
                return await self.channel.fetch_message(self.message_id)
            except discord.NotFound:
                pass
        return None
    
    async def reset(self):
        async with self.lock:
            msg_iter = AsyncIter(self.long_message_ids)
            async for message_id in msg_iter:
                try:
                    message = await self.channel.fetch_message(message_id)
                except discord.NotFound:
                    continue
                else:
                    await message.delete()

            await self.database.db__guild_clan_panel.update_one(
                {'_id':self.id},
                {'$set':{
                    'message_id':0,
                    'long_message_ids':[]
                    }
                })
    
    async def send_to_discord(self,embeds:list[discord.Embed]):
        try:
            async with self.lock:
                if not self.channel:
                    self.delete()
                    return

                message_ids_master = []
                existing_messages = len(self.long_message_ids)

                #iterate through embeds up to len existing messages
                for i,send_message in enumerate(embeds[:existing_messages]):
                    link_button = ClanLinkMenu([send_message['clan']])
                    try:
                        message = await self.channel.fetch_message(self.long_message_ids[i])
                    except discord.NotFound:
                        message = await self.channel.send(
                            embed=send_message['embed'],
                            view=link_button
                            )
                        message_ids_master.append(message.id)
                    else:
                        message = await message.edit(
                            embed=send_message['embed'],
                            view=link_button
                            )
                        message_ids_master.append(message.id)
                
                #iterate through remaining embeds
                for send_message in embeds[existing_messages:]:
                    link_button = ClanLinkMenu([send_message['clan']])
                    message = await self.channel.send(
                        embed=send_message['embed'],
                        view=link_button
                        )
                    message_ids_master.append(message.id)
                
                #delete any remaining messages
                for message_id in self.long_message_ids[len(embeds):]:
                    try:
                        message = await self.channel.fetch_message(message_id)
                    except discord.NotFound:
                        pass
                    else:
                        await message.delete()
                
                await self.database.db__guild_clan_panel.update_one(
                    {'_id':self.id},
                    {'$set':{
                        'message_id':message_ids_master[0],
                        'long_message_ids':message_ids_master
                        }
                    })

        except Exception as exc:
            LOG.exception(
                f"Error sending Clan Panel to Discord: {self.guild.name} {getattr(self.channel,'name','Unknown Channel')}. {exc}"
                )