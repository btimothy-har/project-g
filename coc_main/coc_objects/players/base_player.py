import coc
import pendulum

from typing import *
from mongoengine import *

from ...api_client import BotClashClient as client
from .mongo_player import db_Player

from ...utils.constants.coc_emojis import EmojisTownHall
from ...utils.constants.ui_emojis import EmojisUI
from ...utils.utils import check_rtl

from ..clans.player_clan import *

bot_client = client()

class BasicPlayer():
    """
    This is a Player wrapper for Project G Player attributes and methods.

    Inheriting from this Class: aPlayer
    """
    def __init__(self,**kwargs):
        self.timestamp = pendulum.now()

        self.tag = kwargs.get('tag',None)
        self.name = kwargs.get('name','None')

        self.exp_level = 0
        self.town_hall_level = 0        

        if self.tag:
            self.tag = coc.utils.correct_tag(self.tag)
            self.name = self.cached_name
            self.exp_level = self.cached_xp_level
            self.town_hall_level = self.cached_townhall

            bot_client.player_cache.add_to_queue(self.tag)
    
    def __str__(self):
        return f"Player {self.tag} ({self.name})"

    @property
    def clean_name(self) -> str:
        if check_rtl(self.name):
            return '\u200F' + self.name + '\u200E'
        return self.name
    
    ##################################################
    #####
    ##### PLAYER METHODS
    #####
    ##################################################  
    @classmethod
    def add_link(cls,tag,discord_user:int):
        player = cls(tag=coc.utils.correct_tag(tag))
        player.discord_user = discord_user  

    def new_member(self,user_id:int,home_clan:BasicClan):
        if not self.is_member or not self.last_joined:
            self.last_joined = pendulum.now()

        self.home_clan = home_clan
        self.discord_user = user_id
        self.is_member = True
        bot_client.coc_data_log.info(f"Player {self} is now an Alliance member!")

    def remove_member(self):
        self.home_clan = aPlayerClan()
        self.is_member = False
        self.last_removed = pendulum.now()
        bot_client.coc_data_log.info(f"Player {self} has been removed as a member.")

    @property
    def share_link(self) -> str:
        return f"https://link.clashofclans.com/en?action=OpenPlayerProfile&tag=%23{self.tag.strip('#')}"
    
    ##################################################
    #####
    ##### CACHED VALUES
    #####
    ##################################################    
    @property
    def cached_name(self) -> str:
        return getattr(self.database_attributes,'name',"")
    @cached_name.setter
    def cached_name(self,new_name:str):
        db_Player.objects(tag=self.tag).update_one(set__name=new_name,upsert=True)
        bot_client.coc_data_log.debug(f"{self}: cached_name changed to {new_name}.")
    
    @property
    def cached_xp_level(self) -> int:
        return getattr(self.database_attributes,'xp_level',0)
    @cached_xp_level.setter
    def cached_xp_level(self,new_value:int):
        db_Player.objects(tag=self.tag).update_one(set__xp_level=new_value,upsert=True)
        bot_client.coc_data_log.debug(f"{self}: cached_xp_level changed to {new_value}.")
    
    @property
    def cached_townhall(self) -> int:
        return getattr(self.database_attributes,'townhall',0)
    @cached_townhall.setter
    def cached_townhall(self,new_value:int):
        db_Player.objects(tag=self.tag).update_one(set__townhall=new_value,upsert=True)
        bot_client.coc_data_log.debug(f"{self}: cached_townhall changed to {new_value}.")

    @property
    def title(self):
        return f"{EmojisTownHall.get(self.town_hall_level)} {self.name} ({self.tag})"
    
    ##################################################
    #####
    ##### PLAYER DATABASE ATTRIBUTES
    #####
    ##################################################    
    @property
    def database_attributes(self) -> Optional[db_Player]:
        try:
            return db_Player.objects.get(tag=self.tag)
        except DoesNotExist:
            return None
    
    @property
    def is_new(self) -> bool:
        return True if not self.first_seen else False
    
    @property
    def discord_user(self) -> int:
        return getattr(self.database_attributes,'discord_user',0)
    @discord_user.setter
    def discord_user(self,new_value:int):
        db_Player.objects(tag=self.tag).update_one(set__discord_user=new_value,upsert=True)
        bot_client.coc_data_log.info(f"{self}: discord_user changed to {new_value}.")

    @property
    def discord_user_str(self):
        return f"{EmojisUI.DISCORD} <@{str(self.discord_user)}>" if self.discord_user else ""

    @property
    def is_member(self) -> bool:
        val = getattr(self.database_attributes,'is_member',False)
        if val and not getattr(self.home_clan,'is_alliance_clan',False):
            self.remove_member()
            bot_client.coc_data_log.info(f"{self}: Removed as Member as their previous Home Clan is no longer recognized as an Alliance clan.")
            return False
        return val
    @is_member.setter
    def is_member(self,new_value:bool):
        db_Player.objects(tag=self.tag).update_one(set__is_member=new_value,upsert=True)
        bot_client.coc_data_log.info(f"{self}: is_member changed to {new_value}.")
    
    @property
    def home_clan(self) -> Optional[aPlayerClan]:
        if getattr(self.database_attributes,'home_clan',None):
            return aPlayerClan(tag=self.database_attributes.home_clan)
        return aPlayerClan()
    @home_clan.setter
    def home_clan(self,new_value:aPlayerClan):
        db_Player.objects(tag=self.tag).update_one(set__home_clan=new_value.tag,upsert=True)
        bot_client.coc_data_log.info(f"{self}: home_clan changed to {new_value}.")
    
    @property
    def alliance_rank(self) -> str:
        if self.is_member:
            if self.discord_user == self.home_clan.leader:
                rank = 'Leader'
            elif self.discord_user in self.home_clan.coleaders:
                rank = 'Co-Leader'
            elif self.discord_user in self.home_clan.elders:
                rank = 'Elder'
            else:
                rank = 'Member'
        else:
            rank = 'Non-Member'
        return rank
    
    @property
    def first_seen(self) -> Optional[pendulum.DateTime]:
        if getattr(self.database_attributes,'first_seen',0):
            return pendulum.from_timestamp(self.database_attributes.first_seen)       
        return None
    @first_seen.setter
    def first_seen(self,new_value:pendulum.DateTime):
        db_Player.objects(tag=self.tag).update_one(set__first_seen=new_value.int_timestamp,upsert=True)
        bot_client.coc_data_log.debug(f"{self}: first_seen changed to {new_value}.")
    
    @property
    def last_joined(self) -> Optional[pendulum.DateTime]:
        if getattr(self.database_attributes,'last_joined',0):
            return pendulum.from_timestamp(self.database_attributes.last_joined)
        return None
    @last_joined.setter
    def last_joined(self,new_value:pendulum.DateTime):
        db_Player.objects(tag=self.tag).update_one(set__last_joined=new_value.int_timestamp,upsert=True)
        bot_client.coc_data_log.info(f"{self}: last_joined changed to {new_value}.")
    
    @property
    def last_removed(self) -> Optional[pendulum.DateTime]:
        if getattr(self.database_attributes,'last_removed',0):
            return pendulum.from_timestamp(self.database_attributes.last_removed)
        return None
    @last_removed.setter
    def last_removed(self,new_value:pendulum.DateTime):
        db_Player.objects(tag=self.tag).update_one(set__last_joined=new_value.int_timestamp,upsert=True)
        bot_client.coc_data_log.info(f"{self}: last_removed changed to {new_value}.")
    
    @property
    def member_description(self):
        if self.is_member:
            return f"{self.home_clan.emoji} {self.alliance_rank} of {self.home_clan.name}"
        return ""
        
    @property
    def member_description_no_emoji(self) -> str:
        if self.is_member:
            return f"{self.alliance_rank} of {self.home_clan.name}"
        return ""