import pendulum

from typing import *
from mongoengine import *

from .mongo_season import dSeason

class aClashSeason():
    _cache = {}

    def __new__(cls,season_id):
        if season_id not in cls._cache:
            instance = super().__new__(cls)
            instance._is_new = True
            cls._cache[season_id] = instance
        return cls._cache[season_id]

    def __init__(self,season_id):
        if not self._is_new:
            return
        
        self.id = season_id
        self._is_current = False

        if self._is_new:
            self.load()        
        self._is_new = False
    
    def load(self):
        try:
            season_db = dSeason.objects.get(s_id=self.id).to_mongo().to_dict()

            self.season_month = season_db['s_month']
            self.season_year = season_db['s_year']
            self._clangames_max = season_db['clangames_max']
            self._is_current = season_db['s_is_current']
            self._cwl_signup = season_db.get('cwl_signup',False)

        except DoesNotExist:
            self.season_month = int(self.id.split('-')[0])
            self.season_year = int(self.id.split('-')[1])
            self._clangames_max = 4000
            self._cwl_signup = False
    
    def save_season_to_db(self):
        season_db = dSeason(
            s_id=self.id,
            s_is_current=self._is_current,
            s_month=self.season_month,
            s_year=self.season_year,
            clangames_max=self._clangames_max,
            cwl_signup=self._cwl_signup
            )
        season_db.save()
    
    @classmethod
    def get_current_season(cls):
        now = pendulum.now()
        season = aClashSeason(now.format('M-YYYY'))
        if now < season.season_start:
            season = aClashSeason(now.subtract(months=1).format('M-YYYY'))
        return season

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
    
    ##################################################
    ### SEASON PROPERTIES
    ##################################################
    def __eq__(self,other):
        return isinstance(other,aClashSeason) and self.season_start == other.season_start
    
    def __hash__(self) -> int:
        return hash(self.season_start)  
    
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
    
    def previous_season(self):
        return aClashSeason(self.season_start.subtract(months=1).format('M-YYYY'))
    
    def next_season(self):
        return aClashSeason(self.season_end.format('M-YYYY'))
    
    def time_to_end(self,datetime:pendulum.datetime=None):
        if datetime:
            return datetime.diff(self.season_end,False)
        else:
            return pendulum.now().diff(self.season_end,False)

    ##################################################
    ### SEASON HELPERS
    ##################################################        
    @property
    def is_current(self):
        return self._is_current
    @is_current.setter
    def is_current(self,boolean:bool):
        if boolean:
            dSeason.objects(s_is_current=True).update(set__s_is_current=False)
        dSeason.objects(s_id=self.id).update_one(set__s_is_current=boolean)
        self._is_current = boolean
        
    @property
    def is_current_season(self):
        return self.is_current

    @property
    def clangames_max(self):
        return self._clangames_max
    @clangames_max.setter
    def clangames_max(self,value:int):
        dSeason.objects(s_id=self.id).update_one(set__clangames_max=value)
        self._clangames_max = value
 
    @property
    def cwl_signup_lock(self):
        if self.cwl_start.subtract(days=21) < pendulum.now() < self.cwl_start:
            return False
        return True
    
    @property
    def cwl_signup_status(self):
        if not self.cwl_start.subtract(days=21) < pendulum.now() < self.cwl_start.subtract(days=1):
            return False
        return self._cwl_signup
    
    @cwl_signup_status.setter
    def cwl_signup_status(self,value):
        dSeason.objects(s_id=self.id).update_one(set__cwl_signup=value)
        self._cwl_signup = value