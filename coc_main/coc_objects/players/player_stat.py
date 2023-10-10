from typing import *
from numerize import numerize

from ...api_client import BotClashClient as client
from ..season.season import aClashSeason

bot_client = client()

class aPlayerStat():
    def __init__(self,
        tag:str,
        season:aClashSeason,
        stat_name:str,
        api_value:int,
        dict_value:dict):
        
        self.tag = tag
        self.season = season
        self.description = stat_name

        if 'season' in dict_value:
            self.season_only_clan = dict_value['season']
        else:
            self.season_only_clan = dict_value.get('season_only_clan',0)

        self.season_total = dict_value.get('season_total',0)
        self.last_update = dict_value.get('lastUpdate',api_value)

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
    
    def __json__(self):
        return {
            'season_only_clan': self.season_only_clan,
            'season_total': self.season_total,
            'lastUpdate': self.last_update
            }
    @property
    def json(self):
        return self.__json__()
    @property
    def alliance_only(self):
        if self.last_update >= 2000000000:
            return 'max'
        elif self.season_only_clan >= 100000:
            return f"{numerize.numerize(self.season_only_clan,1)}"
        else:
            return f"{self.season_only_clan:,}"

    async def update_stat(self,
        player,
        new_value:int,
        only_incremental:bool=False):

        #new_value must be higher or equal than last_update
        stat_increment = new_value - self.last_update if new_value >= self.last_update else 0 if only_incremental else new_value
        self.season_total += stat_increment

        if player.timestamp >= self.season.cwl_end and getattr(player.clan,'is_alliance_clan',False):
            self.season_only_clan += stat_increment        
        if stat_increment > 0:
            bot_client.coc_data_log.debug(
                f"{self.tag} {self.season.description}: {self.description} updated to {self.season_only_clan} / {self.season_total} ({stat_increment}). Received: {new_value} vs {self.last_update}."
                )

        self.last_update = new_value
        return stat_increment