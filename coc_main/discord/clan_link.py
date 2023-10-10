import discord

from typing import *
from mongoengine import *

from ..api_client import BotClashClient as client
from ..coc_objects.clans.clan import BasicClan

from .mongo_discord import db_ClanGuildLink

bot_client = client()

class ClanGuildLink():

    @classmethod
    def get_link(cls,clan_tag:str,guild_id:int):
        try:
            return cls(db_ClanGuildLink.objects.get(tag=clan_tag,guild_id=guild_id))
        except DoesNotExist:
            return None
    
    @classmethod
    def get_clan_links(cls,clan_tag:str):
        return [cls(link) for link in db_ClanGuildLink.objects(tag=clan_tag)]
    
    def __init__(self,database_entry:db_ClanGuildLink):
        self.id = database_entry.link_id
        self.tag = database_entry.tag
        self.guild_id = database_entry.guild_id
        self._member_role = database_entry.member_role
        self._elder_role = database_entry.elder_role
        self._coleader_role = database_entry.coleader_role

    @classmethod
    async def create(cls,
        clan_tag:str,
        guild:discord.Guild,
        member_role:discord.Role,
        elder_role:discord.Role,
        coleader_role:discord.Role):

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
    def delete(cls,clan_tag:str,guild:discord.Guild):   
        db_ClanGuildLink.objects(tag=clan_tag,guild_id=guild.id).delete()
    
    @property
    def clan(self) -> BasicClan:
        return BasicClan(tag=self.tag)
    
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