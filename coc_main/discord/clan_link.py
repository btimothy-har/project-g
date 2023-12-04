import discord

from typing import *
from async_property import async_cached_property

from ..api_client import BotClashClient as client
from ..coc_objects.clans.clan import BasicClan

bot_client = client()

class ClanGuildLink():
    @classmethod
    async def get_link(cls,clan_tag:str,guild_id:int) -> Optional['ClanGuildLink']:
        link = await bot_client.coc_db.db__clan_guild_link.find_one(
            {
                'tag':clan_tag,
                'guild_id':guild_id
                }
            )
        if link:
            return cls(link)
        return None
    
    @classmethod
    async def get_links_for_clan(cls,clan_tag:str):
        query = bot_client.coc_db.db__clan_guild_link.find(
            {
                'tag':clan_tag
                }
            )
        return [cls(link) async for link in query]

    @classmethod
    async def get_for_guild(cls,guild_id:int):
        query = bot_client.coc_db.db__clan_guild_link.find(
            {
                'guild_id':guild_id
                }
            )
        return [cls(link) async for link in query]
    
    def __init__(self,database_dict:dict):
        self.id = database_dict.get('_id',None)
        self.tag = database_dict.get('tag',None)
        self.guild_id = database_dict.get('guild_id',0)
        self._member_role = database_dict.get('member_role',0)
        self._elder_role = database_dict.get('elder_role',0)
        self._coleader_role = database_dict.get('coleader_role',0)

    @classmethod
    async def create(cls,
        clan_tag:str,
        guild:discord.Guild,
        member_role:discord.Role,
        elder_role:discord.Role,
        coleader_role:discord.Role):

        link_id = {'guild':guild.id,'tag':clan_tag}
        await bot_client.coc_db.db__clan_guild_link.insert_one(
            {
            '_id':link_id,
            'tag':clan_tag,
            'guild_id':guild.id,
            'member_role':member_role.id,
            'elder_role':elder_role.id,
            'coleader_role':coleader_role.id
        }
        )
        return await cls.get_link(clan_tag,guild.id)
    
    @classmethod
    async def delete(cls,clan_tag:str,guild:discord.Guild):
        await bot_client.coc_db.db__clan_guild_link.delete_one({'tag':clan_tag,'guild_id':guild.id})
    
    @async_cached_property
    async def clan(self) -> BasicClan:
        return await BasicClan(tag=self.tag)
    
    @property
    def guild(self) -> discord.Guild:
        return bot_client.bot.get_guild(self.guild_id)
    
    @property
    def member_role(self) -> discord.Role:
        if self.guild: 
            return self.guild.get_role(self._member_role)
        return None

    @property
    def elder_role(self) -> discord.Role:
        if self.guild: 
            return self.guild.get_role(self._elder_role)
        return None
    
    @property
    def coleader_role(self) -> discord.Role:
        if self.guild: 
            return self.guild.get_role(self._coleader_role)
        return None