import coc

from coc_client.api_client import BotClashClient

from ...constants.coc_constants import *
from ...constants.coc_emojis import *
from ...constants.ui_emojis import *
from ...exceptions import *

bot_client = BotClashClient()

class aSpell():

    @classmethod
    def _not_yet_unlocked(cls,name:str,th_level:int):
        i = bot_client.coc.get_spell(name,level=1)
        spell = cls(i,th_level)
        spell._level = 0
        return spell
    
    def __init__(self,spell:coc.spell.Spell,th_level:int):
        self._game_spell = spell
        self._th_level = th_level
        self._level = None

    @property
    def emoji(self) -> str:
        return EmojisSpells.get(self.name)
    
    @property
    def is_rushed(self) -> bool:
        return True if self.level < self.min_level else False
    
    ##################################################
    ### SLAVED PROPERTIES TO COC.HERO
    ##################################################
    @property
    def name(self) -> str:
        return self._game_spell.name    
    @property
    def range(self) -> int:
        return self._game_spell.range
    @property
    def upgrade_cost(self) -> int:
        return self._game_spell.upgrade_cost
    @property
    def upgrade_resource(self) -> coc.Resource:
        return self._game_spell.upgrade_resource    
    @property
    def upgrade_time(self) -> coc.TimeDelta:
        return self._game_spell.upgrade_time
    @property
    def training_time(self) -> coc.TimeDelta:
        return self._game_spell.training_time
    @property
    def is_elixir_spell(self) -> bool:
        return self._game_spell.is_elixir_spell
    @property
    def is_dark_spell(self) -> bool:
        return self._game_spell.is_dark_spell
    @property
    def level(self) -> int:
        return self._game_spell.level    
    @property
    def max_level(self) -> int:
        try:
            m = self._game_spell.get_max_level_for_townhall(max(self._th_level,3))
        except:
            m = None
        return m if m else self._game_spell.max_level
    @property
    def min_level(self) -> int:
        try:
            m = self._game_spell.get_max_level_for_townhall(max(self._th_level-1,3))
        except:
            m = None
        return m if m else 0
    @property
    def village(self) -> str:
        return self._game_spell.village