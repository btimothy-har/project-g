import asyncio
import pendulum

from typing import *
from mongoengine import *

from functools import cached_property
from async_property import AwaitLoader, async_property, async_cached_property

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

    def __new__(cls,tag:str,season:aClashSeason):
        if (tag,season.id) not in cls._cache:
            instance = super().__new__(cls)
            instance._is_new = True                
            cls._cache[(tag,season.id)] = instance
        return cls._cache[(tag,season.id)]
    
    def __init__(self,tag:str,season:aClashSeason):        
        if self._is_new:
            self.tag = tag
            self.season = season
            
            self._lock = asyncio.Lock()
            self._cached_db = None
            self._last_db_query = None

        self._is_new = False
    
    def __str__(self):
        return f"Player Stats {self.season.id}: {self.name} ({self.tag})"
    
    def __eq__(self,other):
        return isinstance(other,aPlayerSeason) and self.tag == other.tag and self.season == other.season

    @property
    def is_current_season(self) -> bool:
        return self.season.is_current
    
    @property
    def _db_id(self) -> Dict[str,str]:
        return {'season': self.season.id,'tag': self.tag}
    
    @async_property
    async def _database(self) -> Optional[db_PlayerStats]:
        def _get_from_db():
            try:
                return db_PlayerStats.objects.get(stats_id=self._db_id)
            except DoesNotExist:
                return None
        if not self._cached_db or (pendulum.now() - self._last_db_query).total_seconds() > 60:
            self._cached_db = await bot_client.coc_db.db__player_stats.find_one({'_id.season': self.season.id,'_id.tag': self.tag})
            self._last_db_query = pendulum.now()
        return self._cached_db
    
    @async_cached_property
    async def name(self) -> str:
        db = await self._database
        return db.get('name','') if db else ''
    
    @property
    def clean_name(self) -> str:
        if check_rtl(self.name):
            return '\u200F' + self.name + '\u200E'
        return self.name    
    
    @async_cached_property
    async def town_hall(self) -> int:
        db = await self._database
        return db.get('town_hall',0) if db else 0
    
    @async_cached_property
    async def is_member(self) -> bool:
        db = await self._database
        return db.get('is_member',False) if db else False
    
    @async_cached_property
    async def home_clan_tag(self) -> Optional[str]:
        db = await self._database
        return db.get('home_clan',None) if db else None
    
    @async_property
    async def home_clan(self) -> Optional[aPlayerClan]:
        if await self.home_clan_tag:
            return await aPlayerClan(tag=self.home_clan_tag)
        return None
    
    @async_cached_property
    async def other_clan_tags(self) -> List[str]:
        db = await self._database
        return db.get('other_clans',[]) if db else []
    
    @async_cached_property
    async def time_in_home_clan(self) -> int:
        db = await self._database
        return db.get('time_in_home_clan',0) if db else 0
    
    @async_cached_property
    async def _last_seen(self) -> List[int]:
        db = await self._database
        return db.get('last_seen',[]) if db else []
        
    @async_property
    async def last_seen(self) -> List[pendulum.DateTime]:
        return [pendulum.from_timestamp(x) for x in list(set(await self._last_seen))]
    
    @async_cached_property
    async def attacks(self) -> aPlayerStat:
        db = await self._database
        return aPlayerStat(
            tag=self.tag,
            season=self.season,
            description='attack_wins',
            dict_value=db.get('attacks',{}) if db else {}
            )

    @async_cached_property
    async def defenses(self) -> aPlayerStat:
        db = await self._database
        return aPlayerStat(
            tag=self.tag,
            season=self.season,
            description='defense_wins',
            dict_value=db.get('defenses',{}) if db else {}
            )
    
    @async_cached_property
    async def donations_sent(self) -> aPlayerStat:
        db = await self._database
        return aPlayerStat(
            tag=self.tag,
            season=self.season,
            description='donations_sent',
            dict_value=db.get('donations_sent',{}) if db else {}
            )    
    @property
    def donations(self) -> aPlayerStat:
        if not isinstance(self.donations_sent,aPlayerStat):
            raise AttributeError("Donations not loaded")
        return self.donations_sent

    @async_cached_property
    async def donations_rcvd(self) -> aPlayerStat:
        db = await self._database
        return aPlayerStat(
            tag=self.tag,
            season=self.season,
            description='donations_rcvd',
            dict_value=db.get('donations_rcvd',{}) if db else {}
            )
    @property
    def received(self) -> aPlayerStat:
        if not isinstance(self.donations_rcvd,aPlayerStat):
            raise AttributeError("Donations not loaded")
        return self.donations_rcvd

    @async_cached_property
    async def loot_gold(self) -> aPlayerStat:
        db = await self._database
        return aPlayerStat(
            tag=self.tag,
            season=self.season,
            description='loot_gold',
            dict_value=db.get('loot_gold',{}) if db else {}
            )

    @async_cached_property
    async def loot_elixir(self) -> aPlayerStat:
        db = await self._database
        return aPlayerStat(
            tag=self.tag,
            season=self.season,
            description='loot_elixir',
            dict_value=db.get('loot_elixir',{}) if db else {}
            )
    
    @async_cached_property
    async def loot_darkelixir(self) -> aPlayerStat:
        db = await self._database
        return aPlayerStat(
            tag=self.tag,
            season=self.season,
            description='loot_darkelixir',
            dict_value=db.get('loot_darkelixir',{}) if db else {}
            )
    
    @async_cached_property
    async def capitalcontribution(self) -> aPlayerStat:
        db = await self._database
        return aPlayerStat(
            tag=self.tag,
            season=self.season,
            description='capitalcontribution',
            dict_value=db.get('capitalcontribution',{}) if db else {}
            )
    
    @async_cached_property
    async def clangames(self) -> aPlayerClanGames:
        db = await self._database
        return aPlayerClanGames(
            tag=self.tag,
            season=self.season,
            dict_value=db.get('clangames',{}) if db else {}
            )

    async def update_name(self,new_name:str):
        def _update_in_db():
            db_PlayerStats.objects(
                stats_id=self._db_id
                ).update_one(
                    set__season=self.season.id,
                    set__tag=self.tag,
                    set__name=name,
                    upsert=True
                    )
        async with self._lock:
            name = self.name = new_name
            await bot_client.run_in_write_thread(_update_in_db)
    
    async def update_townhall(self,new_th:int):
        def _update_in_db():
            db_PlayerStats.objects(
                stats_id=self._db_id
                ).update_one(
                    set__season=self.season.id,
                    set__tag=self.tag,
                    set__town_hall=town_hall,
                    upsert=True
                    )
        async with self._lock:
            town_hall = self.town_hall = new_th
            await bot_client.run_in_write_thread(_update_in_db)
    
    async def update_home_clan(self,new_tag:Optional[str]=None):
        def _update_in_db():
            db_PlayerStats.objects(
                stats_id=self._db_id
                ).update_one(
                    set__season=self.season.id,
                    set__tag=self.tag,
                    set__home_clan=tag,
                    upsert=True
                    )
        async with self._lock:
            if new_tag:
                tag = self.home_clan_tag = new_tag
            else:
                tag = self.home_clan_tag = None
            home_clan = await self.home_clan
            await bot_client.run_in_write_thread(_update_in_db)
    
    async def update_member(self,is_member:bool=False):
        def _update_in_db():
            db_PlayerStats.objects(
                stats_id=self._db_id
                ).update_one(
                    set__season=self.season.id,
                    set__tag=self.tag,
                    set__is_member=m,
                    upsert=True
                    )
        async with self._lock:
            m = self.is_member = is_member
            await bot_client.run_in_write_thread(_update_in_db)
    
    async def add_time_in_home_clan(self,duration:int):
        def _update_in_db():
            db_PlayerStats.objects(
                stats_id=self._db_id
                ).update_one(
                    set__season=self.season.id,
                    set__tag=self.tag,
                    set__time_in_home_clan=time_in_home_clan,
                    upsert=True
                    )
        async with self._lock:
            time_in_home_clan = self.time_in_home_clan = await self.time_in_home_clan + duration
            await bot_client.run_in_write_thread(_update_in_db)
            bot_client.coc_data_log.debug(f"{self}: Added {duration} to time in home clan")
    
    async def add_last_seen(self,timestamp:pendulum.DateTime):
        def _update_in_db():
            db_PlayerStats.objects(
                stats_id=self._db_id
                ).update_one(
                    set__season=self.season.id,
                    set__tag=self.tag,
                    set__last_seen=last_seen,
                    upsert=True
                    )
            
        async with self._lock:
            if timestamp.int_timestamp not in await self._last_seen:
                last_seen = self._last_seen.append(timestamp.int_timestamp)
                await bot_client.run_in_write_thread(_update_in_db)
                bot_client.coc_data_log.debug(f"{self}: Added last seen {timestamp}")
        
        