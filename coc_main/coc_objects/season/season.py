import pendulum

from typing import *
from mongoengine import *

from .mongo_season import dSeason

class aClashSeason(): 

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
    
    @classmethod
    def get_current_season(cls):
        now = pendulum.now()
        season = aClashSeason(now.format('M-YYYY'))
        if now < season.season_start:
            season = aClashSeason(now.subtract(months=1).format('M-YYYY'))
        return season

    def __init__(self,season_id:str):
        self.id = season_id
        self.season_month = int(self.id.split('-')[0])
        self.season_year = int(self.id.split('-')[1])

        if self.season_month < 1 or self.season_month > 12:
            raise ValueError(f"Season month must be between 1 and 12. {self.season_month} is invalid.")
        
        if self.season_year < 2021 or self.season_year > pendulum.now().add(years=1).year:
            raise ValueError(f"Season year must be between 2021 and 1 year in the future. {self.season_year} is invalid.")
    

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
    
    ##################################################
    ### SEASON VALUES
    ##################################################
    @property
    def database_attributes(self) -> Optional[dSeason]:
        try:
            return dSeason.objects.get(tag=self.tag)
        except DoesNotExist:
            return None
    
    @property
    def is_current(self) -> bool:
        return getattr(self.database_attributes,'s_is_current',False)
    @is_current.setter
    def is_current(self,boolean:bool):
        if boolean:
            dSeason.objects(s_is_current=True).update_one(set__s_is_current=False,upsert=True)
        dSeason.objects(s_id=self.id).update(set__s_is_current=boolean)
        
    @property
    def is_current_season(self) -> bool:
        return self.is_current

    @property
    def clangames_max(self) -> int:
        return getattr(self.database_attributes,'clangames_max',4000)
    @clangames_max.setter
    def clangames_max(self,value:int):
        dSeason.objects(s_id=self.id).update_one(set__clangames_max=value,upsert=True)
 
    @property
    def cwl_signup_lock(self) -> bool:
        if self.cwl_start.subtract(days=21) < pendulum.now() < self.cwl_start:
            return False
        return True
    
    @property
    def cwl_signup_status(self) -> bool:
        if not self.cwl_start.subtract(days=21) < pendulum.now() < self.cwl_start.subtract(days=1):
            return False
        return getattr(self.database_attributes,'cwl_signup',False)
    @cwl_signup_status.setter
    def cwl_signup_status(self,value:bool) -> bool:
        dSeason.objects(s_id=self.id).update_one(set__cwl_signup=value,upsert=True)