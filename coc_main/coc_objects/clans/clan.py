import coc
import pendulum

from typing import *
from mongoengine import *

from ...api_client import BotClashClient as client

from .base_clan import *

from ..season.season import aClashSeason
from ..events.clan_war_leagues import WarLeagueGroup, WarLeagueClan
from ..events.clan_war import aClanWar
from ..events.raid_weekend import aRaidWeekend

from ...utils.constants.coc_emojis import EmojisClash, EmojisCapitalHall, EmojisLeagues
from ...utils.constants.ui_emojis import EmojisUI

bot_client = client()

class aClan(coc.Clan,BasicClan):
    def __init__(self,**kwargs):

        self._name = None
        self._description = None
        self._badge = None
        self._level = None
        
        coc.Clan.__init__(self,**kwargs)
        BasicClan.__init__(self,tag=self.tag)

        self.timestamp = pendulum.now()
        self._badge = getattr(self.badge,'url',"")   

    ##################################################
    ### DATA FORMATTERS
    ##################################################
    def __str__(self) -> str:
        return f"{self.name} ({self.tag})"
    
    def __eq__(self,other) -> bool:
        return isinstance(other,aClan) and self.tag == other.tag
    
    def __hash__(self):
        return hash(self.tag)
    
    @property
    def name(self) -> str:
        return self._name
    @name.setter
    def name(self,value:str):
        self._name = value
    
    @property
    def description(self) -> str:
        if len(BasicClan(self.tag).description) > 0:
            return BasicClan(self.tag).description
        return self._description
    @description.setter
    def description(self,value:str):
        self._description = value

    @property
    def badge(self) -> str:
        return self._badge
    @badge.setter
    def badge(self,value:str):
        self._badge = value
    
    @property
    def level(self) -> int:
        return self._level
    @level.setter
    def level(self,value:int):
        self._level = value
    
    @property
    def capital_hall(self) -> int:
        try:
            return [district.hall_level for district in self.capital_districts if district.name=="Capital Peak"][0]
        except IndexError:
            return 0
    
    @property
    def war_league_name(self) -> str:
        return getattr(self.war_league,'name',"")
    
    @property
    def long_description(self) -> str:
        description = f"{EmojisClash.CLAN} Level {self.level}\u3000"
        description += f"{EmojisUI.MEMBERS} {self.member_count}" + (f" (R:{self.alliance_member_count})" if self.is_alliance_clan else "") + "\u3000"
        description += f"{EmojisUI.GLOBE} {self.location.name}\n"
        description += (f"{EmojisClash.CLANWAR} W{self.war_wins}/D{self.war_ties}/L{self.war_losses} (Streak: {self.war_win_streak})\n" if self.public_war_log else "")
        description += f"{EmojisClash.WARLEAGUES}" + (f"{EmojisLeagues.get(self.war_league.name)} {self.war_league.name}\n" if self.war_league else "Unranked\n")
        description += f"{EmojisCapitalHall.get(self.capital_hall)} CH {self.capital_hall}\u3000"
        description += f"{EmojisClash.CAPITALTROPHY} {self.capital_points}\u3000"
        description += (f"{EmojisLeagues.get(self.capital_league.name)} {self.capital_league}" if self.capital_league else f"{EmojisLeagues.UNRANKED} Unranked") #+ "\n"
        #description += f"**[Clan Link: {self.tag}]({self.share_link})**"
        return description
    
    @property
    def summary_description(self) -> str:
        war_league_str = f"{EmojisLeagues.get(self.war_league.name)} {self.war_league.name}" if self.war_league else ""
        description = f"{EmojisClash.CLAN} Level {self.level}\u3000{EmojisCapitalHall.get(self.capital_hall)} CH {self.capital_hall}\u3000{war_league_str}"
        return description
    
    async def _sync_cache(self):
        asyncio.create_task(bot_client.player_queue.add_many([m.tag for m in self.members]))

        if self._attributes._last_sync and pendulum.now().int_timestamp - self._attributes._last_sync.int_timestamp <= 600:
            return        
        if self._attributes._sync_lock.locked():
            return
        
        async with self._attributes._sync_lock:            
            basic_clan = BasicClan(self.tag)

            tasks = []

            if await basic_clan.name != self.name:
                tasks.append(basic_clan.set_name(self.name))

            if await basic_clan.badge != self.badge:
                tasks.append(basic_clan.set_badge(self.badge))

            if await basic_clan.level != self.level:
                tasks.append(basic_clan.set_level(self.level))

            if await basic_clan.capital_hall != self.capital_hall:
                tasks.append(basic_clan.set_capital_hall(self.capital_hall))

            if await basic_clan.war_league_name != self.war_league_name:
                tasks.append(basic_clan.set_war_league(self.war_league_name))
            
            if tasks:
                await asyncio.gather(*tasks)
                basic_clan._attributes._last_sync = pendulum.now()

    def war_league_season(self,season:aClashSeason) -> WarLeagueClan:
        return WarLeagueClan(self.tag,season)