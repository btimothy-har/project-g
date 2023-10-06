import discord

from mongoengine import *

from coc_client.api_client import BotClashClient
from redbot.core.utils import AsyncIter

bot_client = BotClashClient()

class db_ClanGuildLink(Document):
    #ID using format {'guild':int,'tag':#123}
    link_id = DictField(primary_key=True,required=True)
    tag = StringField(required=True)
    guild_id = IntField(required=True)
    member_role = IntField(default=0)
    elder_role = IntField(default=0)
    coleader_role = IntField(default=0)

class ClanGuildLink():
    def __init__(self,database_entry:db_ClanGuildLink):
        self.id = database_entry.link_id
        self.tag = database_entry.tag
        self.guild_id = database_entry.guild_id
        self._member_role = database_entry.member_role
        self._elder_role = database_entry.elder_role
        self._coleader_role = database_entry.coleader_role

    @classmethod
    def get_link(cls,clan_tag:str,guild_id:int):
        try:
            return cls(db_ClanGuildLink.objects.get(tag=clan_tag,guild_id=guild_id))
        except DoesNotExist:
            return None
    
    @classmethod
    def get_clan_links(cls,clan_tag:str):
        return [cls(link) for link in db_ClanGuildLink.objects(tag=clan_tag)]

    @classmethod
    def get_guild_links(cls,guild_id:int):
        return [cls(link) for link in db_ClanGuildLink.objects(guild_id=guild_id)]

    @classmethod
    async def create(cls,
        clan_tag:str,
        guild:discord.Guild,
        member_role:discord.Role,
        elder_role:discord.Role,
        coleader_role:discord.Role
        ):
        link_id = {'guild':guild.id,'tag':clan_tag}
        guild_link = db_ClanGuildLink(
            link_id = link_id,
            tag = clan_tag,
            guild_id = guild.id,
            member_role = member_role.id,
            elder_role = elder_role.id,
            coleader_role = coleader_role.id
            )
        guild_link.save()
        return cls(guild_link)
    
    @classmethod
    async def delete(cls,clan_tag:str,guild:discord.Guild):        
        links = ClanGuildLink.get_link(clan_tag,guild.id)
        if len(links) == 0:
            return
        
        async for link in AsyncIter(links):
            link.delete()
    
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