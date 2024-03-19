import coc
import pendulum
import asyncio
import random
import logging
import motor.motor_asyncio

from typing import *

from pymongo import ReturnDocument
from collections import defaultdict
from async_property import AwaitLoader
from redbot.core.bot import Red

from ..clans.clan import BasicClan, aClan, _PlayerClan

from ...client.db_client import MotorClient

from ...utils.constants.coc_emojis import EmojisTownHall
from ...utils.constants.ui_emojis import EmojisUI
from ...utils.utils import check_rtl

DATA_LOG = logging.getLogger("coc.main")

class BasicPlayer(AwaitLoader):
    
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
        self._discord_user = None
        self.home_clan = None

    def __str__(self):
        return f"Player {self.tag}"    
    def __hash__(self):
        return hash(self.tag)
    @property
    def database(self) -> motor.motor_asyncio.AsyncIOMotorDatabase:
        return self._attributes.database
    @property
    def bot(self) -> Red:
        return self._attributes.bot
    
    async def load(self):
        await self._attributes.load()
        self.home_clan = await BasicClan(tag=self._attributes.home_clan_tag) if self._attributes.home_clan_tag else None
    
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
    def _create_snapshot(self) -> bool:
        if random.randint(1,100) == random.randint(1,100):
            return True
        
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
        if self._discord_user:
            return self._discord_user
        return self._attributes.discord_user
    @discord_user.setter
    def discord_user(self,value:int):
        self._discord_user = value
    
    @property
    def is_member(self) -> bool:
        return self._attributes.is_member

    @property
    def alliance_rank(self) -> str:
        try:
            if self.is_member:
                try:
                    if self.discord_user == self.home_clan.leader:
                        return 'Leader'
                    elif self.discord_user in self.home_clan.coleaders:
                        return 'Co-Leader'
                    elif self.discord_user in self.home_clan.elders:
                        return 'Elder'
                    else:
                        return 'Member'
                except:
                    return 'Member'
            else:
                return 'Non-Member'
        except:
            return 'Non-Member'
    
    @property
    def war_elo(self) -> float:
        return round(self._attributes.war_elo,1)
    
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
        return False if self.first_seen else True
    
    ##################################################
    #####
    ##### PLAYER METHODS
    #####
    ##################################################
    @classmethod
    async def player_first_seen(cls,tag:str):
        player = await cls(tag=coc.utils.correct_tag(tag))

        async with player._attributes._lock:
            player._attributes.first_seen = pendulum.now()
            
            await _PlayerAttributes.database.db__player.update_one(
                {'_id':player.tag},
                {'$set':{'first_seen':getattr(player.first_seen,'int_timestamp',pendulum.now().int_timestamp)}},
                upsert=True
                )
            DATA_LOG.debug(f"{player}: first_seen changed to {player.first_seen}. Is new: {player.is_new}")
    
    @classmethod
    async def set_discord_link(cls,tag:str,discord_user:int):
        player = await cls(tag=coc.utils.correct_tag(tag))
        async with player._attributes._lock:
            player._attributes.discord_user = discord_user

            await _PlayerAttributes.database.db__player.update_one(
                {'_id':player.tag},
                {'$set':{'discord_user':player.discord_user}},
                upsert=True
                )
            DATA_LOG.info(f"{player}: discord_user changed to {player.discord_user}.")            
    
    async def unlink_discord(self):
        async with self._attributes._lock:
            self._attributes.discord_user = 0
            await _PlayerAttributes.database.db__player.update_one(
                {'_id':self.tag},
                {'$set':{
                    'discord_user':0,
                    'is_member':False,
                    'home_clan':None}
                    },
                upsert=True
                )
            DATA_LOG.info(f"{self}: discord_user unlinked.")

    async def new_member(self,user_id:int,home_clan:BasicClan):
        await BasicPlayer.set_discord_link(self.tag,user_id)

        async with self._attributes._lock:
            if not self.is_member or not self.last_joined:
                self._attributes.last_joined = pendulum.now()         

            self._attributes.is_member = True
            self._attributes.home_clan_tag = home_clan.tag
            self.home_clan = await BasicClan(tag=home_clan.tag)                
            await self.home_clan.new_member(self.tag)

            await _PlayerAttributes.database.db__player.update_one(
                {'_id':self.tag},
                {'$set':{
                    'is_member':self.is_member,
                    'home_clan':getattr(self.home_clan,'tag',None),
                    'last_joined':getattr(self.last_joined,'int_timestamp',pendulum.now().int_timestamp)
                    }
                },
                upsert=True)
            
            await home_clan.clean_coleaders()
            await home_clan.clean_elders()
            
            DATA_LOG.info(
                f"Player {self} is now an Alliance member!"
                    + f"\n\tHome Clan: {self.home_clan.tag} {self.home_clan.name}"
                    + f"\n\tLast Joined: {self.last_joined}"
                    )
            
    async def remove_member(self):
        self.home_clan = await BasicClan(tag=self._attributes.home_clan_tag) if self._attributes.home_clan_tag else None
        if self.home_clan:
            await self.home_clan.remove_member(self.tag)
            await self.home_clan.clean_coleaders()
            await self.home_clan.clean_elders()

        async with self._attributes._lock:
            ts = pendulum.now()
            self._attributes.is_member = False
            self._attributes.home_clan_tag = None
            self._attributes.last_removed = ts

            self.home_clan = None

            await _PlayerAttributes.database.db__player.update_one(
                {'_id':self.tag},
                {'$set':{
                    'is_member':False,
                    'last_removed':ts.int_timestamp
                    },
                '$unset':{
                    'home_clan':''
                    }
                },
                upsert=True
                )
            DATA_LOG.info(
                f"Player {self} has been removed as a member."
                + f"\n\tLast Removed: {self._attributes.last_removed}"
                )
    
    async def reset_war_elo(self):
        async with self._attributes._lock:
            player = await _PlayerAttributes.database.db__player.find_one_and_update(
                {'_id':self.tag},
                {'$set':{'war_elo':0}},
                return_document=ReturnDocument.AFTER,
                upsert=True
                )
            self._attributes.war_elo = player['war_elo']
            DATA_LOG.debug(f"{self}: war_elo reset to 0. New: {self.war_elo}.")
    
    async def adjust_war_elo(self,amount:float):
        async with self._attributes._lock:
            player = await _PlayerAttributes.database.db__player.find_one_and_update(
                {'_id':self.tag},
                {'$inc':{'war_elo':amount}},
                return_document=ReturnDocument.AFTER,
                upsert=True
                )
            self._attributes.war_elo = player['war_elo']
            DATA_LOG.debug(f"{self}: war_elo adjusted by {amount}. New: {self.war_elo}.")

    ##################################################
    #####
    ##### DATABASE INTERACTIONS
    #####
    ##################################################    
    async def set_name(self,new_name:str):
        async with self._attributes._lock:
            self._attributes.name = new_name
            await _PlayerAttributes.database.db__player.update_one(
                {'_id':self.tag},
                {'$set':{'name':self.name}},
                upsert=True
                )
            DATA_LOG.debug(f"{self}: name changed to {self.name}.")
    
    async def set_exp_level(self,new_value:int):        
        async with self._attributes._lock:
            self._attributes.exp_level = new_value
            await _PlayerAttributes.database.db__player.update_one(
                {'_id':self.tag},
                {'$set':{'xp_level':self.exp_level}},
                upsert=True
                )
            DATA_LOG.debug(f"{self}: exp_level changed to {self.exp_level}.")
        
    async def set_town_hall_level(self,new_value:int):        
        async with self._attributes._lock:
            self._attributes.town_hall_level = new_value
            await _PlayerAttributes.database.db__player.update_one(
                {'_id':self.tag},
                {'$set':{'townhall':self.town_hall_level}},
                upsert=True
                )
            DATA_LOG.debug(f"{self}: town_hall_level changed to {self.town_hall_level}.")

# db__player = {
#   '_id': string, #player tag
#   'discord_user': string,
#   'is_member': bool,
#   'home_clan': string,
#   'war_elo': int,
#   'first_seen': int,
#   'last_joined': int,
#   'last_removed': int,
#   'name': string,
#   'xp_level': int,
#   'townhall': int
#   }

class _PlayerAttributes(MotorClient):
    """
    This class enforces a singleton pattern that caches database responses.

    This class DOES NOT handle database updates - those are handled within the BasicPlayer class.
    """
    _cache = {}
    _locks = defaultdict(asyncio.Lock)
    _sync_locks = defaultdict(asyncio.Lock)

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
        'war_elo',
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
            self.war_elo = None
            self.is_member = None
            self.first_seen = None
            self.last_joined = None
            self.last_removed = None

            self._last_sync = None

        self._new = False
    
    @property
    def _lock(self) -> asyncio.Lock:
        return self._locks[self.tag]
    @property
    def _sync_lock(self) -> asyncio.Lock:
        return self._sync_locks[self.tag]
    
    async def load(self):
        if not self._loaded:
            await self.load_data()
    
    async def load_data(self):
        database = await self.database.db__player.find_one({'_id':self.tag})

        self.name = database.get('name','') if database else ""
        self.exp_level = database.get('xp_level','') if database else 0
        self.town_hall_level = database.get('townhall','') if database else 0
        self.discord_user = database.get('discord_user','') if database else 0
        self.home_clan_tag = database.get('home_clan',None) if database else None
        self.war_elo = database.get('war_elo',0) if database else 0

        self.is_member = await self.eval_membership(database.get('is_member',False)) if database else False

        fs = database.get('first_seen',0) if database else 0
        self.first_seen = pendulum.from_timestamp(fs) if fs > 0 else None

        lj = database.get('last_joined',0) if database else 0
        self.last_joined = pendulum.from_timestamp(lj) if lj > 0 else None

        lr = database.get('last_removed',0) if database else 0
        self.last_removed = pendulum.from_timestamp(lr) if lr > 0 else None

        ls = database.get('last_sync',0) if database else 0
        self._last_sync = pendulum.from_timestamp(ls) if ls > 0 else None

        self._loaded = True
    
    async def eval_membership(self,database_entry:bool):
        if database_entry and self.home_clan_tag:
            clan = await BasicClan(tag=self.home_clan_tag)
            if not clan.is_alliance_clan:
                player = BasicPlayer(tag=self.tag)
                await player.remove_member()
                DATA_LOG.info(f"{self}: Removing as Member as their previous Home Clan is no longer recognized as an Alliance clan.")
                return False
        return database_entry
    
    async def update_last_sync(self,timestamp:pendulum.DateTime):
        async with self._attributes._lock:
            self._attributes._last_sync = timestamp
            await self.database.db__player.update_one(
                {'_id':self.tag},
                {'$set':{'last_sync':timestamp.int_timestamp}},
                upsert=True
                )
            DATA_LOG.debug(f"{self}: last_sync changed to {self._attributes._last_sync}.")