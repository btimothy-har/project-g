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
        
        BasicClan.__init__(self)
        coc.Clan.__init__(self,**kwargs)

        try:
            self.capital_hall = [district.hall_level for district in self.capital_districts if district.name=="Capital Peak"][0]
        except IndexError:
            self.capital_hall = 0            
        self.badge = getattr(self.badge,'url',"")
        self.war_league_name = getattr(self.war_league,'name',"")

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
    def description(self) -> str:
        if self.custom_description:
            return self.custom_description
        return self._description
    @description.setter
    def description(self,value):
        self._description = value

    @property
    def c_description(self) -> str:
        return self.description
    
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

    async def change_description(self,new_desc:str):
        if not self.is_alliance_clan:
            return
        self.custom_description = new_desc