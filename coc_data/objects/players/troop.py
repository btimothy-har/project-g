import coc

from coc_client.api_client import BotClashClient

from ...constants.coc_constants import *
from ...constants.coc_emojis import *
from ...constants.ui_emojis import *
from ...exceptions import *

bot_client = BotClashClient()

class aTroop():

    @classmethod
    def _not_yet_unlocked(cls,name:str,th_level:int):
        i = bot_client.coc.get_troop(name,level=1)
        spell = cls(i,th_level)
        spell._level = 0
        return spell
    
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
        return self._game_troop.level    
    @property
    def max_level(self) -> int:
        try:
            m = self._game_troop.get_max_level_for_townhall(max(self._th_level,3))
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