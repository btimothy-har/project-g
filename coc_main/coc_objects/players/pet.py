from typing import *

from ...api_client import coc as coc
from ...api_client import BotClashClient as client

from ...utils.constants.coc_emojis import EmojisPets

bot_client = client()

class aPet():
    @classmethod
    def _not_yet_unlocked(cls,name:str,th_level:int) -> 'aPet':
        if name == 'Spirit Fox':
            i = bot_client.coc.get_pet('L.A.S.S.I',level=1)
            i.name = 'Spirit Fox'
        else:
            i = bot_client.coc.get_pet(name,level=1)
        pet = cls(i,th_level)
        pet._level = 0
        return pet
    
    def __init__(self,pet:coc.Pet,th_level:int):
        self._game_pet = pet
        self._th_level = th_level
        self._level = None

    @property
    def emoji(self) -> str:
        return EmojisPets.get(self.name)
    
    @property
    def is_rushed(self) -> bool:
        return True if self.level < self.min_level else False
    
    ##################################################
    ### SLAVED PROPERTIES TO COC.HERO
    ##################################################
    @property
    def name(self) -> str:
        return self._game_pet.name    
    @property
    def range(self) -> int:
        if self.name == 'Spirit Fox':
            return 0
        return self._game_pet.range
    @property
    def dps(self) -> int:
        if self.name == 'Spirit Fox':
            return 0
        return self._game_pet.dps
    @property
    def ground_target(self) -> bool:
        if self.name == 'Spirit Fox':
            return False
        return self._game_pet.ground_target
    @property
    def hitpoints(self) -> int:
        if self.name == 'Spirit Fox':
            return 0
        return self._game_pet.hitpoints
    @property
    def speed(self) -> int:
        if self.name == 'Spirit Fox':
            return 0
        return self._game_pet.speed
    @property
    def upgrade_cost(self) -> int:
        if self.name == 'Spirit Fox':
            return 0
        return self._game_pet.upgrade_cost
    @property
    def upgrade_resource(self) -> coc.Resource:
        if self.name == 'Spirit Fox':
            return 0
        return self._game_pet.upgrade_resource    
    @property
    def upgrade_time(self) -> coc.TimeDelta:
        if self.name == 'Spirit Fox':
            return 0
        return self._game_pet.upgrade_time
    @property
    def level(self) -> int:
        if isinstance(self._level,int):
            return self._level
        return self._game_pet.level    
    @property
    def max_level(self) -> int:
        th = self._th_level
        if th == 16:
            if self.name == 'Spirit Fox':
                return 10
            else:
                th = 15
        try:
            m = self._game_pet.get_max_level_for_townhall(max(th,3))
        except:
            m = None
        return m if m else self._game_pet.max_level
    @property
    def min_level(self) -> int:
        th = self._th_level
        if th == 16:
            if self.name == 'Spirit Fox':
                return 0
        try:
            m = self._game_pet.get_max_level_for_townhall(max(th-1,3))
        except:
            m = None
        return m if m else 0
    @property
    def village(self) -> str:
        if self.name == 'Spirit Fox':
            return 'Home'
        return self._game_pet.village
    @property
    def required_th_level(self) -> int:
        if self.name == 'Spirit Fox':
            return 16
        return self._game_pet.required_th_level