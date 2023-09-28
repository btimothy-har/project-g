import pendulum

from typing import *
from mongoengine import *

from coc_client.api_client import BotClashClient

from ..clans.clan import aClan

from ...constants.coc_constants import *
from ...constants.coc_emojis import *
from ...exceptions import *

##################################################
#####
##### DATABASE
#####
##################################################
class db_Player(Document):
    tag = StringField(primary_key=True,required=True)
    name = StringField(default="",required=True)
    discord_user = IntField(default=0)
    is_member = BooleanField(default=False)
    home_clan = StringField(default="")
    first_seen = IntField(default=0)
    last_joined = IntField(default=0)
    last_removed = IntField(default=0)

##################################################
#####
##### PLAYER ATTRIBUTES OBJECT
#####
##################################################
class _PlayerAttributes():
    _cache = {}

    def __new__(cls,player):
        if player.tag not in cls._cache:
            instance = super().__new__(cls)
            instance._is_new = True
            cls._cache[player.tag] = instance
        return cls._cache[player.tag]
    
    def __init__(self,player):
        self.bot = player.bot
        self.client = BotClashClient()
        self.tag = player.tag
        self.name = player.name

        if self._is_new:
            player_database = None
            try:
                player_database = db_Player.objects.get(tag=self.tag).to_mongo().to_dict()
            except DoesNotExist:
                self._new_player = True
                self._discord_user = 0
                self._is_member = False
                self._home_clan_tag = None
                self._first_seen = player.timestamp.int_timestamp
                self._last_joined = None
                self._last_removed = None
            else:
                player_database = db_Player.objects.get(tag=self.tag).to_mongo().to_dict()
            
            if player_database:
                self._new_player = False
                self._discord_user = player_database.get('discord_user',0)
                self._is_member = player_database.get('is_member',False)
                self._home_clan_tag = player_database.get('home_clan',None)
                self._first_seen = player_database.get('first_seen',0)
                self._last_joined = player_database.get('last_joined',0)
                self._last_removed = player_database.get('last_removed',0)
        
            self._is_new = False
    
    def __str__(self):
        return f"{self.name} ({self.tag})"
    def __eq__(self,other):
        return isinstance(other,_PlayerAttributes) and self.tag == other.tag    
    def __hash__(self):
        return hash(self.tag)
    
    def save(self):
        self._new_player = False
        player_data = db_Player(
            tag=self.tag,
            name=self.name,
            discord_user=self._discord_user,
            is_member=self._is_member,
            home_clan=self._home_clan_tag,
            first_seen=self._first_seen,
            last_joined=self._last_joined,
            last_removed=self._last_removed
            )
        player_data.save()
        self.client.cog.coc_data_log.info(
            f'Player {self.name} ({self.tag}): attributes saved to database.'
            )
    
    @property
    def discord_user(self) -> int:
        return getattr(self,'_discord_user',0)
    @discord_user.setter
    def discord_user(self,discord_user_id:int):
        self.client.cog.coc_data_log.info(
            f"Player {self}: discord_user set to {discord_user_id}. Previous value: {getattr(self,'_discord_user',0)}."
            )
        self._discord_user = discord_user_id
        self.save()

    @property
    def is_member(self) -> bool:
        val = getattr(self,'_is_member',False)
        try:
            home_clan = self.home_clan
        except CacheNotReady:
            return val
        else:
            if val and not getattr(home_clan,'is_alliance_clan',False):
                self.client.cog.coc_data_log.info(
                    f"Player {self}: Removing as Member as their previous Home Clan is no longer recognized as an Alliance clan."
                    )
                self.player.remove_member()
            return val
    @is_member.setter
    def is_member(self,member_boolean:bool):
        self.client.cog.coc_data_log.info(
            f"Player {self}: is_member set to {member_boolean}. Previous value: {getattr(self,'_is_member',False)}."
            )
        self._is_member = member_boolean
        self.save()
    
    @property
    def home_clan(self):
        tag = getattr(self,'_home_clan_tag',None)
        if tag:
            return aClan.from_cache(tag)
        return aClan()
    @home_clan.setter
    def home_clan(self,clan):
        self.client.cog.coc_data_log.info(
            f"Player {self}: home_clan set to {getattr(clan,'tag')}. Previous value: {getattr(self.home_clan,'tag',None)}."
            )
        self._home_clan_tag = getattr(clan,'tag',None)
        self.save()
    
    @property
    def first_seen(self):
        ts = getattr(self,'_first_seen',0)
        return None if ts == 0 else pendulum.from_timestamp(ts)
    @first_seen.setter
    def first_seen(self,datetime:pendulum.datetime):
        self._first_seen = datetime.int_timestamp
        self.client.cog.coc_data_log.info(
            f"Player {self}: first_seen set to {datetime}."
            )
        self.save()

    @property
    def last_joined(self):
        ts = getattr(self,'_last_joined',0)
        return None if ts == 0 else pendulum.from_timestamp(ts)
    @last_joined.setter
    def last_joined(self,datetime:pendulum.datetime):
        self._last_joined = datetime.int_timestamp
        self.client.cog.coc_data_log.info(
            f"Player {self}: last_joined set to {datetime}."
            )
        self.save()

    @property
    def last_removed(self):
        ts = getattr(self,'_last_removed',0)
        return None if ts == 0 else pendulum.from_timestamp(ts)
    @last_removed.setter
    def last_removed(self,datetime:pendulum.datetime):
        self._last_removed = datetime.int_timestamp
        self.client.cog.coc_data_log.info(
            f"Player {self}: last_removed set to {datetime}."
            )
        self.save()