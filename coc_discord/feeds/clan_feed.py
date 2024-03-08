import discord
import bson

from typing import *
from redbot.core.bot import Red

from coc_main.client.global_client import GlobalClient
from coc_main.coc_objects.clans.clan import BasicClan, aClan

feed_description = {
    1: "Member Join/Leave",
    2: "Donation Log",
    3: "Raid Weekend Results"
    }

class ClanDataFeed(GlobalClient):

    @classmethod
    async def get_by_id(cls,id:str) -> 'ClanDataFeed':
        query = await cls.database.db__clan_data_feed.find_one({'_id':bson.ObjectId(id)})
        return cls(query) if query else None

    @classmethod
    async def feeds_for_clan(cls,clan:aClan,type:Optional[int]=None) -> List['ClanDataFeed']:        
        if type:
            query = cls.database.db__clan_data_feed.find({'tag':clan.tag,'type':type})
        else:
            query = cls.database.db__clan_data_feed.find({'tag':clan.tag})
        return [cls(q) async for q in query]
    
    @classmethod
    async def get_all(cls) -> List['ClanDataFeed']:        
        query = cls.database.db__clan_data_feed.find({})
        return [cls(q) async for q in query]

    @classmethod
    async def create_feed(cls,
        clan:BasicClan,
        channel:Union[discord.TextChannel,discord.Thread],
        type:int) -> 'ClanDataFeed':

        feed = await cls.database.db__clan_data_feed.insert_one(
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
        self.tag = database['tag']
        self.type = database['type']
        self.guild_id = database['guild_id']
        self.channel_id = database['channel_id']
    
    async def delete(self):
        await self.database.db__clan_data_feed.delete_one({'_id':bson.ObjectId(self._id)})

    @property
    def description(self) -> str:
        return feed_description.get(self.type,'Unknown Feed Type')
    
    @property
    def bot(self) -> Red:
        return GlobalClient.bot    
    @property
    def guild(self) -> Optional[discord.Guild]:
        return self.bot.get_guild(self.guild_id)    
    @property
    def channel(self) -> Optional[discord.TextChannel]:
        return self.bot.get_channel(self.channel_id)