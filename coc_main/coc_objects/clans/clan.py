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
        #if self.is_registered_clan or self.is_active_league_clan:
        asyncio.create_task(bot_client.clan_queue.add_many([m.tag for m in self.members]))

        if BasicClan(self.tag).name != self.name:
            await self.set_name(self.name)
        if BasicClan(self.tag).badge != self.badge:
            await self.set_badge(self.badge)
        if BasicClan(self.tag).level != self.level:
            await self.set_level(self.level)
        if BasicClan(self.tag).capital_hall != self.capital_hall:
            await self.set_capital_hall(self.capital_hall)
        if BasicClan(self.tag).war_league_name != self.war_league_name:
            await self.set_war_league(self.war_league_name)

    def war_league_season(self,season:aClashSeason) -> WarLeagueClan:
        return WarLeagueClan(self.tag,season)
    
    ##################################################
    ### CLAN METHODS
    ##################################################
    # async def cleanup_staff(self):
    #     #Remove Leaders from Elders/Cos:
    #     if self.leader in self.coleaders:
    #         self.coleaders.remove(self.leader)
    #     if self.leader in self.elders:
    #         self.elders.remove(self.leader)

    #     for m in self.coleaders:
    #         mem = aMember(m)
    #         if self.tag not in [c.tag for c in mem.home_clans]:
    #             self.coleaders.remove(m)

    #     for m in self.elders:
    #         mem = aMember(m)
    #         if self.tag not in [c.tag for c in mem.home_clans]:
    #             self.elders.remove(m)