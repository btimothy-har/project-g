from typing import *

from ...api_client import coc as coc
from ...api_client import BotClashClient as client

from ...utils.constants.coc_emojis import EmojisTroops

bot_client = client()

th_16_max_level = {
    'Barbarian': 12,
    'Archer': 12,
    'Giant': 12,
    'Wall Breaker': 12,
    'Balloon': 11,
    'Wizard': 12,
    'Healer': 9,
    'Dragon': 11,
    'P.E.K.K.A': 11,
    'Miner': 10,
    'Electro Dragon': 7,
    'Dragon Rider': 4,
    'Valkyrie': 11,
    'Golem': 13,
    'Witch': 7,
    'Root Rider': 3
    }

root_rider_max_level = {
    15: 2,
    16: 3
    }
root_rider_min_level = {
    16: 2
    }

class aTroop():
    @classmethod
    def _not_yet_unlocked(cls,name:str,th_level:int):
        if name == 'Root Rider':
            i = bot_client.coc.get_troop('Barbarian',level=1)
            i.name = 'Root Rider'
        else:
            i = bot_client.coc.get_troop(name,level=1)
        troop = cls(i,th_level)
        troop._level = 0
        return troop
    
    def __init__(self,troop:coc.troop.Troop,th_level:int):
        self._game_troop = troop
        self._th_level = th_level
        self._level = None

    @property
    def emoji(self) -> str:
        return EmojisTroops.get(self.name)
    
    @property
    def is_rushed(self) -> bool:
        if not self.is_super_troop:
            return True if self.level < self.min_level else False
        return False
    
    ##################################################
    ### SLAVED PROPERTIES TO COC.HERO
    ##################################################
    @property
    def name(self) -> str:
        return self._game_troop.name    
    @property
    def range(self) -> int:
        if self.name == 'Root Rider':
            return 0
        return self._game_troop.range
    @property
    def lab_level(self) -> int:
        if self.name == 'Root Rider':
            return 13
        return self._game_troop.lab_level
    @property
    def dps(self) -> int:
        if self.name == 'Root Rider':
            return 0
        return self._game_troop.dps    
    @property
    def hitpoints(self) -> int:
        if self.name == 'Root Rider':
            return 0
        return self._game_troop.hitpoints    
    @property
    def ground_target(self) -> bool:
        if self.name == 'Root Rider':
            return True
        return self._game_troop.ground_target
    @property
    def speed(self) -> int:
        if self.name == 'Root Rider':
            return 0
        return self._game_troop.speed    
    @property
    def upgrade_cost(self) -> int:
        if self.name == 'Root Rider':
            return 0
        return self._game_troop.upgrade_cost
    @property
    def upgrade_resource(self) -> coc.Resource:
        if self.name == 'Root Rider':
            return coc.Resource.elixir
        return self._game_troop.upgrade_resource    
    @property
    def upgrade_time(self) -> coc.TimeDelta:
        if self.name == 'Root Rider':
            return coc.TimeDelta(seconds=0)
        return self._game_troop.upgrade_time
    @property
    def training_time(self) -> coc.TimeDelta:
        if self.name == 'Root Rider':
            return coc.TimeDelta(seconds=0)
        return self._game_troop.training_time
    @property
    def is_elixir_troop(self) -> bool:
        if self.name == 'Root Rider':
            return True
        return self._game_troop.is_elixir_troop
    @property
    def is_dark_troop(self) -> bool:
        if self.name == 'Root Rider':
            return False
        return self._game_troop.is_dark_troop
    @property
    def is_siege_machine(self) -> bool:
        if self.name == 'Root Rider':
            return False
        return self._game_troop.is_siege_machine
    @property
    def is_super_troop(self) -> bool:
        if self.name == 'Root Rider':
            return False
        return self._game_troop.is_super_troop
    @property
    def cooldown(self) -> coc.TimeDelta:
        if self.name == 'Root Rider':
            return coc.TimeDelta(seconds=0)
        return self._game_troop.cooldown
    @property
    def duration(self) -> coc.TimeDelta:
        if self.name == 'Root Rider':
            return coc.TimeDelta(seconds=0)
        return self._game_troop.duration
    @property
    def min_original_level(self) -> int:
        if self.name == 'Root Rider':
            return 0
        return self._game_troop.min_original_level
    @property
    def original_troop(self) -> Optional['aTroop']:
        if self.name == 'Root Rider':
            return None
        return self._game_troop.original_troop
    @property
    def level(self) -> int:
        if isinstance(self._level,int):
            return self._level
        return self._game_troop.level    
    @property
    def max_level(self) -> int:
        if self.name == 'Root Rider':
            return root_rider_max_level.get(self._th_level,0)
        th = self._th_level
        if th == 16:
            if self.name in th_16_max_level:
                return th_16_max_level[self.name]
            else:
                th = 15
        
        try:
            m = self._game_troop.get_max_level_for_townhall(max(th,3))
        except:
            m = None
        return m if m else self._game_troop.max_level
    @property
    def min_level(self) -> int:
        if self.name == 'Root Rider':
            return root_rider_min_level.get(self._th_level,0)
        try:
            m = self._game_troop.get_max_level_for_townhall(max(self._th_level-1,3))
        except:
            m = None
        return m if m else 0
    @property
    def village(self) -> str:
        return self._game_troop.village