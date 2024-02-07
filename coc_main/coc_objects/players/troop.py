from typing import *

from ...api_client import coc as coc
from ...api_client import BotClashClient as client

from ...utils.constants.coc_emojis import EmojisTroops

bot_client = client()

class aTroop():
    @classmethod
    def _not_yet_unlocked(cls,name:str,th_level:int):
        i = bot_client.coc.get_troop(name,level=1)
        troop = cls(i,th_level)
        troop._level = 0
        return troop
    
    def __init__(self,troop:coc.troop.Troop,th_level:int):
        self._game_troop = troop
        self._th_level = th_level
        self._level = None

    def to_json(self) -> dict:
        return {
            'name': self.name,
            'level': self.level,
            'max_level': self.max_level,
            'min_level': self.min_level,
            'emoji': self.emoji,
            'is_rushed': self.is_rushed,
            'village': self.village,
            }

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
        return self._game_troop.range
    @property
    def lab_level(self) -> int:
        return self._game_troop.lab_level
    @property
    def dps(self) -> int:
        return self._game_troop.dps    
    @property
    def hitpoints(self) -> int:
        return self._game_troop.hitpoints    
    @property
    def ground_target(self) -> bool:
        return self._game_troop.ground_target
    @property
    def speed(self) -> int:
        return self._game_troop.speed    
    @property
    def upgrade_cost(self) -> int:
        return self._game_troop.upgrade_cost
    @property
    def upgrade_resource(self) -> coc.Resource:
        return self._game_troop.upgrade_resource    
    @property
    def upgrade_time(self) -> coc.TimeDelta:
        return self._game_troop.upgrade_time
    @property
    def training_time(self) -> coc.TimeDelta:
        return self._game_troop.training_time
    @property
    def is_elixir_troop(self) -> bool:
        return self._game_troop.is_elixir_troop
    @property
    def is_dark_troop(self) -> bool: 
        return self._game_troop.is_dark_troop
    @property
    def is_siege_machine(self) -> bool:
        return self._game_troop.is_siege_machine
    @property
    def is_super_troop(self) -> bool:
        return self._game_troop.is_super_troop
    @property
    def cooldown(self) -> coc.TimeDelta:
        return self._game_troop.cooldown
    @property
    def duration(self) -> coc.TimeDelta:
        return self._game_troop.duration
    @property
    def min_original_level(self) -> int:
        return self._game_troop.min_original_level
    @property
    def original_troop(self) -> Optional['aTroop']:
        return self._game_troop.original_troop
    @property
    def level(self) -> int:
        if isinstance(self._level,int):
            return self._level
        return self._game_troop.level    
    @property
    def max_level(self) -> int:
        th = self._th_level
        try:
            m = self._game_troop.get_max_level_for_townhall(max(th,3))
        except:
            m = None
        return m if m else self._game_troop.max_level
    @property
    def min_level(self) -> int:
        try:
            m = self._game_troop.get_max_level_for_townhall(max(self._th_level-1,3))
        except:
            m = None
        return m if m else 0
    @property
    def village(self) -> str:
        return self._game_troop.village
    @property
    def is_home_troop(self) -> bool:
        return self.village == 'home'