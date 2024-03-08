import asyncio
import pendulum
import logging
import motor.motor_asyncio

from typing import *

from collections import defaultdict

from ...client.db_client import MotorClient
from ...exceptions import SeasonNotLoaded

LOG = logging.getLogger("coc.main")

# d_season = {
#     '_id': string,
#     's_is_current': bool,
#     's_month': int,
#     's_year': int,
#     'clangames_max': int,
#     'cwl_signup': bool
#     }

class aClashSeason(MotorClient):
    _cache = {}
    _locks = defaultdict(asyncio.Lock)

    __slots__ = [
        '_is_new',
        'id',
        'season_month',
        'season_year'
        'is_current',
        'clangames_max',
        'cwl_signup'
        ]
    
    @classmethod
    async def load_seasons(cls) -> List['aClashSeason']:
        ret_seasons = []

        find_seasons = cls.database.d_season.find({})
        async for db_season in find_seasons:
            season = cls(db_season['_id'])
            await season.load()
            ret_seasons.append(season)        
        return ret_seasons
    
    @classmethod
    def current(cls) -> 'aClashSeason':
        try:
            return [s for s in list(cls._cache.values()) if s.is_current][0]
        except IndexError as e:
            raise SeasonNotLoaded() from e
    
    @classmethod
    def tracked(cls) -> List['aClashSeason']:
        seasons = [s for s in list(cls._cache.values()) if not s.is_current]
        if len(seasons) == 0:
            raise SeasonNotLoaded()
        return sorted(seasons,
            key=lambda x: x.season_start.int_timestamp,
            reverse=True
            )

    @classmethod
    def all_seasons(cls) -> List['aClashSeason']:
        seasons = [s for s in list(cls._cache.values())]
        if len(seasons) == 0:
            raise SeasonNotLoaded()
        return sorted(seasons,
            key=lambda x: x.season_start.int_timestamp,
            reverse=True
            )    

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
            self.is_current = False
            self.clangames_max = 4000
            self.cwl_signup = False
        
        self._is_new = False
    
    def __eq__(self,other):
        return isinstance(other,aClashSeason) and self.season_start == other.season_start
    
    def __hash__(self) -> int:
        return hash(self.season_start)

    async def load(self):
        season = await self.database.d_season.find_one({'_id':self.id})

        self.is_current = season.get('s_is_current',False) if season else False
        self.clangames_max = season.get('clangames_max',4000) if season else 4000
        self.cwl_signup = season.get('cwl_signup',False) if season else False
    
    ##################################################
    ### DATABASE ATTRIBUTES
    ##################################################    
    @property
    def _lock(self) -> asyncio.Lock:
        return self._locks[self.id]
    
    ##################################################
    ### DATABASE ATTRIBUTES
    ##################################################        
    @property
    def is_current_season(self) -> bool:
        return self.is_current 
    @property
    def cwl_signup_lock(self) -> bool:
        if self.cwl_start.subtract(days=20) < pendulum.now() < self.cwl_start.subtract(hours=12):
            return False
        return True    
    @property
    def cwl_signup_status(self) -> bool:
        if self.cwl_signup_lock:
            return False
        return self.cwl_signup

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
    def trophy_season_start(self):
        last_day_of_last_month = pendulum.datetime(self.season_start.subtract(months=1).year, self.season_start.subtract(months=1).month, 1).end_of('month')
        for day in range(last_day_of_last_month.day, 0, -1):
            date = pendulum.datetime(last_day_of_last_month.year, last_day_of_last_month.month, day,5,0,0)
            if date.day_of_week == pendulum.MONDAY:
                return date                
    @property
    def trophy_season_end(self):
        last_day_of_this_month = pendulum.datetime(self.season_start.year, self.season_start.month, 1).end_of('month')
        for day in range(last_day_of_this_month.day, 0, -1):
            date = pendulum.datetime(last_day_of_this_month.year, last_day_of_this_month.month, day,5,0,0)
            if date.day_of_week == pendulum.MONDAY:
                return date
    
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
        async with self._lock:
            await self.database.d_season.update_one(
                {'_id':self.id},
                {'$set': {
                    's_is_current':True
                    }
                },
                upsert=True
                )
            await self.database.d_season.update_many(
                {'_id':{'$ne':self.id}},
                {'$set': {
                    's_is_current':False
                    }
                }
                )
            LOG.info(f"Season {self.id} {self.description} set as current season.")
    
    async def open_cwl_signups(self):            
        async with self._lock:
            self.cwl_signup = True
            await self.database.d_season.update_one(
                {'_id':self.id},
                {'$set': 
                    {'cwl_signup':True}
                },
                upsert=True
                )
            LOG.info(f"Season {self.id} {self.description} CWL signups opened.")

    async def close_cwl_signups(self):
        async with self._lock:
            self.cwl_signup = False
            await self.database.d_season.update_one(
                {'_id':self.id},
                {'$set': 
                    {'cwl_signup':False}
                },
                upsert=True
                )
            LOG.info(f"Season {self.id} {self.description} CWL signups closed.")
    
    ##################################################
    ### STATIC METHODS
    ##################################################    
    @staticmethod
    def get_raid_weekend_dates(datetime:pendulum.datetime=None):
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
        current_season = aClashSeason.current()
        return current_season if pendulum.now() >= current_season.clangames_start else current_season.previous_season()