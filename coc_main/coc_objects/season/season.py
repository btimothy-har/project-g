import pendulum
import logging
import asyncio

from typing import *
from concurrent.futures import ThreadPoolExecutor
from mongoengine import *

from functools import cached_property

from .mongo_season import dSeason

coc_main_logger = logging.getLogger("coc.main")

class aClashSeason():
    _cache = {}
    _thread_pool = ThreadPoolExecutor(max_workers=1)

    def __new__(cls,id:str):
        if id not in cls._cache:
            instance = super().__new__(cls)
            instance._is_new = True
            cls._cache[id] = instance
        return cls._cache[id]

    def __init__(self,id:str):
        self.id = id
        self.season_month = int(self.id.split('-')[0])
        self.season_year = int(self.id.split('-')[1])

        if self.season_month < 1 or self.season_month > 12:
            raise ValueError(f"Season month must be between 1 and 12. {self.season_month} is invalid.")
        
        if self.season_year < 2021 or self.season_year > pendulum.now().add(years=1).year:
            raise ValueError(f"Season year must be between 2021 and 1 year in the future. {self.season_year} is invalid.")

        if self._is_new:
            self._lock = asyncio.Lock()
        
        self._is_new = False
    
    def __eq__(self,other):
        return isinstance(other,aClashSeason) and self.season_start == other.season_start
    
    def __hash__(self) -> int:
        return hash(self.season_start)
    
    ##################################################
    ### DATABASE ATTRIBUTES
    ##################################################    
    @classmethod
    def get_current_season(cls) -> 'aClashSeason':
        now = pendulum.now()
        season = aClashSeason(now.format('M-YYYY'))
        if now < season.season_start:
            season = aClashSeason(now.subtract(months=1).format('M-YYYY'))
        return season
    
    ##################################################
    ### DATABASE ATTRIBUTES
    ##################################################
    @property
    def _attributes(self) -> Optional[dSeason]:
        try:
            return dSeason.objects.get(s_id=self.id)
        except DoesNotExist:
            return None
    
    @cached_property
    def is_current(self) -> bool:
        return getattr(self._attributes,'s_is_current',False)
        
    @property
    def is_current_season(self) -> bool:
        return self.is_current

    @cached_property
    def clangames_max(self) -> int:
        return getattr(self._attributes,'clangames_max',4000)
 
    @property
    def cwl_signup_lock(self) -> bool:
        if self.cwl_start.subtract(days=20) < pendulum.now() < self.cwl_start.subtract(hours=12):
            return False
        return True
    
    @cached_property
    def _cwl_signup(self) -> bool:
        return getattr(self._attributes,'cwl_signup',False)
    
    @property
    def cwl_signup_status(self) -> bool:
        if self.cwl_signup_lock:
            return False
        return self._cwl_signup

    ##################################################
    ### PROPERTIES
    ##################################################    
    @property
    def season_start(self):
        return pendulum.datetime(self.season_year, self.season_month, 1, 8)
    
    @property
    def season_end(self):
        return pendulum.datetime(self.season_start.add(months=1).year, self.season_start.add(months=1).month, 1, 8)
    
    @property
    def cwl_start(self):
        return self.season_start
    
    @property
    def cwl_end(self):
        return pendulum.datetime(self.season_start.year, self.season_start.month, 10, 8)

    @property
    def clangames_start(self):
        return pendulum.datetime(self.season_start.year, self.season_start.month, 22, 8)
    
    @property
    def clangames_end(self):
        return pendulum.datetime(self.season_start.year, self.season_start.month, 28, 8)

    @property
    def season_description(self):
        return self.season_start.format('MMMM YYYY')
    
    @property
    def description(self):
        return self.season_description
    
    @property
    def short_description(self):
        return self.season_start.format('MMM YYYY')
    
    ##################################################
    ### SEASON METHODS
    ##################################################
    def previous_season(self):
        return aClashSeason(self.season_start.subtract(months=1).format('M-YYYY'))
    
    def next_season(self):
        return aClashSeason(self.season_end.format('M-YYYY'))
    
    def time_to_end(self,datetime:pendulum.datetime=None):
        if datetime:
            return datetime.diff(self.season_end,False)
        else:
            return pendulum.now().diff(self.season_end,False)
    
    async def set_as_current(self):
        def _update_in_db():
            dSeason.objects(s_id=self.id).update_one(set__s_is_current=True,upsert=True)
            dSeason.objects(s_id__ne=self.id).update_one(set__s_is_current=False)
            coc_main_logger.info(f"Season {self.id} {self.description} set as current season.")

        async with self._lock:
            self.is_current = True
            existing = [s for s in aClashSeason._cache.values() if s.is_current and s != self]
            for season in existing:
                season.is_current = False
            
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(aClashSeason._thread_pool,_update_in_db)
    
    async def open_cwl_signups(self):
        def _update_in_db():
            dSeason.objects(s_id=self.id).update_one(set__cwl_signup=True,upsert=True)
            coc_main_logger.info(f"Season {self.id} {self.description} CWL signups opened.")

        async with self._lock:
            self._cwl_signup = True
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(aClashSeason._thread_pool,_update_in_db)

    async def close_cwl_signups(self):
        def _update_in_db():
            dSeason.objects(s_id=self.id).update_one(set__cwl_signup=False,upsert=True)
            coc_main_logger.info(f"Season {self.id} {self.description} CWL signups closed.")

        async with self._lock:
            self._cwl_signup = False
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(aClashSeason._thread_pool,_update_in_db)
    
    ##################################################
    ### STATIC METHODS
    ##################################################    
    @staticmethod
    async def get_raid_weekend_dates(datetime:pendulum.datetime=None):
        if not datetime:
            datetime = pendulum.now('UTC')
        
        if datetime.day_of_week == pendulum.FRIDAY:
            raid_start = pendulum.datetime(datetime.year, datetime.month, datetime.day, 7)
            raid_end = datetime.next(pendulum.MONDAY).add(hours=7)
        elif datetime.day_of_week in [pendulum.SATURDAY,pendulum.SUNDAY]:
            raid_start = datetime.previous(pendulum.FRIDAY).add(hours=7)
            raid_end = datetime.next(pendulum.MONDAY).add(hours=7)
        elif datetime.day_of_week == pendulum.MONDAY:
            raid_start = datetime.previous(pendulum.FRIDAY).add(hours=7)
            raid_end = pendulum.datetime(datetime.year, datetime.month, datetime.day, 7)            
        else:
            raid_start = datetime.next(pendulum.FRIDAY).add(hours=7)
            raid_end = datetime.next(pendulum.MONDAY).add(hours=7)        
        return raid_start, raid_end
    
    @staticmethod
    def last_completed_clangames():
        current_season = aClashSeason.get_current_season()
        return current_season if pendulum.now() >= current_season.clangames_start else current_season.previous_season()