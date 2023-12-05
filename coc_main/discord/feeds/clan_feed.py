import discord
import bson

from typing import *
from functools import cached_property

from ...api_client import BotClashClient as client
from ...coc_objects.clans.clan import BasicClan

bot_client = client()

feed_description = {
    1: "Member Join/Leave",
    2: "Donation Log",
    3: "Raid Weekend Results"
    }

class ClanDataFeed():
    @classmethod
    async def get_by_id(cls,id:str) -> 'ClanDataFeed':
        query = await bot_client.coc_db.db__clan_data_feed.find_one({'_id':bson.ObjectId(id)})
        return cls(query) if query else None

    @classmethod
    async def feeds_for_clan(cls,clan:BasicClan,type:Optional[int]=None) -> List['ClanDataFeed']:        
        if type:
            query = bot_client.coc_db.db__clan_data_feed.find({'tag':clan.tag,'type':type})
        else:
            query = bot_client.coc_db.db__clan_data_feed.find({'tag':clan.tag})
        return [cls(q) async for q in query]

    @classmethod
    async def create_feed(cls,
        clan:BasicClan,
        channel:Union[discord.TextChannel,discord.Thread],
        type:int) -> 'ClanDataFeed':

        feed = await bot_client.coc_db.db__clan_data_feed.insert_one(
            {
                'tag':clan.tag,
                'type':type,
                'guild_id':channel.guild.id,
                'channel_id':channel.id
                }    
            )
        return await cls.get_by_id(feed.inserted_id)

    def __init__(self,database:dict):
        self._id = str(database['_id'])
        self.type = database['type']
        self.guild_id = database['guild_id']
        self.channel_id = database['channel_id']
    
    async def delete(self):
        await bot_client.coc_db.db__clan_data_feed.delete_one({'_id':bson.ObjectId(self._id)})

    @cached_property
    def description(self) -> str:
        return feed_description.get(self.type,'Unknown Feed Type')
    
    @cached_property
    def guild(self) -> Optional[discord.Guild]:
        return bot_client.bot.get_guild(self.guild_id)
    
    @cached_property
    def channel(self) -> Optional[discord.TextChannel]:
        if not self.guild:
            return None
        return self.guild.get_channel(self.channel_id)
    