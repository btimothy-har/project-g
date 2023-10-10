from typing import *

from ...api_client import coc as coc
from ...api_client import BotClashClient as client
from ...utils.constants.coc_emojis import EmojisHeroes

bot_client = client()

class aHero():
    @classmethod
    def _not_yet_unlocked(cls,name:str,th_level:int):
        i = bot_client.coc.get_hero(name,level=1)
        hero = cls(i,th_level)
        hero._level = 0
        return hero
    
    def __init__(self,hero:coc.hero.Hero,th_level:int):
        self._game_hero = hero
        self._th_level = th_level
        self._level = None

    @property
    def emoji(self) -> str:
        return EmojisHeroes.get(self.name)
    
    @property
    def is_rushed(self) -> bool:
        return True if self.level < self.min_level else False
    
    ##################################################
    ### SLAVED PROPERTIES TO COC.HERO
    ##################################################
    @property
    def name(self) -> str:
        return self._game_hero.name    
    @property
    def range(self) -> int:
        return self._game_hero.range
    @property
    def dps(self) -> int:
        return self._game_hero.dps    
    @property
    def hitpoints(self) -> int:
        return self._game_hero.hitpoints    
    @property
    def ground_target(self) -> bool:
        return self._game_hero.ground_target
    @property
    def speed(self) -> int:
        return self._game_hero.speed    
    @property
    def upgrade_cost(self) -> int:
        return self._game_hero.upgrade_cost    
    @property
    def upgrade_resource(self) -> str:
        return self._game_hero.upgrade_resource    
    @property
    def upgrade_time(self) -> int:
        return self._game_hero.upgrade_time    
    @property
    def ability_time(self) -> int:
        return self._game_hero.ability_time    
    @property
    def required_th_level(self) -> int:
        return self._game_hero.required_th_level    
    @property
    def regeneration_time(self) -> str:
        return self._game_hero.regeneration_time    
    @property
    def level(self) -> int:
        if isinstance(self._level,int):
            return self._level
        return self._game_hero.level    
    @property
    def max_level(self) -> int:
        try:
            m = self._game_hero.get_max_level_for_townhall(max(self._th_level,3))
        except:
            m = None
        return m if m else self._game_hero.max_level
    @property
    def min_level(self) -> int:
        try:
            m = self._game_hero.get_max_level_for_townhall(max(self._th_level-1,3))
        except:
            m = None
        return m if m else 0
    @property
    def village(self) -> str:
        return self._game_hero.village