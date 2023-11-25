import asyncio

from typing import *
from numerize import numerize

from .mongo_player import db_PlayerStats

from ...api_client import BotClashClient as client
from ..season.season import aClashSeason

bot_client = client()

class aPlayerStat():
    def __init__(self,tag:str,season:aClashSeason,description:str,dict_value:dict):        
        self.tag = tag
        self.season = season
        self.description = description
        self._lock = asyncio.Lock()
        self._prior_seen = dict_value.get('priorSeen',False)

        if 'season' in dict_value:
            self.season_only_clan = dict_value['season']
        else:
            self.season_only_clan = dict_value.get('season_only_clan',0)

        self.season_total = dict_value.get('season_total',0)
        self.last_update = dict_value.get('lastUpdate',0)

        #override for season 5-2023 to account for data migration players
        if self.season.id == '5-2023':
            self.season_only_clan = self.season_total

    def __str__(self):
        if self.last_update >= 2000000000:
            return 'max'
        elif self.season_total >= 100000:
            return f"{numerize.numerize(self.season_total,2)}"
        else:
            return f"{self.season_total:,}"
    
    @property
    def _db_id(self) -> Dict[str,str]:
        return {'season': self.season.id,'tag': self.tag}
    
    @property
    def json(self):
        return {
            'season_only_clan': self.season_only_clan,
            'season_total': self.season_total,
            'lastUpdate': self.last_update,
            'priorSeen': self._prior_seen
            }
    
    @property
    def alliance_only(self):
        if self.last_update >= 2000000000:
            return 'max'
        elif self.season_only_clan >= 100000:
            return f"{numerize.numerize(self.season_only_clan,1)}"
        else:
            return f"{self.season_only_clan:,}"
    
    async def increment_stat(self,
        increment:int,
        latest_value:int,
        db_update:Callable,
        alliance:bool=False) -> 'aPlayerStat': 

        async with self._lock:
            self.last_update = latest_value
            self.season_total += increment
            if alliance:
                self.season_only_clan += increment
            
            self._prior_seen = True

            await db_update(self._db_id,self.json)
        
        #bot_client.coc_data_log.debug(f"{self.season.short_description} {self.tag}: Incremented {self.description} by {increment} to {self.season_total}")
        return self