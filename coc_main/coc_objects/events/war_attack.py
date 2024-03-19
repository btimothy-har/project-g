import coc
import logging

from typing import *

from ...utils.constants.coc_constants import ClanWarType

LOG = logging.getLogger("coc.main")

class bWarAttack(coc.WarAttack):    
    def __init__(self,**kwargs):
        self._new_stars = None
        self._new_destruction = None

        coc.WarAttack.__init__(self,**kwargs)

    @property
    def is_triple(self) -> bool:
        if self.war.type == 'cwl':
            return self.stars == 3
        return self.stars==3 and self.attacker.town_hall <= self.defender.town_hall    
    @property
    def is_best_attack(self) -> bool:
        if len(self.defender.defenses) == 0:
            return False
        return self.defender.best_opponent_attack.order == self.order    
    @property
    def new_stars(self) -> int:
        if self._new_stars is None:
            self.compute_attack_stats()
        return self._new_stars    
    @property
    def new_destruction(self) -> float:
        if self._new_destruction is None:
            self.compute_attack_stats()
        return self._new_destruction
    
    def compute_attack_stats(self):
        prior_attacks = [att for att in self.defender.defenses if att.order < self.order]

        if len(prior_attacks) == 0:
            self._new_stars = self.stars
            self._new_destruction = self.destruction
            return

        prior_stars = max([att.stars for att in prior_attacks])
        prior_destruction = max([att.destruction for att in prior_attacks])
        
        self._new_stars = max(0,self.stars - prior_stars)
        self._new_destruction = max(0,self.destruction - prior_destruction)
    
    @property
    def elo_effect(self) -> int:
        eff = 0
        if self.war.type == ClanWarType.CWL:
            if self.stars >= 1:
                eff += 1
            if self.stars >= 2:
                eff += 1
            if self.stars >= 3:
                eff += 2
            eff += (self.defender.town_hall - self.attacker.town_hall)
        
        if self.war.type == ClanWarType.RANDOM:
            if self.defender.town_hall == self.attacker.town_hall:
                eff -= 1
                if self.stars >= 1:
                    eff += 0.25
                if self.stars >= 2:
                    eff += 0.5
                if self.stars >= 3:
                    eff += 0.75
        return eff

    def _api_json(self):
        return {
            'attackerTag': self.attacker_tag,
            'defenderTag': self.defender_tag,
            'stars': self.stars,
            'destructionPercentage': self.destruction,
            'order': self.order,
            'duration': self.duration,
            }