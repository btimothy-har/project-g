import asyncio
import pendulum

from typing import *
from mongoengine import *

from async_property import AwaitLoader

from ...api_client import BotClashClient as client
from ..season.season import aClashSeason

from .mongo_player import db_PlayerStats
from .player_stat import aPlayerStat
from .player_clangames import aPlayerClanGames

from ..clans.player_clan import aPlayerClan
from ...utils.utils import check_rtl

bot_client = client()

class aPlayerSeason(AwaitLoader):
    _cache = {}

    __slots__ = [
        '_new',
        '_loaded',
        '_lock',
        'tag',
        'season',
        'name',
        'town_hall',
        'is_member',
        'home_clan_tag',
        'home_clan',
        'time_in_home_clan',
        'last_seen',
        'attacks',
        'defenses',
        'donations_sent',
        'donations_rcvd',
        'loot_gold',
        'loot_elixir',
        'loot_darkelixir',
        'capitalcontribution',
        'clangames'
        ]

    def __new__(cls,tag:str,season:aClashSeason):
        if (tag,season.id) not in cls._cache:
            instance = super().__new__(cls)
            instance._new = True
            instance._loaded = False
            cls._cache[(tag,season.id)] = instance
        return cls._cache[(tag,season.id)]
    
    def __init__(self,tag:str,season:aClashSeason):        
        if self._new:
            self._lock = asyncio.Lock()

            self.tag = tag
            self.season = season

            self.name = None
            self.town_hall = None
            self.is_member = None
            self.home_clan_tag = None
            self.time_in_home_clan = 0
            self.last_seen = []
            self.attacks = None
            self.defenses = None
            self.donations_sent = None
            self.donations_rcvd = None
            self.loot_gold = None
            self.loot_elixir = None
            self.loot_darkelixir = None
            self.capitalcontribution = None
            self.clangames = None

            self._new = False
    
    def __str__(self):
        return f"Player Stats {self.season.id}: {self.name} ({self.tag})"
    
    def __eq__(self,other):
        return isinstance(other,aPlayerSeason) and self.tag == other.tag and self.season == other.season

    async def load(self):
        if not self._loaded:
            database = await bot_client.coc_db.db__player_stats.find_one({'_id':self._db_id})
            
            self.name = database.get('name','') if database else ''
            self.town_hall = database.get('town_hall',0) if database else 0
            self.is_member = database.get('is_member',False) if database else False
            
            self.home_clan_tag = database.get('home_clan',None) if database else None
            self.home_clan = await aPlayerClan(tag=self.home_clan_tag) if self.home_clan_tag else None

            self.time_in_home_clan = database.get('time_in_home_clan',0) if database else 0
            last_seen_db = list(set(database.get('last_seen',[]))) if database else []
            self.last_seen = [pendulum.from_timestamp(x) for x in last_seen_db] if last_seen_db else []

            self.attacks = aPlayerStat(
                tag=self.tag,
                season=self.season,
                description='attacks',
                dict_value=database.get('attacks',{}) if database else {}
                )
            self.defenses = aPlayerStat(
                tag=self.tag,
                season=self.season,
                description='defenses',
                dict_value=database.get('defenses',{}) if database else {}
                )
            self.donations_sent = aPlayerStat(
                tag=self.tag,
                season=self.season,
                description='donations_sent',
                dict_value=database.get('donations_sent',{}) if database else {}
                )
            self.donations_rcvd = aPlayerStat(
                tag=self.tag,
                season=self.season,
                description='donations_rcvd',
                dict_value=database.get('donations_rcvd',{}) if database else {}
                )
            self.loot_gold = aPlayerStat(
                tag=self.tag,
                season=self.season,
                description='loot_gold',
                dict_value=database.get('loot_gold',{}) if database else {}
                )
            self.loot_elixir = aPlayerStat(
                tag=self.tag,
                season=self.season,
                description='loot_elixir',
                dict_value=database.get('loot_elixir',{}) if database else {}
                )
            self.loot_darkelixir = aPlayerStat(
                tag=self.tag,
                season=self.season,
                description='loot_darkelixir',
                dict_value=database.get('loot_darkelixir',{}) if database else {}
                )
            self.capitalcontribution = aPlayerStat(
                tag=self.tag,
                season=self.season,
                description='capitalcontribution',
                dict_value=database.get('capitalcontribution',{}) if database else {}
                )
            self.clangames = aPlayerClanGames(
                tag=self.tag,
                season=self.season,
                dict_value=database.get('clangames',{}) if database else {}
                )
            self._loaded = True
        
    @property
    def is_current_season(self) -> bool:
        return self.season.is_current
    
    @property
    def _db_id(self) -> Dict[str,str]:
        return {'season': self.season.id,'tag': self.tag}
    
    @property
    def clean_name(self) -> str:
        if check_rtl(self.name):
            return '\u200F' + self.name + '\u200E'
        return self.name 
    
    @property
    def donations(self) -> aPlayerStat:
        return self.donations_sent

    @property
    def received(self) -> aPlayerStat:
        return self.donations_rcvd

    async def update_name(self,new_name:str):
        async with self._lock:            
            self.name = new_name
            await bot_client.coc_db.db__player_stats.update_one(
                {'_id':self._db_id},
                {'$set': {
                    'season':self.season.id,
                    'tag':self.tag,
                    'name':self.name
                    }
                },
                upsert=True)
    
    async def update_townhall(self,new_th:int):
        async with self._lock:
            self.town_hall = new_th
            await bot_client.coc_db.db__player_stats.update_one(
                {'_id':self._db_id},
                {'$set': {
                    'season':self.season.id,
                    'tag':self.tag,
                    'town_hall':self.town_hall
                    }
                },
                upsert=True)
    
    async def update_home_clan(self,new_tag:Optional[str]=None):
        async with self._lock:
            self.home_clan_tag = new_tag
            self.home_clan = await aPlayerClan(tag=self.home_clan_tag) if self.home_clan_tag else None
            await bot_client.coc_db.db__player_stats.update_one(
                {'_id':self._db_id},
                {'$set': {
                    'season':self.season.id,
                    'tag':self.tag,
                    'home_clan':self.home_clan_tag
                    }
                },
                upsert=True)
    
    async def update_member(self,is_member:bool=False):
        async with self._lock:
            self.is_member = is_member
            await bot_client.coc_db.db__player_stats.update_one(
                {'_id':self._db_id},
                {'$set': {
                    'season':self.season.id,
                    'tag':self.tag,
                    'is_member':self.is_member
                    }
                },
                upsert=True)
    
    async def add_time_in_home_clan(self,duration:int):
        async with self._lock:
            self.time_in_home_clan += duration
            await bot_client.coc_db.db__player_stats.update_one(
                {'_id':self._db_id},
                {'$set': {
                    'season':self.season.id,
                    'tag':self.tag,
                    'time_in_home_clan':self.time_in_home_clan
                    }
                },
                upsert=True)
            bot_client.coc_data_log.debug(f"{self}: Added {duration} to time in home clan")
    
    async def add_last_seen(self,timestamp:pendulum.DateTime):
        async with self._lock:
            if timestamp.int_timestamp not in [ts.int_timestamp for ts in self.last_seen]:
                self.last_seen.append(timestamp)
                
                await bot_client.coc_db.db__player_stats.update_one(
                    {'_id':self._db_id},
                    {'$set': {
                        'season':self.season.id,
                        'tag':self.tag,
                        'last_seen':[ts.int_timestamp for ts in self.last_seen]
                        }
                    },
                    upsert=True)
                bot_client.coc_data_log.debug(f"{self}: Added last seen {timestamp}")
        
        