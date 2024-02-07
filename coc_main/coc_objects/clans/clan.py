import coc
import pendulum
import asyncio

from typing import *
from async_property import AwaitLoader

from ...api_client import BotClashClient as client

from .base_clan import BasicClan

from ...utils.constants.coc_emojis import EmojisClash, EmojisCapitalHall, EmojisLeagues
from ...utils.constants.ui_emojis import EmojisUI

bot_client = client()

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
            base['leader'] = getattr(bot_client.bot.get_user(self.leader),'display_name','No Leader')
            base['coleaders'] = [bot_client.bot.get_user(i).display_name for i in self.coleaders if bot_client.bot.get_user(i)]
            base['elders'] = [bot_client.bot.get_user(i).display_name for i in self.elders if bot_client.bot.get_user(i)]
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
    
    async def _sync_cache(self,force:bool=False):
        if force:
            pass
        else:
            if self._attributes._last_sync and pendulum.now().int_timestamp - self._attributes._last_sync.int_timestamp <= 3600:
                return
        
        if self._attributes._sync_lock.locked():
            return
        
        async with self._attributes._sync_lock:
            basic_clan = await BasicClan(self.tag)
            await basic_clan._attributes.load_data()

            if basic_clan._attributes._last_sync and basic_clan._attributes._last_sync.int_timestamp >= self.timestamp.int_timestamp:
                return
            
            await basic_clan.update_last_sync(pendulum.now())
            if bot_client.bot.user.id == 1031240380487831664:
                #only nebula to handle elders/coleaders
                tasks = [
                    basic_clan.clean_elders(),
                    basic_clan.clean_coleaders(),
                    ]
            else:
                tasks = []

            if basic_clan.name != self.name:
                tasks.append(basic_clan.set_name(self.name))
            if basic_clan.badge != self.badge:
                tasks.append(basic_clan.set_badge(self.badge))
            if basic_clan.level != self.level:
                tasks.append(basic_clan.set_level(self.level))
            if basic_clan.capital_hall != self.capital_hall:
                tasks.append(basic_clan.set_capital_hall(self.capital_hall))
            if basic_clan.war_league_name != self.war_league_name:
                tasks.append(basic_clan.set_war_league(self.war_league_name))            
            if tasks:
                await asyncio.gather(*tasks)