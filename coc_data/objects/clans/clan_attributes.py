import asyncio

from typing import *
from mongoengine import *

from redbot.core.utils import chat_formatting as chat

from coc_client.api_client import BotClashClient

from ...constants.coc_constants import *
from ...constants.coc_emojis import *
from ...exceptions import *

##################################################
#####
##### DATABASE
#####
##################################################
class db_Clan(Document):
    tag = StringField(primary_key=True,required=True)
    abbreviation = StringField(default="")
    emoji = StringField(default="")

class db_AllianceClan(Document):
    tag = StringField(primary_key=True,required=True)
    description = StringField(default="")
    recruitment_level = ListField(IntField(),default=[])
    recruitment_info = StringField(default="")
    leader = IntField(default=0)
    coleaders = ListField(IntField(),default=[])
    elders = ListField(IntField(),default=[])
    
    #deprecated
    announcement_channel = IntField(default=0)
    member_role = IntField(default=0)
    home_guild = IntField(default=0)
    elder_role = IntField(default=0)
    coleader_role = IntField(default=0)

##################################################
#####
##### CLAN ATTRIBUTES OBJECT
#####
##################################################
class _ClanAttributes():
    _cache = {}

    def __new__(cls,clan):
        if clan.tag not in cls._cache:
            instance = super().__new__(cls)
            instance._is_new = True
            cls._cache[clan.tag] = instance
        return cls._cache[clan.tag]
    
    def __init__(self,clan):
        self.client = BotClashClient()

        self.bot = clan.bot
        self.clan = clan
        self.tag = clan.tag
        self.name = clan.name
        
        if self._is_new:
            self.load()        
        self._is_new = False
    
    def __str__(self):
        return str(self.clan)
    
    def load(self):
        self._is_registered_clan = False
        self._abbreviation = ""
        self._emoji = ""

        self._is_alliance_clan = False
        self._description = ""
        self._recruitment_level = []
        self._recruitment_info = ""
        
        self._leader = 0
        self._coleaders = []
        self._elders = []

        self._balance = 0
        self._bank_lock = asyncio.Lock()

        if self.tag == None:
            return

        try:
            db_clan = db_Clan.objects.get(tag=self.tag).to_mongo().to_dict()
        except DoesNotExist:
            pass
        else:
            self._is_registered_clan = True
            self._abbreviation = db_clan.get('abbreviation','')
            self._emoji = db_clan.get('emoji','')
        
        try:
            db_alliance_clan = db_AllianceClan.objects.get(tag=self.tag).to_mongo().to_dict()
        except DoesNotExist:
            pass
        else:
            self._is_alliance_clan = True            
            self._description = db_alliance_clan.get('description','')
            self._recruitment_level = db_alliance_clan.get('recruitment_level',[])
            self._recruitment_info = db_alliance_clan.get('recruitment_info','')

            self._leader = db_alliance_clan.get('leader',0)
            self._coleaders = db_alliance_clan.get('coleaders',[])
            self._elders = db_alliance_clan.get('elders',[])
    
    def save_attributes(self):
        try:
            db_clan = db_Clan.objects.get(tag=self.tag)
        except DoesNotExist:
            db_clan = db_Clan(tag=self.tag)
        
        db_clan.abbreviation = self._abbreviation
        db_clan.emoji = self._emoji
        db_clan.save()
    
    def save_alliance_clan(self):      
        try:
            db_alliance_clan = db_AllianceClan.objects.get(tag=self.tag)
        except DoesNotExist:
            db_alliance_clan = db_AllianceClan(tag=self.tag)
        
        db_alliance_clan.description = self._description
        db_alliance_clan.recruitment_level = self._recruitment_level
        db_alliance_clan.recruitment_info = self._recruitment_info
        db_alliance_clan.leader = self._leader
        db_alliance_clan.coleaders = self._coleaders
        db_alliance_clan.elders = self._elders
        db_alliance_clan.save()
    
    @property
    def is_registered_clan(self):
        return self._is_registered_clan
    
    @property
    def abbreviation(self):
        return self._abbreviation
    @abbreviation.setter
    def abbreviation(self,new_abbreviation:str):
        self._abbreviation = new_abbreviation.upper()
        self.client.cog.coc_data_log.info(f"Clan {self}: abbreviation changed to {new_abbreviation.upper()}.")
        self.save_attributes()        
        self.load()

    @property
    def emoji(self) -> str:
        return self._emoji
    @emoji.setter
    def emoji(self,new_emoji:str):
        self._emoji = new_emoji
        self.client.cog.coc_data_log.info(f"Clan {self}: emoji changed to {new_emoji}.")
        self.save_attributes()
        self.load()
    
    @property
    def is_alliance_clan(self):
        return self._is_alliance_clan
    @is_alliance_clan.setter
    def is_alliance_clan(self,boolean:bool):
        if boolean == True:
            self.save_alliance_clan()
        elif boolean == False:
            try:
                db_clan = db_Clan.objects.get(tag=self.tag)
            except DoesNotExist:
                pass
            else:
                db_clan.delete()
            try:
                db_alliance_clan = db_AllianceClan.objects.get(tag=self.tag)
            except DoesNotExist:
                pass
            else:
                db_alliance_clan.delete()
        self.load()
        self.client.cog.coc_data_log.info(f"Clan {self}: is_alliance_clan changed to {boolean}.")
    
    @property
    def description(self):
        if len(self._description) > 0:
            return self._description
        else:
            return self.clan.description
    @description.setter
    def description(self,description:str):
        self._description = description
        self.save_alliance_clan()
        self.client.cog.coc_data_log.info(f"Clan {self}: description changed to {description}.")
    
    @property
    def recruitment_level(self):
        return self._recruitment_level
    @recruitment_level.setter
    def recruitment_level(self,recruitment_level:list[int]):
        self._recruitment_level = list(set(recruitment_level))
        self.save_alliance_clan()
        self.client.cog.coc_data_log.info(f"Clan {self}: recruitment_level changed to {self._recruitment_level}.")
    
    @property
    def recruitment_info(self):
        return self._recruitment_info
    @recruitment_info.setter
    def recruitment_info(self,recruitment_info:str):
        self._recruitment_info = recruitment_info
        self.save_alliance_clan()
        self.client.cog.coc_data_log.info(f"Clan {self}: recruitment_info changed to {recruitment_info}.")
    
    @property
    def leader(self):
        return self._leader
    @leader.setter
    def leader(self,leader:int):
        self._leader = leader
        self.save_alliance_clan()
        self.client.cog.coc_data_log.info(f"Clan {self}: leader changed to {leader}.")
    
    @property
    def coleaders(self) -> list[int]:
        return self._coleaders
    @coleaders.setter
    def coleaders(self,new_coleaders:list[int]):
        self._coleaders = list(set(new_coleaders))
        self.client.cog.coc_data_log.info(f"Clan {self}: coleaders changed to {chat.humanize_list(new_coleaders)}.")
        self.save_alliance_clan()
            
    @property
    def elders(self) -> list[int]:
        return self._elders
    @elders.setter
    def elders(self,new_elders:list[int]):
        self._elders = list(set(new_elders))
        self.client.cog.coc_data_log.info(f"Clan {self}: elders changed to {chat.humanize_list(new_elders)}.")
        self.save_alliance_clan()