import coc
import pendulum
import asyncio

from typing import *
from async_property import AwaitLoader

from .base_clan import BasicClan

from ...utils.constants.coc_emojis import EmojisClash, EmojisCapitalHall, EmojisLeagues
from ...utils.constants.ui_emojis import EmojisUI

class aClan(coc.Clan,BasicClan,AwaitLoader):
    def __init__(self,**kwargs):

        self._name = None
        self._description = None
        self._badge = None
        self._level = None
        
        coc.Clan.__init__(self,**kwargs)
        BasicClan.__init__(self,tag=self.tag)

        self.timestamp = pendulum.now()
        self._badge = getattr(self.badge,'url',"")
    
    async def load(self):
        await BasicClan.load(self)
    
    def assistant_name_json(self) -> dict:
        return {
            'tag': self.tag,
            'name': self.name,
            'share_link': self.share_link,
            }

    def assistant_clan_information(self) -> dict:
        base = {
            'tag': self.tag,
            'name': self.name,
            'level': self.level,
            'location': getattr(self.location,'name','Not Provided'),
            'description': self.description,
            'share_link': self.share_link,
            'capital_hall': self.capital_hall,
            'clan_war_league': self.war_league_name,            
            }
        if self.abbreviation:
            base['abbreviation'] = self.abbreviation
        if self.emoji:
            base['emoji'] = self.emoji
        if self.is_alliance_clan:
            base['member_count'] = self.alliance_member_count
            base['leader'] = getattr(self.bot.get_user(self.leader),'display_name','No Leader')
            base['coleaders'] = [self.bot.get_user(i).display_name for i in self.coleaders if self.bot.get_user(i)]
            base['elders'] = [self.bot.get_user(i).display_name for i in self.elders if self.bot.get_user(i)]
        else:
            base['member_count'] = self.member_count
        return base

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
    def total_clan_donations(self) -> int:
        return sum([member.donations for member in self.members]) + sum([member.received for member in self.members])
    
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
        description += f"{EmojisUI.GLOBE} {getattr(self.location,'name','No Location')}\n"
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
    
    @classmethod
    async def _sync_cache(cls,clan:'aClan',force:bool=False):        
        basic_clan = await BasicClan(clan.tag)
        await basic_clan._attributes.load_data()
        
        if not force:
            if basic_clan._attributes._last_sync and pendulum.now().int_timestamp - basic_clan._attributes._last_sync.int_timestamp <= 3600:
                return
        
        async with basic_clan._attributes._sync_lock:
            if basic_clan._attributes._last_sync and basic_clan._attributes._last_sync.int_timestamp >= clan.timestamp.int_timestamp:
                return
            
            await basic_clan.update_last_sync(pendulum.now())

            tasks = []

            if basic_clan.name != clan.name:
                tasks.append(basic_clan.set_name(clan.name))

            if basic_clan.badge != clan.badge:
                tasks.append(basic_clan.set_badge(clan.badge))

            if basic_clan.level != clan.level:
                tasks.append(basic_clan.set_level(clan.level))

            if basic_clan.capital_hall != clan.capital_hall:
                tasks.append(basic_clan.set_capital_hall(clan.capital_hall))

            if basic_clan.war_league_name != clan.war_league_name:
                tasks.append(basic_clan.set_war_league(clan.war_league_name))            

            if tasks:
                await asyncio.gather(*tasks)

class _PlayerClan(coc.PlayerClan,BasicClan):
    def __init__(self,**kwargs):

        self._name = None
        self._badge = None
        self._level = None

        coc.PlayerClan.__init__(self,**kwargs)
        BasicClan.__init__(self,self.tag)
    
    def to_json(self) -> dict:
        return {
            'tag': self.tag,
            'name': self.name,
            'level': self.level,
            }
    
    @property
    def name(self) -> str:
        return self._name
    @name.setter
    def name(self,value:str):
        self._name = value

    @property
    def badge(self) -> Optional[str]:
        if self._badge:
            return self._badge.url
        return None
    @badge.setter
    def badge(self,badge:coc.Badge):
        self._badge = badge
    
    @property
    def level(self) -> int:
        return self._level
    @level.setter
    def level(self,value:int):
        self._level = value