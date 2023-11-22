import coc
import pendulum
import asyncio

from typing import *
from mongoengine import *

from functools import cached_property
from ...api_client import BotClashClient as client
from .mongo_player import db_Player

from ...utils.constants.coc_emojis import EmojisTownHall
from ...utils.constants.ui_emojis import EmojisUI
from ...utils.utils import check_rtl

from ..clans.player_clan import *

bot_client = client()

class BasicPlayer():

    @classmethod
    async def load_all(cls) -> List['BasicPlayer']:
        def _get_from_db():
            return [db.tag for db in db_Player.objects.only('tag')]
        
        player_tags = await bot_client.run_in_thread(_get_from_db)
        players = []
        for player in player_tags:
            await asyncio.sleep(0)
            players.append(await cls._load_attributes(player))
        return players
    
    @classmethod
    def clear_cache(cls):
        _PlayerAttributes._cache = {}
    
    @classmethod
    async def _load_attributes(cls,tag):
        attr = _PlayerAttributes(tag=tag)
        await attr._load_attributes()
        return cls(tag=tag)
    
    """
    The BasicPlayer class provides a consolidated interface for inheriting player objects.

    Access to database attributes are provided through the _PlayerAttributes class.
    """
    def __init__(self,tag:str):
        self.tag = coc.utils.correct_tag(tag)
        self._attributes = _PlayerAttributes(tag=self.tag)

    def __str__(self):
        return f"Player {self.tag} ({self.name})"
    
    def __hash__(self):
        return hash(self.tag)   
    
    ##################################################
    #####
    ##### FORMATTERS
    #####
    ##################################################
    @property
    def title(self):
        return f"{EmojisTownHall.get(self.town_hall_level)} {self.name} ({self.tag})"

    @property
    def clean_name(self) -> str:
        if check_rtl(self.name):
            return '\u200F' + self.name + '\u200E'
        return self.name
    
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
    
    @property
    def share_link(self) -> str:
        return f"https://link.clashofclans.com/en?action=OpenPlayerProfile&tag=%23{self.tag.strip('#')}"
    
    @property
    def discord_user_str(self):
        return f"{EmojisUI.DISCORD} <@{str(self.discord_user)}>" if self.discord_user else ""
    
    ##################################################
    #####
    ##### PLAYER ATTRIBUTES
    #####
    ##################################################
    @property
    def name(self) -> str:
        return self._attributes.name
    
    @property
    def exp_level(self) -> int:
        return self._attributes.exp_level
    
    @property
    def town_hall_level(self) -> int:
        return self._attributes.town_hall_level
    
    @property
    def discord_user(self) -> int:
        return self._attributes.discord_user
    
    @property
    def is_member(self) -> bool:
        return self._attributes.is_member
    
    @property
    def home_clan(self) -> Optional[aPlayerClan]:
        return self._attributes.home_clan

    @property
    def alliance_rank(self) -> str:
        if self.is_member:
            if self.discord_user == self.home_clan.leader:
                return 'Leader'
            elif self.discord_user in self.home_clan.coleaders:
                return 'Co-Leader'
            elif self.discord_user in self.home_clan.elders:
                return 'Elder'
            else:
                return 'Member'
        else:
            return 'Non-Member'
    
    @property
    def first_seen(self) -> Optional[pendulum.DateTime]:
        return self._attributes.first_seen
    
    @property
    def last_joined(self) -> Optional[pendulum.DateTime]:
        return self._attributes.last_joined

    @property
    def last_removed(self) -> Optional[pendulum.DateTime]:
        return self._attributes.last_removed
    
    @property
    def is_new(self) -> bool:
        return self._attributes.is_new
    
    ##################################################
    #####
    ##### PLAYER METHODS
    #####
    ##################################################
    @classmethod
    async def player_first_seen(cls,tag:str):
        def _update_in_db():
            db_Player.objects(tag=player.tag).update_one(
                set__first_seen=player.first_seen.int_timestamp,
                upsert=True
                )
            bot_client.coc_data_log.debug(f"{player}: first_seen changed to {player.first_seen}.")
        
        player = cls(tag=coc.utils.correct_tag(tag))

        async with player._attributes._lock:
            player._attributes.first_seen = pendulum.now()
            player._attributes.is_new = False
            
            await bot_client.run_in_thread(_update_in_db)
    
    @classmethod
    async def set_discord_link(cls,tag:str,discord_user:int):
        def _update_in_db():
            db_Player.objects(tag=player.tag).update_one(
                set__discord_user=player.discord_user,
                upsert=True
                )
            bot_client.coc_data_log.info(f"{player}: discord_user changed to {player.discord_user}.")

        player = cls(tag=coc.utils.correct_tag(tag))
        async with player._attributes._lock:
            player._attributes.discord_user = discord_user
            await bot_client.run_in_thread(_update_in_db)

    async def new_member(self,user_id:int,home_clan:BasicClan):
        def _update_in_db():
            db_Player.objects(tag=self.tag).update_one(
                set__is_member=self.is_member,
                upsert=True
                )
            db_Player.objects(tag=self.tag).update_one(
                set__home_clan=getattr(home_clan,'tag',None),
                upsert=True
                )
            db_Player.objects(tag=self.tag).update_one(
                set__last_joined=self.last_joined.int_timestamp,
                upsert=True
                )
            bot_client.coc_data_log.info(
                f"Player {self} is now an Alliance member!"
                    + f"\n\tHome Clan: {self.home_clan.tag} {self.home_clan.name}"
                    + f"\n\tLast Joined: {self.last_joined}"
                    )

        await BasicPlayer.set_discord_link(self.tag,user_id)
        async with self._attributes._lock:
            if not self.is_member or not self.last_joined:
                self._attributes.last_joined = pendulum.now()
            self._attributes.is_member = True
            self._attributes.home_clan = aPlayerClan(tag=home_clan.tag)
            await self.home_clan.new_member(self.tag)
            await bot_client.run_in_thread(_update_in_db)
        
    async def remove_member(self):
        def _update_in_db():
            db_Player.objects(tag=self.tag).update_one(
                set__is_member=self.is_member,
                upsert=True
                )
            db_Player.objects(tag=self.tag).update_one(
                set__home_clan=getattr(self.home_clan,'tag',None),
                upsert=True
                )
            db_Player.objects(tag=self.tag).update_one(
                set__last_removed=self.last_removed.int_timestamp,
                upsert=True
                )
            bot_client.coc_data_log.info(
                f"Player {self} has been removed as a member."
                    + f"\n\tHome Clan: {self.home_clan}"
                    + f"\n\tLast Removed: {self.last_removed}"
                    )
            
        if self.home_clan:
            await self.home_clan.remove_member(self.tag)

        async with self._attributes._lock:
            self._attributes.is_member = False
            self._attributes.home_clan = None
            self._attributes.last_removed = pendulum.now()
            await bot_client.run_in_thread(_update_in_db)

    ##################################################
    #####
    ##### DATABASE INTERACTIONS
    #####
    ##################################################    
    async def set_name(self,new_name:str):
        def _update_in_db():
            db_Player.objects(tag=self.tag).update_one(
                set__name=self.name,
                upsert=True
                )
            bot_client.coc_data_log.debug(f"{self}: name changed to {self.name}.")

        async with self._attributes._lock:
            self._attributes.name = new_name
            await bot_client.run_in_thread(_update_in_db)
    
    async def set_exp_level(self,new_value:int):
        def _update_in_db():
            db_Player.objects(tag=self.tag).update_one(
                set__xp_level=self.exp_level,
                upsert=True
                )
            bot_client.coc_data_log.debug(f"{self}: exp_level changed to {self.exp_level}.")
        
        async with self._attributes._lock:
            self._attributes.exp_level = new_value
            await bot_client.run_in_thread(_update_in_db)
        
    async def set_town_hall_level(self,new_value:int):
        def _update_in_db():
            db_Player.objects(tag=self.tag).update_one(
                set__townhall=self.town_hall_level,
                upsert=True
                )
            bot_client.coc_data_log.debug(f"{self}: town_hall_level changed to {self.town_hall_level}.")
        
        async with self._attributes._lock:
            self._attributes.town_hall_level = new_value
            await bot_client.run_in_thread(_update_in_db)

class _PlayerAttributes():    
    """
    This class enforces a singleton pattern that caches database responses.

    This class DOES NOT handle database updates - those are handled within the BasicPlayer class.
    """
    _cache = {}

    def __new__(cls,tag:str):
        n_tag = coc.utils.correct_tag(tag)
        if n_tag not in cls._cache:
            instance = super().__new__(cls)
            instance._is_new = True
            cls._cache[n_tag] = instance
        return cls._cache[n_tag]
    
    def __init__(self,tag:str):
        if self._is_new:
            self.tag = coc.utils.correct_tag(tag)
            self._lock = asyncio.Lock()
            bot_client.player_queue.add(self.tag)
        
        self._is_new = False

    async def _load_attributes(self):
        def _get_from_db() -> db_Player:
            try:
                return db_Player.objects.get(tag=self.tag)
            except DoesNotExist:
                return None
        db = await bot_client.run_in_thread(_get_from_db)
        if db:
            self.name = db.name
            self.exp_level = db.xp_level
            self.town_hall_level = db.townhall
            self.discord_user = db.discord_user
            self.is_member = db.is_member
            self.home_clan = aPlayerClan(tag=db.home_clan) if db.home_clan else None
            
            self.first_seen = pendulum.from_timestamp(db.first_seen) if db.first_seen > 0 else None
            self.last_joined = pendulum.from_timestamp(db.last_joined) if db.last_joined > 0 else None
            self.last_removed = pendulum.from_timestamp(db.last_removed) if db.last_removed > 0 else None
    
    @property
    def _database(self) -> Optional[db_Player]:
        try:
            return db_Player.objects.get(tag=self.tag)
        except DoesNotExist:
            return None

    @cached_property
    def name(self) -> str:
        return getattr(self._database,'name',"")
    
    @cached_property
    def exp_level(self) -> int:
        return getattr(self._database,'xp_level',0)    
  
    @cached_property
    def town_hall_level(self) -> int:
        return getattr(self._database,'townhall',0)
    
    @cached_property
    def discord_user(self) -> int:
        return getattr(self._database,'discord_user',0)
    
    @cached_property
    def is_member(self) -> bool:
        val = getattr(self._database,'is_member',False)
        if val and not getattr(self.home_clan,'is_alliance_clan',False):
            asyncio.create_task(self.remove_member())
            bot_client.coc_data_log.info(f"{self}: Removing as Member as their previous Home Clan is no longer recognized as an Alliance clan.")
            return False
        return val
    
    @cached_property
    def home_clan(self) -> Optional[aPlayerClan]:
        tag = getattr(self._database,'home_clan',None)
        if tag:
            return aPlayerClan(tag=tag)
        return None
    
    @cached_property
    def first_seen(self) -> Optional[pendulum.DateTime]:
        fs = getattr(self._database,'first_seen',0)
        if fs > 0:
            return pendulum.from_timestamp(fs)
        return None
    
    @cached_property
    def last_joined(self) -> Optional[pendulum.DateTime]:
        lj = getattr(self._database,'last_joined',0)
        if lj > 0:
            return pendulum.from_timestamp(lj)
        return None

    @cached_property
    def last_removed(self) -> Optional[pendulum.DateTime]:
        lr = getattr(self._database,'last_removed',0)
        if lr > 0:
            return pendulum.from_timestamp(lr)
        return None
    
    @cached_property
    def is_new(self) -> bool:
        return True if not self.first_seen else False