import pendulum

from typing import *
from mongoengine import *

from .raid_weekend import aRaidWeekend

from ...constants.coc_constants import *
from ...constants.coc_emojis import *
from ...exceptions import *

class aSummaryRaidStats():
    def __init__(self,player_tag:str,raid_log:list[aRaidWeekend]):
        
        self.timestamp = pendulum.now()
        self.raid_log = raid_log
        self.tag = player_tag
        self.raids_participated = 0
        self.raid_attacks = 0
        self.resources_looted = 0
        self.medals_earned = 0
        self.unused_attacks = 0
    
    @classmethod
    def for_player(cls,player_tag:str,raid_log:list[aRaidWeekend]):
        def predicate_raid(raid):
            return raid.is_alliance_raid and raid.get_member(player_tag)

        stats = cls(player_tag,raid_log)

        stats.raids_participated = len(
            [raid for raid in raid_log if predicate_raid(raid)]
            )
        stats.raid_attacks = sum(
            [raid.get_member(player_tag).attack_count
            for raid in raid_log if predicate_raid(raid)]
            )
        stats.resources_looted = sum(
            [raid.get_member(player_tag).capital_resources_looted
            for raid in raid_log if predicate_raid(raid)]
            )
        stats.medals_earned = sum(
            [raid.get_member(player_tag).medals_earned
            for raid in raid_log if predicate_raid(raid)]
            )
        stats.unused_attacks = (stats.raids_participated * 6) - stats.raid_attacks        
        return stats