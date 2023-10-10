import pendulum

from typing import *

from collections import defaultdict
from redbot.core.utils import AsyncIter

from .clan_war import aClanWar

from ...utils.components import s_convert_seconds_to_str

default_structure = lambda: {
    'attacker': None,
    'defender': None,
    'total': 0,
    'stars': 0,
    'destruction': 0,
    'triples': 0
    }

class aClanWarSummary():
    def __init__(self,war_log:List[aClanWar]):
        
        self.timestamp = pendulum.now()    

        self.player_tag = None
        self.clan_tag = None

        self.war_log = war_log
        self.wars_participated = len(self.war_log) if self.war_log else 0
    
    @classmethod
    def for_player(cls,player_tag:str,war_log:List[aClanWar]):
        instance = cls([w for w in war_log if w.get_member(player_tag)])
        instance.player_tag = player_tag
        return instance

    @classmethod
    def for_clan(cls,clan_tag:str,war_log:List[aClanWar]):
        instance = cls(war_log)
        instance.clan_tag = clan_tag
        return instance
    
    @property
    def attack_count(self) -> int:
        try:
            if self.player_tag:
                return sum(
                    [len(war.get_member(self.player_tag).attacks)
                    for war in self.war_log]
                    )
            if self.clan_tag:
                return sum(
                    [war.get_clan(self.clan_tag).attacks_used for war in self.war_log]
                    )
        except:
            return 0
    
    @property
    def offense_stars(self) -> int:
        try:
            if self.player_tag:
                return sum(
                    [sum([attack.stars for attack in war.get_member(self.player_tag).attacks])
                    for war in self.war_log]
                    )
            if self.clan_tag:
                return sum(
                    [war.get_clan(self.clan_tag).stars for war in self.war_log]
                    )
        except:
            return 0
    
    @property
    def offense_destruction(self) -> int:
        try:
            if self.player_tag:
                return sum(
                    [sum([attack.destruction for attack in war.get_member(self.player_tag).attacks])
                    for war in self.war_log]
                    )
            if self.clan_tag:
                return sum(
                    [war.get_clan(self.clan_tag).destruction for war in self.war_log]
                    )
        except:
            return 0
    
    @property
    def defense_count(self) -> int:
        try:
            if self.player_tag:
                return sum(
                    [war.get_member(self.player_tag).defense_count
                    for war in self.war_log]
                    )
            if self.clan_tag:
                return sum(
                    [len(war.get_clan(self.clan_tag).defenses)
                    for war in self.war_log]
                    )
        except:
            return 0
    
    @property
    def defense_stars(self) -> int:
        try:
            if self.player_tag:
                return sum(
                    [getattr(war.get_member(self.player_tag).best_opponent_attack,'stars',0)
                    for war in self.war_log]
                    )
            if self.clan_tag:
                return sum(
                    [war.get_opponent(self.clan_tag).stars for war in self.war_log]
                    )
        except:
            return 0
    
    @property
    def defense_destruction(self) -> int:
        try:
            if self.player_tag:
                return sum(
                    [getattr(war.get_member(self.player_tag).best_opponent_attack,'destruction',0)
                    for war in self.war_log]
                    )
            if self.clan_tag:
                return sum(
                    [war.get_opponent(self.clan_tag).destruction for war in self.war_log]
                    )
        except:
            return 0
    
    @property
    def triples(self) -> int:
        try:
            if self.player_tag:
                return sum(
                    [len([attack for attack in war.get_member(self.player_tag).attacks if attack.is_triple])
                    for war in self.war_log]
                    )
            if self.clan_tag:
                return sum(
                    [len([attack for attack in war.get_clan(self.clan_tag).attacks if attack.is_triple])
                    for war in self.war_log]
                    )
        except:
            return 0
    
    @property
    def unused_attacks(self) -> int:
        try:
            if self.player_tag:
                return sum(
                    [war.get_member(self.player_tag).unused_attacks
                    for war in self.war_log]
                    )
            if self.clan_tag:
                return sum(
                    [((war.attacks_per_member * war.team_size) - war.get_clan(self.clan_tag).attacks_used)
                    for war in self.war_log]
                    )
        except:
            return 0
    
    @property
    def average_new_stars(self) -> float:
        try:
            if self.player_tag:
                total_new_star = sum([attack.new_stars for war in self.war_log for attack in war.get_member(self.player_tag).attacks])
                return round(total_new_star / self.attack_count,2)
            
            if self.clan_tag:
                total_new_star = sum([attack.new_stars for war in self.war_log for attack in war.get_clan(self.clan_tag).attacks])
                return round(total_new_star / self.attack_count,2)
        except:
            return 0
    
    @property
    def average_attack_duration(self) -> float:
        try:
            if self.player_tag:
                total_duration = sum([attack.duration for war in self.war_log for attack in war.get_member(self.player_tag).attacks if attack.duration <= 180])
                duration_count = sum([1 for war in self.war_log for attack in war.get_member(self.player_tag).attacks if attack.duration <= 180])
                return total_duration / duration_count
            
            if self.clan_tag:
                total_duration = sum([attack.duration for war in self.war_log for attack in war.get_clan(self.clan_tag).attacks if attack.duration <= 180])
                duration_count = sum([1 for war in self.war_log for attack in war.get_clan(self.clan_tag).attacks if attack.duration <= 180])
                return total_duration / duration_count 
        except:
            return 0
    
    async def hit_rate_for_th(self,th_level:int) -> dict:
        hit_rate = defaultdict(default_structure)
        try:
            if self.player_tag:
                attacks_for_th = [attack for war in self.war_log for attack in war.get_member(self.player_tag).attacks if attack.attacker.town_hall == th_level]                
            
            if self.clan_tag:
                attacks_for_th = [attack for war in self.war_log for attack in war.get_clan(self.clan_tag).attacks if attack.attacker.town_hall == th_level]

            async for attack in AsyncIter(attacks_for_th):
                hit_rate[attack.defender.town_hall]['attacker'] = th_level
                hit_rate[attack.defender.town_hall]['defender'] = attack.defender.town_hall
                hit_rate[attack.defender.town_hall]['total'] += 1
                hit_rate[attack.defender.town_hall]['stars'] += attack.stars
                hit_rate[attack.defender.town_hall]['destruction'] += attack.destruction
                hit_rate[attack.defender.town_hall]['triples'] += 1 if attack.is_triple else 0
            return hit_rate
        
        except:
            return hit_rate

    @property
    def average_duration_str(self):
        d,h,m,s = s_convert_seconds_to_str(self.average_attack_duration)
        ret_str = ""
        if d > 0:
            ret_str += f"{int(d)}d "
        if h > 0:
            ret_str += f"{int(h)}h "
        if m > 0:
            ret_str += f"{int(m)}m "
        if s > 0:
            ret_str += f"{int(s)}s "
        if ret_str == "":
            ret_str = "0s"
        return ret_str.strip()