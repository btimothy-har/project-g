import discord

from typing import *
from mongoengine import *

from coc_client.api_client import BotClashClient

from ...constants.coc_constants import *
from ...constants.coc_emojis import *
from ...exceptions import *

##################################################
#####
##### DATABASE
#####
##################################################
class db_WarLeagueClanSetup(Document):
    tag = StringField(primary_key=True,required=True)
    is_active = BooleanField(default=False)
    role = IntField(default=0)
    channel = IntField(default=0)

    #deprecated
    webhook = IntField(default=0)

##################################################
#####
##### CLAN CWL ATTRIBUTES OBJECT
#####
##################################################
class _ClanCWLConfig():
    _cache = {}

    def __new__(cls,clan):
        if clan.tag not in cls._cache:
            instance = super().__new__(cls)
            instance._is_new = True
            cls._cache[clan.tag] = instance
        return cls._cache[clan.tag]
    
    def __init__(self,clan):
        self.client = BotClashClient()
        self.bot = self.client.bot

        if self._is_new:
            self.tag = clan.tag
            self.name = clan.name
            self.load()

        self._is_new = False        
    
    def load(self):
        self._is_cwl_clan = False
        self._cwl_channel = 0
        self._cwl_role = 0
        
        if self.tag == None:
            return
        try:
            db_clan = db_WarLeagueClanSetup.objects.get(tag=self.tag).to_mongo().to_dict()
        except DoesNotExist:
            pass
        else:
            self._is_cwl_clan = db_clan.get('is_active',False)
            self._cwl_channel = db_clan.get('channel',0)
            self._cwl_role = db_clan.get('role',0)
    
    ##################################################
    ### CLASS PROPERTIES
    ##################################################    
    @property
    def is_cwl_clan(self) -> bool:
        return self._is_cwl_clan
    @is_cwl_clan.setter
    def is_cwl_clan(self,is_cwl_clan:bool):
        self._is_cwl_clan = is_cwl_clan
        try:
            db_clan = db_WarLeagueClanSetup.objects.get(tag=self.tag)
        except DoesNotExist:
            db_clan = db_WarLeagueClanSetup(tag=self.tag)
        db_clan.is_active = self._is_cwl_clan
        db_clan.save()
        
    @property
    def channel(self) -> Optional[Union[discord.abc.GuildChannel,discord.Thread]]:
        channel = self.bot.get_channel(self._cwl_channel)
        if isinstance(channel,(discord.TextChannel,discord.Thread)):
            return channel
        return None
    @channel.setter
    def channel(self,channel_id:int):
        channel = self.bot.get_channel(channel_id)
        if isinstance(channel,(discord.TextChannel,discord.Thread)):
            self._cwl_channel = channel.id
        else:
            self._cwl_channel = 0
        try:
            db_clan = db_WarLeagueClanSetup.objects.get(tag=self.tag)
        except DoesNotExist:
            db_clan = db_WarLeagueClanSetup(tag=self.tag)
        db_clan.channel = self._cwl_channel
        db_clan.save()
    
    @property
    def role(self) -> Optional[discord.Role]:
        for guild in self.bot.guilds:
            role = guild.get_role(self._cwl_role)
            if isinstance(role,discord.Role):
                return role
        return None
    @role.setter
    def role(self,role_id:int):
        for guild in self.bot.guilds:
            role = guild.get_role(role_id)
            if isinstance(role,discord.Role):
                self._cwl_role = role.id
                break
        else:
            self._cwl_role = 0
        try:
            db_clan = db_WarLeagueClanSetup.objects.get(tag=self.tag)
        except DoesNotExist:
            db_clan = db_WarLeagueClanSetup(tag=self.tag)
        db_clan.role = self._cwl_role
        db_clan.save()