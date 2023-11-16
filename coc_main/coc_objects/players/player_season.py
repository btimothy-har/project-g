import asyncio
import pendulum

from typing import *
from mongoengine import *

from functools import cached_property

from ...api_client import BotClashClient as client
from ..season.season import aClashSeason

from .mongo_player import db_PlayerStats
from .player_stat import aPlayerStat
from .player_clangames import aPlayerClanGames

from ..clans.player_clan import aPlayerClan
from ...utils.utils import check_rtl

bot_client = client()

class aPlayerSeason():
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
    
    @property
    def _database(self) -> Optional[db_PlayerStats]:
        try:
            return db_PlayerStats.objects.get(stats_id=self._db_id)
        except DoesNotExist:
            return None
    
    @cached_property
    def name(self) -> str:
        return getattr(self._database,'name','')
    
    @property
    def clean_name(self) -> str:
        if check_rtl(self.name):
            return '\u200F' + self.name + '\u200E'
        return self.name    
    
    @cached_property
    def town_hall(self) -> int:
        return getattr(self._database,'town_hall',0)
    
    @cached_property
    def is_member(self) -> bool:
        return getattr(self._database,'is_member',False)
    
    @cached_property
    def home_clan_tag(self) -> Optional[str]:
        return getattr(self._database,'home_clan',None)
    
    @property
    def home_clan(self) -> Optional[aPlayerClan]:
        if self.home_clan_tag:
            return aPlayerClan(tag=self.home_clan_tag)
        return None
    
    @cached_property
    def other_clan_tags(self) -> List[str]:
        return getattr(self._database,'other_clans',[])
    
    @cached_property
    def time_in_home_clan(self) -> int:
        return getattr(self._database,'time_in_home_clan',0)
    
    @cached_property
    def _last_seen(self) -> List[int]:
        return sorted(getattr(self._database,'last_seen',[]))
        
    @property
    def last_seen(self) -> List[pendulum.DateTime]:
        return [pendulum.from_timestamp(x) for x in list(set(self._last_seen))]
    
    @cached_property
    def attacks(self) -> aPlayerStat:
        return aPlayerStat(
            tag=self.tag,
            season=self.season,
            description='attack_wins',
            dict_value=getattr(self._database,'attacks',{})
            )

    @cached_property
    def defenses(self) -> aPlayerStat:
        return aPlayerStat(
            tag=self.tag,
            season=self.season,
            description='defense_wins',
            dict_value=getattr(self._database,'defenses',{})
            )
    
    @cached_property
    def donations_sent(self) -> aPlayerStat:
        return aPlayerStat(
            tag=self.tag,
            season=self.season,
            description='donations_sent',
            dict_value=getattr(self._database,'donations_sent',{})
            )
    
    @property
    def donations(self) -> aPlayerStat:
        return self.donations_sent

    @cached_property
    def donations_rcvd(self) -> aPlayerStat:
        return aPlayerStat(
            tag=self.tag,
            season=self.season,
            description='donations_rcvd',
            dict_value=getattr(self._database,'donations_rcvd',{})
            )
    @property
    def received(self) -> aPlayerStat:
        return self.donations_rcvd

    @cached_property
    def loot_gold(self) -> aPlayerStat:
        return aPlayerStat(
            tag=self.tag,
            season=self.season,
            description='loot_gold',
            dict_value=getattr(self._database,'loot_gold',{})
            )

    @cached_property
    def loot_elixir(self) -> aPlayerStat:
        return aPlayerStat(
            tag=self.tag,
            season=self.season,
            description='loot_elixir',
            dict_value=getattr(self._database,'loot_elixir',{})
            )
    
    @cached_property
    def loot_darkelixir(self) -> aPlayerStat:
        return aPlayerStat(
            tag=self.tag,
            season=self.season,
            description='loot_darkelixir',
            dict_value=getattr(self._database,'loot_darkelixir',{})
            )
    
    @cached_property
    def capitalcontribution(self) -> aPlayerStat:
        return aPlayerStat(
            tag=self.tag,
            season=self.season,
            description='capitalcontribution',
            dict_value=getattr(self._database,'capitalcontribution',{})
            )
    
    @cached_property
    def clangames(self) -> aPlayerClanGames:
        return aPlayerClanGames(
            tag=self.tag,
            season=self.season,
            dict_value=getattr(self._database,'clangames',{})
            )

    async def update_name(self,new_name:str):
        def _update_in_db():
            db_PlayerStats.objects(
                stats_id=self._db_id
                ).update_one(
                    set__season=self.season.id,
                    set__tag=self.tag,
                    set__name=self.name,
                    upsert=True
                    )
        async with self._lock:
            self.name = new_name
            await bot_client.run_in_thread(_update_in_db)
    
    async def update_townhall(self,new_th:int):
        def _update_in_db():
            db_PlayerStats.objects(
                stats_id=self._db_id
                ).update_one(
                    set__season=self.season.id,
                    set__tag=self.tag,
                    set__town_hall=self.town_hall,
                    upsert=True
                    )
        async with self._lock:
            self.town_hall = new_th
            await bot_client.run_in_thread(_update_in_db)
    
    async def update_home_clan(self,new_tag:Optional[str]=None):
        def _update_in_db():
            db_PlayerStats.objects(
                stats_id=self._db_id
                ).update_one(
                    set__season=self.season.id,
                    set__tag=self.tag,
                    set__home_clan=getattr(self.home_clan,'tag',None),
                    upsert=True
                    )
        async with self._lock:
            if new_tag:
                self.home_clan_tag = new_tag
            else:
                self.home_clan_tag = None
            await bot_client.run_in_thread(_update_in_db)
    
    async def update_member(self,is_member:bool=False):
        def _update_in_db():
            db_PlayerStats.objects(
                stats_id=self._db_id
                ).update_one(
                    set__season=self.season.id,
                    set__tag=self.tag,
                    set__is_member=self.is_member,
                    upsert=True
                    )
        async with self._lock:
            self.is_member = is_member
            await bot_client.run_in_thread(_update_in_db)
    
    async def add_time_in_home_clan(self,duration:int):
        def _update_in_db():
            db_PlayerStats.objects(
                stats_id=self._db_id
                ).update_one(
                    set__season=self.season.id,
                    set__tag=self.tag,
                    set__time_in_home_clan=self.time_in_home_clan,
                    upsert=True
                    )
        async with self._lock:
            self.time_in_home_clan += duration
            await bot_client.run_in_thread(_update_in_db)
            bot_client.coc_data_log.debug(f"{self}: Added {duration} to time in home clan")
    
    async def add_last_seen(self,timestamp:pendulum.DateTime):
        def _update_in_db():
            db_PlayerStats.objects(
                stats_id=self._db_id
                ).update_one(
                    set__season=self.season.id,
                    set__tag=self.tag,
                    set__last_seen=self._last_seen,
                    upsert=True
                    )
            
        async with self._lock:
            if timestamp.int_timestamp not in self._last_seen:
                self._last_seen.append(timestamp.int_timestamp)
                await bot_client.run_in_thread(_update_in_db)
                bot_client.coc_data_log.debug(f"{self}: Added last seen {timestamp}")
        
        