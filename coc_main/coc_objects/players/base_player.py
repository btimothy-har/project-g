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
        query = bot_client.coc_db.db__player.find({},{'_id':1})        
        async for p in query:
            player = await cls(tag=p['_id'])
            await bot_client.player_queue.put(player.tag)
    
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
    @async_cached_property
    async def name(self) -> str:
        return await self._attributes.name
    
    @async_cached_property
    async def exp_level(self) -> int:
        return await self._attributes.exp_level
    
    @async_cached_property
    async def town_hall_level(self) -> int:
        return await self._attributes.town_hall_level
    
    @async_cached_property
    async def discord_user(self) -> int:
        return await self._attributes.discord_user
    
    @async_cached_property
    async def is_member(self) -> bool:
        return await self._attributes.is_member
    
    @async_cached_property
    async def home_clan(self) -> Optional[aPlayerClan]:
        return await self._attributes.home_clan

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
    
    @async_cached_property
    async def first_seen(self) -> Optional[pendulum.DateTime]:
        return await self._attributes.first_seen
    
    @async_cached_property
    async def last_joined(self) -> Optional[pendulum.DateTime]:
        return await self._attributes.last_joined

    @async_cached_property
    async def last_removed(self) -> Optional[pendulum.DateTime]:
        return await self._attributes.last_removed
    
    @async_cached_property
    async def is_new(self) -> bool:
        return await self._attributes.is_new
    
    ##################################################
    #####
    ##### PLAYER METHODS
    #####
    ##################################################
    @classmethod
    async def player_first_seen(cls,tag:str):
        player = cls(tag=coc.utils.correct_tag(tag))

        async with player._attributes._lock:
            player.first_seen = player._attributes.first_seen = pendulum.now()
            player.is_new = player._attributes.is_new = False

            await bot_client.coc_db.db__player.update_one(
                {'_id':player.tag},
                {'$set':{'first_seen':getattr(await player.first_seen,'int_timestamp',pendulum.now().int_timestamp)}},
                upsert=True
                )
            bot_client.coc_data_log.debug(f"{player}: first_seen changed to {player.first_seen}. Is new: {player.is_new}")
    
    @classmethod
    async def set_discord_link(cls,tag:str,discord_user:int):
        player = cls(tag=coc.utils.correct_tag(tag))
        async with player._attributes._lock:
            player.discord_user = player._attributes.discord_user = discord_user

            await bot_client.coc_db.db__player.update_one(
                {'_id':player.tag},
                {'$set':{'discord_user':await player.discord_user}},
                upsert=True
                )
            bot_client.coc_data_log.info(f"{player}: discord_user changed to {player.discord_user}.")            

    async def new_member(self,user_id:int,home_clan:BasicClan):
        await BasicPlayer.set_discord_link(self.tag,user_id)
        async with self._attributes._lock:
            if not self.is_member or not self.last_joined:
                self.last_joined = self._attributes.last_joined = pendulum.now()         

            self.is_member = self._attributes.is_member = True
            self._attributes.home_clan_tag = home_clan.tag
            self.home_clan = await aPlayerClan(tag=home_clan.tag)
                
            await self.home_clan.new_member(self.tag)

            await bot_client.coc_db.db__player.update_one(
                {'_id':self.tag},
                {'$set':{
                    'is_member':await self.is_member,
                    'home_clan':getattr(await self.home_clan,'tag',None),
                    'last_joined':getattr(await self.last_joined,'int_timestamp',pendulum.now().int_timestamp)
                    }
                },
                upsert=True)
            
            bot_client.coc_data_log.info(
                f"Player {self} is now an Alliance member!"
                    + f"\n\tHome Clan: {self.home_clan.tag} {self.home_clan.name}"
                    + f"\n\tLast Joined: {self.last_joined}"
                    )
            
    async def remove_member(self):
        if await self.home_clan:
            await self.home_clan.remove_member(self.tag)

        async with self._attributes._lock:
            self.is_member = self._attributes.is_member = False
            self.home_clan = self._attributes.home_clan_tag = None
            self.last_removed = self._attributes.last_removed = pendulum.now()

            await bot_client.coc_db.db__player.update_one(
                {'_id':self.tag},
                {'$set':{
                    'is_member':await self.is_member,
                    'home_clan':None,
                    'last_removed':getattr(await self.last_removed,'int_timestamp',pendulum.now().int_timestamp)
                    }
                },
                upsert=True
                )
            bot_client.coc_data_log.info(
                f"Player {self} has been removed as a member."
                    + f"\n\tLast Removed: {self.last_removed}"
                    )

    ##################################################
    #####
    ##### DATABASE INTERACTIONS
    #####
    ##################################################    
    async def set_name(self,new_name:str):
        async with self._attributes._lock:
            self.name = self._attributes.name = new_name
            await bot_client.coc_db.db__player.update_one(
                {'_id':self.tag},
                {'$set':{'name':await self.name}},
                upsert=True
                )
            bot_client.coc_data_log.debug(f"{self}: name changed to {self.name}.")
    
    async def set_exp_level(self,new_value:int):        
        async with self._attributes._lock:
            self.exp_level = self._attributes.exp_level = new_value
            await bot_client.coc_db.db__player.update_one(
                {'_id':self.tag},
                {'$set':{'xp_level':await self.exp_level}},
                upsert=True
                )
            bot_client.coc_data_log.debug(f"{self}: exp_level changed to {self.exp_level}.")
        
    async def set_town_hall_level(self,new_value:int):        
        async with self._attributes._lock:
            self.town_hall_level = self._attributes.town_hall_level = new_value
            await bot_client.coc_db.db__player.update_one(
                {'_id':self.tag},
                {'$set':{'townhall':await self.town_hall_level}},
                upsert=True
                )
            bot_client.coc_data_log.debug(f"{self}: town_hall_level changed to {self.town_hall_level}.")

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
            self._cache_loaded = False
            self._cached_db = None
            self._last_db_query = None
            
            bot_client.player_queue.add(self.tag)
        
        self._is_new = False
    
    @async_property
    async def _database(self) -> Optional[dict]:
        if not self._cached_db or (pendulum.now() - self._last_db_query).total_seconds() > 60:
            self._cached_db = await bot_client.coc_db.db__player.find_one({'_id':self.tag})
            self._last_db_query = pendulum.now()
        return self._cached_db

    @async_cached_property
    async def name(self) -> str:
        db = await self._database
        return db.get('name','') if db else ""
    
    @async_cached_property
    async def exp_level(self) -> int:
        db = await self._database
        return db.get('xp_level','') if db else 0
  
    @async_cached_property
    async def town_hall_level(self) -> int:
        db = await self._database
        return db.get('townhall','') if db else 0
    
    @async_cached_property
    async def discord_user(self) -> int:
        db = await self._database
        return db.get('discord_user','') if db else 0

    @async_cached_property
    async def home_clan_tag(self) -> Optional[str]:
        db = await self._database
        return db.get('home_clan',None) if db else None
    
    @async_property
    async def home_clan(self) -> Optional[aPlayerClan]:
        if await self.home_clan_tag:
            return await aPlayerClan(tag=await self.home_clan_tag)
        return None
    
    @async_cached_property
    async def is_member(self) -> bool:
        db = await self._database
        is_member = db.get('is_member',False) if db else False
        if is_member and not getattr(await self.home_clan,'is_alliance_clan',False):
            player = BasicPlayer(tag=self.tag)
            await player.remove_member()
            bot_client.coc_data_log.info(f"{self}: Removing as Member as their previous Home Clan is no longer recognized as an Alliance clan.")
            return False
        return is_member
    
    @async_cached_property
    async def first_seen(self) -> Optional[pendulum.DateTime]:
        db = await self._database
        fs = db.get('first_seen',0) if db else 0
        if fs > 0:
            return pendulum.from_timestamp(fs)
        return None
    
    @async_cached_property
    async def last_joined(self) -> Optional[pendulum.DateTime]:
        db = await self._database
        lj = db.get('last_joined',0) if db else 0
        if lj > 0:
            return pendulum.from_timestamp(lj)
        return None

    @async_cached_property
    async def last_removed(self) -> Optional[pendulum.DateTime]:
        db = await self._database
        lr = db.get('last_removed',0) if db else 0
        if lr > 0:
            return pendulum.from_timestamp(lr)
        return None
    
    @async_cached_property
    async def is_new(self) -> bool:
        return True if not await self.first_seen else False