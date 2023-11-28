import coc
import pendulum
import asyncio

from typing import *
from mongoengine import *

from functools import cached_property
from collections import defaultdict
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
        count = 0     
        query = bot_client.coc_db.db__player.find({},{'_id':1})        
        async for p in query:
            await bot_client.player_queue.put(p['_id'])
            await asyncio.sleep(0.1)
            count += 1
            if count >= 100000:
                break
    
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
        await self._attributes.load()
        self.home_clan = await aPlayerClan(tag=self._attributes.home_clan_tag) if self._attributes.home_clan_tag else None            
    
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
    @property
    def name(self) -> str:
        if not self._attributes._loaded:
            raise CacheNotReady(f"{self} has not been loaded.")
        return self._attributes.name
    
    @property
    def exp_level(self) -> int:
        if not self._attributes._loaded:
            raise CacheNotReady(f"{self} has not been loaded.")
        return self._attributes.exp_level
    
    @property
    def town_hall_level(self) -> int:
        if not self._attributes._loaded:
            raise CacheNotReady(f"{self} has not been loaded.")
        return self._attributes.town_hall_level
    
    @property
    def discord_user(self) -> int:
        if not self._attributes._loaded:
            raise CacheNotReady(f"{self} has not been loaded.")
        return self._attributes.discord_user
    
    @property
    def is_member(self) -> bool:
        if not self._attributes._loaded:
            raise CacheNotReady(f"{self} has not been loaded.")
        return self._attributes.is_member

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
        if not self._attributes._loaded:
            raise CacheNotReady(f"{self} has not been loaded.")
        return self._attributes.first_seen
    
    @property
    def last_joined(self) -> Optional[pendulum.DateTime]:
        if not self._attributes._loaded:
            raise CacheNotReady(f"{self} has not been loaded.")
        return self._attributes.last_joined

    @property
    def last_removed(self) -> Optional[pendulum.DateTime]:
        if not self._attributes._loaded:
            raise CacheNotReady(f"{self} has not been loaded.")
        return self._attributes.last_removed
    
    @property
    def is_new(self) -> bool:
        if not self._attributes._loaded:
            raise CacheNotReady(f"{self} has not been loaded.")
        return False if self.first_seen else True
    
    ##################################################
    #####
    ##### PLAYER METHODS
    #####
    ##################################################
    @classmethod
    async def player_first_seen(cls,tag:str):
        player = cls(tag=coc.utils.correct_tag(tag))

        async with player._attributes._lock:
            player._attributes.first_seen = pendulum.now()

            await bot_client.coc_db.db__player.update_one(
                {'_id':player.tag},
                {'$set':{'first_seen':getattr(player.first_seen,'int_timestamp',pendulum.now().int_timestamp)}},
                upsert=True
                )
            bot_client.coc_data_log.debug(f"{player}: first_seen changed to {player.first_seen}. Is new: {player.is_new}")
    
    @classmethod
    async def set_discord_link(cls,tag:str,discord_user:int):
        player = cls(tag=coc.utils.correct_tag(tag))
        async with player._attributes._lock:
            player._attributes.discord_user = discord_user

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
                self._attributes.last_joined = pendulum.now()         

            self._attributes.is_member = True
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
        if self.home_clan:
            await self.home_clan.remove_member(self.tag)

        async with self._attributes._lock:
            self._attributes.is_member = False
            self.home_clan = self._attributes.home_clan_tag = None
            self._attributes.last_removed = pendulum.now()

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
            self._attributes.name = new_name
            await bot_client.coc_db.db__player.update_one(
                {'_id':self.tag},
                {'$set':{'name':self.name}},
                upsert=True
                )
            bot_client.coc_data_log.debug(f"{self}: name changed to {self.name}.")
    
    async def set_exp_level(self,new_value:int):        
        async with self._attributes._lock:
            self._attributes.exp_level = new_value
            await bot_client.coc_db.db__player.update_one(
                {'_id':self.tag},
                {'$set':{'xp_level':self.exp_level}},
                upsert=True
                )
            bot_client.coc_data_log.debug(f"{self}: exp_level changed to {self.exp_level}.")
        
    async def set_town_hall_level(self,new_value:int):        
        async with self._attributes._lock:
            self._attributes.town_hall_level = new_value
            await bot_client.coc_db.db__player.update_one(
                {'_id':self.tag},
                {'$set':{'townhall':self.town_hall_level}},
                upsert=True
                )
            bot_client.coc_data_log.debug(f"{self}: town_hall_level changed to {self.town_hall_level}.")

class _PlayerAttributes():
    """
    This class enforces a singleton pattern that caches database responses.

    This class DOES NOT handle database updates - those are handled within the BasicPlayer class.
    """
    _cache = {}
    _locks = defaultdict(asyncio.Lock)

    __slots__ = [
        '_new',
        '_loaded',
        '_last_sync',
        'tag',
        'name',
        'exp_level',
        'town_hall_level',
        'discord_user',
        'home_clan_tag',
        'is_member',
        'first_seen',
        'last_joined',
        'last_removed'
        ]

    def __new__(cls,tag:str):
        n_tag = coc.utils.correct_tag(tag)
        if n_tag not in cls._cache:
            instance = super().__new__(cls)
            instance._new = True
            instance._loaded = False
            cls._cache[n_tag] = instance
        return cls._cache[n_tag]
    
    def __init__(self,tag:str):
        if self._new:
            self.tag = coc.utils.correct_tag(tag)
            self.name = None
            self.exp_level = None
            self.town_hall_level = None
            self.discord_user = None
            self.home_clan_tag = None
            self.is_member = None
            self.first_seen = None
            self.last_joined = None
            self.last_removed = None

            self._last_sync = None            
            bot_client.player_queue.add(self.tag)
        
        self._new = False
    
    @property
    def _lock(self) -> asyncio.Lock:
        return self._locks[self.tag]
    
    async def load(self):
        if not self._loaded:            
            database = await bot_client.coc_db.db__player.find_one({'_id':self.tag})
            self.name = database.get('name','') if database else ""
            self.exp_level = database.get('xp_level','') if database else 0
            self.town_hall_level = database.get('townhall','') if database else 0
            self.discord_user = database.get('discord_user','') if database else 0
            self.home_clan_tag = database.get('home_clan',None) if database else None
            self.is_member = await self.eval_membership(database.get('is_member',False)) if database else False

            fs = database.get('first_seen',0) if database else 0
            self.first_seen = pendulum.from_timestamp(fs) if fs > 0 else None

            lj = database.get('last_joined',0) if database else 0
            self.last_joined = pendulum.from_timestamp(lj) if lj > 0 else None

            lr = database.get('last_removed',0) if database else 0
            self.last_removed = pendulum.from_timestamp(lr) if lr > 0 else None

            self._loaded = True
    
    async def eval_membership(self,database_entry:bool):
        if database_entry and not getattr(await self.home_clan,'is_alliance_clan',False):
            player = BasicPlayer(tag=self.tag)
            await player.remove_member()
            bot_client.coc_data_log.info(f"{self}: Removing as Member as their previous Home Clan is no longer recognized as an Alliance clan.")
            return False
        return database_entry