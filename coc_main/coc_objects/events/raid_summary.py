import pendulum

from typing import *

from functools import cached_property
from .raid_weekend import aRaidWeekend

class aSummaryRaidStats():
    def __init__(self,raid_log:List[aRaidWeekend]):
        
        self.timestamp = pendulum.now()
        self.player_tag = None
        self.clan_tag = None
        self.raid_log = raid_log
        self.raids_participated = len(raid_log) if raid_log else 0
    
    @classmethod
    def for_player(cls,player_tag:str,raid_log:list[aRaidWeekend]):
        stats = cls(raid_log)
        stats.player_tag = player_tag
        return stats
    
    @cached_property
    def raid_attacks(self) -> int:
        try:
            if self.player_tag:
                return sum(
                    [raid.get_member(self.player_tag).attack_count
                    for raid in self.raid_log]
                    )
        except:
            return 0
    
    @cached_property
    def resources_looted(self) -> int:
        try:
            if self.player_tag:
                return sum(
                    [raid.get_member(self.player_tag).capital_resources_looted
                    for raid in self.raid_log]
                    )
        except:
            return 0
    
    @cached_property
    def medals_earned(self) -> int:
        try:
            if self.player_tag:
                return sum(
                    [raid.get_member(self.player_tag).medals_earned
                    for raid in self.raid_log]
                    )
        except:
            return 0
    
    @cached_property
    def unused_attacks(self) -> int:
        try:
            if self.player_tag:
                return (self.raids_participated * 6) - self.raid_attacks
        except:
            return 0