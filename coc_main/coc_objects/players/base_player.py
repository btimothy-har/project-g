import coc
import pendulum
import asyncio

from typing import *
from mongoengine import *

from functools import cached_property
from async_property import AwaitLoader, AwaitableOnly, async_property, async_cached_property
from redbot.core.utils import AsyncIter
from ...api_client import BotClashClient as client
from .mongo_player import db_Player

from ...utils.constants.coc_emojis import EmojisTownHall
from ...utils.constants.ui_emojis import EmojisUI
from ...utils.utils import check_rtl
from ...exceptions import CacheNotReady

from ..clans.player_clan import *

bot_client = client()

class BasicPlayer(AwaitLoader):

    @classmethod
    async def load_all(cls) -> List['BasicPlayer']:
        def _get_from_db():
            return [db.tag for db in db_Player.objects.only('tag')]
        
        player_tags = await bot_client.run_in_read_thread(_get_from_db)
        return player_tags
        # a_iter = AsyncIter(player_tags)
        # players = []
        # async for tag in a_iter:
        #     players.append(await cls(tag))
        # return players
    
    @classmethod
    def clear_cache(cls):
        _PlayerAttributes._cache = {}
    
    """
    The BasicPlayer class provides a consolidated interface for inheriting player objects.

    Access to database attributes are provided through the _PlayerAttributes class.
    """
    def __init__(self,tag:str):
        self.tag = coc.utils.correct_tag(tag)
        self._attributes = _PlayerAttributes(tag=self.tag)

    def __str__(self):
        return f"Player {self.tag}"
    
    def __hash__(self):
        return hash(self.tag)   
    
    async def load(self):
        self._attributes = await _PlayerAttributes(self.tag)
        self._attributes._cache_loaded = True
    
    ##################################################
    #####
    ##### FORMATTERS
    #####
    ##################################################
    @property
    def title(self) -> str:
        return f"{EmojisTownHall.get(self.town_hall_level)} {self.name} ({self.tag})"

    @property
    def clean_name(self) -> str:
        if check_rtl(self.name):
            return '\u200F' + self.name + '\u200E'
        return self.name
    
    @property
    def member_description(self):
        if self._attributes.is_member:
            return f"{getattr(self.home_clan,'emoji','')} {self.alliance_rank} of {getattr(self.home_clan,'clean_name','')}"
        return ""
        
    @property
    def member_description_no_emoji(self) -> str:
        if self.is_member:
            return f"{self.alliance_rank} of {getattr(self.home_clan,'clean_name','')}"
        return ""
    
    @property
    def discord_user_str(self):
        return f"{EmojisUI.DISCORD} <@{str(self.discord_user)}>" if self.discord_user else ""

    @property
    def share_link(self) -> str:
        return f"https://link.clashofclans.com/en?action=OpenPlayerProfile&tag=%23{self.tag.strip('#')}"
    
    ##################################################
    #####
    ##### PLAYER ATTRIBUTES
    #####
    ##################################################
    @async_property
    async def name(self) -> str:
        return await self._attributes.name
    
    @property
    def exp_level(self) -> int:
        if isinstance(self._attributes.exp_level,AwaitableOnly):
            raise CacheNotReady
        return self._attributes.exp_level
    
    @property
    def town_hall_level(self) -> int:
        if isinstance(self._attributes.town_hall_level,AwaitableOnly):
            raise CacheNotReady
        return self._attributes.town_hall_level
    
    @property
    def discord_user(self) -> int:
        if isinstance(self._attributes.discord_user,AwaitableOnly):
            raise CacheNotReady
        return self._attributes.discord_user
    
    @property
    def is_member(self) -> bool:
        if isinstance(self._attributes.is_member,AwaitableOnly):
            raise CacheNotReady
        return self._attributes.is_member
    
    @property
    def home_clan(self) -> Optional[aPlayerClan]:
        if isinstance(self._attributes.home_clan,AwaitableOnly):
            raise CacheNotReady
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
        if isinstance(self._attributes.first_seen,AwaitableOnly):
            raise CacheNotReady
        return self._attributes.first_seen
    
    @property
    def last_joined(self) -> Optional[pendulum.DateTime]:
        if isinstance(self._attributes.last_joined,AwaitableOnly):
            raise CacheNotReady
        return self._attributes.last_joined

    @property
    def last_removed(self) -> Optional[pendulum.DateTime]:
        if isinstance(self._attributes.last_removed,AwaitableOnly):
            raise CacheNotReady
        return self._attributes.last_removed
    
    @property
    def is_new(self) -> bool:
        if isinstance(self._attributes.is_new,AwaitableOnly):
            raise CacheNotReady
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
                set__first_seen=first_seen.int_timestamp,
                upsert=True
                )
            bot_client.coc_data_log.debug(f"{player}: first_seen changed to {first_seen}.")
        
        player = cls(tag=coc.utils.correct_tag(tag))

        async with player._attributes._lock:
            first_seen = player._attributes.first_seen = pendulum.now()
            player._attributes.is_new = False            
            await bot_client.run_in_write_thread(_update_in_db)
    
    @classmethod
    async def set_discord_link(cls,tag:str,discord_user:int):
        def _update_in_db():
            db_Player.objects(tag=player.tag).update_one(
                set__discord_user=user,
                upsert=True
                )
            bot_client.coc_data_log.info(f"{player}: discord_user changed to {user}.")

        player = cls(tag=coc.utils.correct_tag(tag))
        async with player._attributes._lock:
            user = player._attributes.discord_user = discord_user
            await bot_client.run_in_write_thread(_update_in_db)

    async def new_member(self,user_id:int,home_clan:BasicClan):
        def _update_in_db():
            db_Player.objects(tag=self.tag).update_one(
                set__is_member=is_member,
                set__home_clan=getattr(clan,'tag',None),
                set__last_joined=last_joined.int_timestamp,
                upsert=True
                )
            bot_client.coc_data_log.info(
                f"Player {self} is now an Alliance member!"
                    + f"\n\tHome Clan: {clan.tag} {clan.name}"
                    + f"\n\tLast Joined: {last_joined}"
                    )

        await BasicPlayer.set_discord_link(self.tag,user_id)
        async with self._attributes._lock:
            if not self.is_member or not self.last_joined:
                self._attributes.last_joined = pendulum.now()
            
            last_joined = self.last_joined
            is_member = self._attributes.is_member = True
            clan = self._attributes.home_clan = aPlayerClan(tag=home_clan.tag)
            await clan.new_member(self.tag)
            await bot_client.run_in_write_thread(_update_in_db)
        
    async def remove_member(self):
        def _update_in_db():
            db_Player.objects(tag=self.tag).update_one(
                set__is_member=is_member,
                set__home_clan=getattr(home_clan,'tag',None),
                set__last_removed=last_removed.int_timestamp,
                upsert=True
                )
            bot_client.coc_data_log.info(
                f"Player {self} has been removed as a member."
                    + f"\n\tHome Clan: {home_clan}"
                    + f"\n\tLast Removed: {last_removed}"
                    )
            
        if await self.home_clan:
            await self.home_clan.remove_member(self.tag)

        async with self._attributes._lock:
            is_member = self._attributes.is_member = False
            home_clan = self._attributes.home_clan = None
            last_removed = self._attributes.last_removed = pendulum.now()        
            await bot_client.run_in_write_thread(_update_in_db)

    ##################################################
    #####
    ##### DATABASE INTERACTIONS
    #####
    ##################################################    
    async def set_name(self,new_name:str):
        def _update_in_db():
            db_Player.objects(tag=self.tag).update_one(
                set__name=name,
                upsert=True
                )
            bot_client.coc_data_log.debug(f"{self}: name changed to {name}.")

        async with self._attributes._lock:
            name = self._attributes.name = new_name
            await bot_client.run_in_write_thread(_update_in_db)
    
    async def set_exp_level(self,new_value:int):
        def _update_in_db():
            db_Player.objects(tag=self.tag).update_one(
                set__xp_level=exp_level,
                upsert=True
                )
            bot_client.coc_data_log.debug(f"{self}: exp_level changed to {exp_level}.")
        
        async with self._attributes._lock:
            exp_level = self._attributes.exp_level = new_value
            await bot_client.run_in_write_thread(_update_in_db)
        
    async def set_town_hall_level(self,new_value:int):
        def _update_in_db():
            db_Player.objects(tag=self.tag).update_one(
                set__townhall=townhall,
                upsert=True
                )
            bot_client.coc_data_log.debug(f"{self}: town_hall_level changed to {townhall}.")
        
        async with self._attributes._lock:
            townhall = self._attributes.town_hall_level = new_value
            await bot_client.run_in_write_thread(_update_in_db)

class _PlayerAttributes(AwaitLoader):
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
            self._cache_loaded = False
            self._cached_db = None
            self._last_db_query = None
            
            bot_client.player_queue.add(self.tag)
        
        self._is_new = False
    
    @async_property
    async def _database(self) -> Optional[db_Player]:
        def _get_from_db() -> db_Player:
            try:
                return db_Player.objects.get(tag=self.tag)
            except DoesNotExist:
                return None
        if not self._cached_db or (pendulum.now() - self._last_db_query).total_seconds() > 60:
            self._cached_db = await bot_client.run_in_read_thread(_get_from_db)
            self._last_db_query = pendulum.now()
        return self._cached_db

    @async_cached_property
    async def name(self) -> str:
        return getattr(await self._database,'name',"")
    
    @async_cached_property
    async def exp_level(self) -> int:
        return getattr(await self._database,'xp_level',0)
  
    @async_cached_property
    async def town_hall_level(self) -> int:
        return getattr(await self._database,'townhall',0)
    
    @async_cached_property
    async def discord_user(self) -> int:
        return getattr(await self._database,'discord_user',0)
    
    @async_cached_property
    async def is_member(self) -> bool:
        val = getattr(await self._database,'is_member',False)
        if val and not getattr(await self.home_clan,'is_alliance_clan',False):
            player = BasicPlayer(tag=self.tag)
            await player.remove_member()
            bot_client.coc_data_log.info(f"{self}: Removing as Member as their previous Home Clan is no longer recognized as an Alliance clan.")
            return False
        return val
    
    @async_cached_property
    async def home_clan(self) -> Optional[aPlayerClan]:
        tag = getattr(await self._database,'home_clan',None)
        if tag:
            return aPlayerClan(tag=tag)
        return None
    
    @async_cached_property
    async def first_seen(self) -> Optional[pendulum.DateTime]:
        fs = getattr(await self._database,'first_seen',0)
        if fs > 0:
            return pendulum.from_timestamp(fs)
        return None
    
    @async_cached_property
    async def last_joined(self) -> Optional[pendulum.DateTime]:
        lj = getattr(await self._database,'last_joined',0)
        if lj > 0:
            return pendulum.from_timestamp(lj)
        return None

    @async_cached_property
    async def last_removed(self) -> Optional[pendulum.DateTime]:
        lr = getattr(await self._database,'last_removed',0)
        if lr > 0:
            return pendulum.from_timestamp(lr)
        return None
    
    @async_cached_property
    async def is_new(self) -> bool:
        return True if not await self.first_seen else False