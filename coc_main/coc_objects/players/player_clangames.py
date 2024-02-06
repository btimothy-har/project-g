import asyncio
import datetime
import pendulum

from typing import *

from .player_stat import aPlayerActivity

from ..season.season import aClashSeason
from ...api_client import BotClashClient as client

bot_client = client()

class aPlayerClanGames():
    __slots__ = [
        'tag',
        'season',
        'clan_tag',
        'starting_time',
        '_score',
        'ending_time'
        ]
    
    def __init__(self,tag:str,season:aClashSeason,activities:List[aPlayerActivity]):        
        self.tag = tag
        self.season = season

        if len(activities) == 0:
            self.clan_tag = None
            self.starting_time = None
            self._score = 0
            self.ending_time = None
        
        else:
            first_entry = activities[0]
            last_entry = activities[-1]

            self.clan_tag = first_entry.clan
            self.starting_time = first_entry.timestamp

            self._score = sum([activity.change for activity in activities if activity.activity == 'clangames'])
            self._ending_time = last_entry.timestamp
    
    @property
    def games_start(self):
        return self.season.clangames_start    
    @property
    def games_end(self):
        return self.season.clangames_end    
    @property
    def is_participating(self) -> bool:
        return self.clan_tag is not None    
    @property
    def is_completed(self) -> bool:
        return self.score >= self.season.clangames_max    
    @property
    def score(self) -> int:
        return min(self._score,self.season.clangames_max)    
    @property
    def ending_time(self) -> Optional[pendulum.DateTime]:
        if self.is_completed:
            return self._ending_time
        return None    
    @property
    def completion(self) -> Optional[pendulum.Duration]:
        if self.ending_time:
            return self.games_start.diff(self.ending_time)
        else:
            return None        
    @property
    def completion_seconds(self) -> int:
        if self.ending_time:
            return self.completion.in_seconds()
        else:
            return 0        
    @property
    def time_to_completion(self):
        if self.ending_time:
            if self.ending_time.int_timestamp - self.games_start.int_timestamp <= 50:
                return "Not Tracked"            
            completion_str = ""
            if self.completion.days > 0:
                completion_str += f"{self.completion.days}d"
            if self.completion.hours > 0:
                completion_str += f" {self.completion.hours}h"
            if self.completion.minutes > 0:
                completion_str += f" {self.completion.minutes}m"
            return completion_str
        else:
            return ""