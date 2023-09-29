import datetime
import pendulum

from typing import *

from coc_client.api_client import BotClashClient

from ..season.season import aClashSeason

class aPlayerClanGames():
    def __init__(self,
        tag:str,
        season:aClashSeason,
        api_value:int,
        dict_value:dict):

        self.client = BotClashClient()
        
        self.tag = tag
        self.season = season    

        self.clan_tag = dict_value.get('clan',None)
        self.score = dict_value.get('score',0)
        self.last_updated = dict_value.get('last_updated',api_value)

        if isinstance(dict_value.get('starting_time'),datetime.datetime):
            if dict_value['starting_time'].timestamp() > 0:
                self.starting_time = pendulum.instance(dict_value['starting_time'])
            else:
                self.starting_time = None
        else:
            if isinstance(dict_value.get('starting_time',0),int) and dict_value.get('starting_time',0) > 0:
                self.starting_time = pendulum.from_timestamp(dict_value.get('starting_time',0))
            else:
                self.starting_time = None

        if isinstance(dict_value.get('ending_time'),datetime.datetime):
            if dict_value['ending_time'].timestamp() > 0:
                self.ending_time = pendulum.instance(dict_value['ending_time'])
            else:
                self.ending_time = None
        else:
            if dict_value.get('ending_time') and int(dict_value.get('ending_time',0)) > 0:
                self.ending_time = pendulum.from_timestamp(dict_value.get('ending_time',0))
            else:
                self.ending_time = None
    
    def __json__(self):
        return {
            'clan': self.clan_tag,
            'score': self.score,
            'last_updated': self.last_updated,
            'starting_time': getattr(self.starting_time,'int_timestamp',None),
            'ending_time': getattr(self.ending_time,'int_timestamp',None)
            }
    @property
    def json(self):
        return self.__json__()    
    @property
    def games_start(self):
        return self.season.clangames_start
    @property
    def games_end(self):
        return self.season.clangames_end
    @property
    def completion(self):
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

    async def calculate_clangames(self,player):
        increment = 0

        if self.games_start <= player.timestamp <= self.games_end.add(days=1):
            new_score = getattr(player.get_achievement('Games Champion'),'value',self.last_updated)
            increment = new_score - self.last_updated

            if increment > 0:                
                if self.score == 0:
                    self.clan_tag = player.clan.tag
                    self.starting_time = player.timestamp                    
                    self.client.cog.coc_data_log.debug(
                        f"Player {self.tag} {self.season.id}: Started Clan Games at {player.timestamp}."
                        )

                self.score += increment
                self.last_updated = new_score
                self.client.cog.coc_data_log.debug(
                    f"Player {self.tag} {self.season.id}: Clan Games score updated to {self.score} ({increment})."
                    )

                if self.score >= self.season.clangames_max:
                    self.ending_time = player.timestamp
                    self.score = self.season.clangames_max
                    self.client.cog.coc_data_log.debug(
                        f"Player {self.tag} {self.season.id}: Finished Clan Games at {player.timestamp}."
                        )
        else:
            self.last_updated = getattr(player.get_achievement('Games Champion'),'value',0)        
        return increment