import coc
import asyncio
import pendulum

from typing import *

from functools import cached_property
from async_property import AwaitLoader

from .base_player import BasicPlayer
from .player_season import aPlayerSeason

from .townhall import aTownHall
from .hero import aHero
from .troop import aTroop
from .spell import aSpell
from .pet import aPet

from ..season.season import aClashSeason
from ..clans.clan import _PlayerClan

from ...utils.constants.coc_constants import HeroAvailability, TroopAvailability, SpellAvailability, PetAvailability
from ...utils.constants.coc_emojis import EmojisClash, EmojisHeroes, EmojisLeagues

##################################################
#####
##### PLAYER
#####
##################################################
class aPlayer(coc.Player,BasicPlayer,AwaitLoader):
    def __init__(self,**kwargs):

        self._name = None
        self._exp_level = None
        self._town_hall_level = None
        self.clan_cls = _PlayerClan
        
        coc.Player.__init__(self,**kwargs)
        BasicPlayer.__init__(self,self.tag)

        self.timestamp = pendulum.now()        

        self._heroes = super().heroes
        self._heroes_cached = False

        self._troops = super().troops
        self._troops_cached = False

        self._spells = super().spells
        self._spells_cached = False

        self._pets = super().pets
        self._pets_cached = False
    
    def __str__(self):
        return f"{self.name} ({self.tag})"
    
    def __eq__(self,other):
        return isinstance(other,aPlayer) and self.tag == other.tag
    
    def __hash__(self):
        return hash(self.tag)
    
    def name_json(self) -> dict:
        return {
            'tag': self.tag,
            'name': self.name,
            'share_link': self.share_link,
            'town_hall': self.town_hall_level,
            }
    
    def profile_json(self) -> dict:
        return {
            'tag': self.tag,
            'name': self.name,
            'is_alliance_member': self.is_member,
            'alliance_clan': self.home_clan.to_json() if self.home_clan else None,
            'clan': self.clan.to_json() if self.clan else None,
            'town_hall': self.town_hall_level
            }
    
    def hero_json(self) -> dict:
        return {
            'tag': self.tag,
            'name': self.name,            
            'heroes': [hero.to_json() for hero in self.heroes]
            }

    async def load(self):
        if self.clan and isinstance(self.clan,AwaitLoader):
            await self.clan
        await BasicPlayer.load(self)
    
    @property
    def name(self) -> str:
        return self._name
    @name.setter
    def name(self,value:str):
        self._name = value
    
    @property
    def exp_level(self) -> int:
        return self._exp_level
    @exp_level.setter
    def exp_level(self,value:int):
        self._exp_level = value
    
    @property
    def town_hall_level(self) -> int:
        return self._town_hall_level
    
    @property
    def label_ids(self) -> List[str]:
        return [label.id for label in self.labels]
    
    @property
    def town_hall(self) -> aTownHall:
        return aTownHall(level=self.town_hall_level,weapon=self.town_hall_weapon)
    @town_hall.setter
    def town_hall(self,value:int):
        self._town_hall_level = value
    
    @property
    def clan_tag(self) -> str:
        return getattr(self.clan,'tag',None)

    @property
    def heroes(self) -> List[aHero]:
        if not self._heroes_cached:
            hero_ph = []
            for hero_name in HeroAvailability.return_all_unlocked(self.town_hall.level):
                hero = self.get_hero(hero_name)
                if not hero:
                    hero = aHero._not_yet_unlocked(hero_name,self.town_hall.level)
                hero_ph.append(hero)
            self._heroes = hero_ph
            self._heroes_cached = True
        return self._heroes
    @heroes.setter
    def heroes(self,value:List[Union[coc.Hero,aHero]]):
        self._heroes = value
    
    @property
    def troops(self) -> List[aTroop]:
        if not self._troops_cached:
            troops_ph = []
            for troop_name in TroopAvailability.return_all_unlocked(self.town_hall.level):
                troop = self.get_troop(name=troop_name,is_home_troop=True)
                if not troop:
                    if troop_name not in coc.SUPER_TROOP_ORDER:
                        troop = aTroop._not_yet_unlocked(troop_name,self.town_hall.level)                    
                if troop:
                    troops_ph.append(troop)
            self._troops = troops_ph
            self._troops_cached = True
        return self._troops
    @troops.setter
    def troops(self,value:List[Union[coc.Troop,aTroop]]):
        self._troops = value

    @property
    def spells(self) -> List[aSpell]:
        if not self._spells_cached:
            spells_ph = []
            for spell_name in SpellAvailability.return_all_unlocked(self.town_hall.level):
                spell = self.get_spell(name=spell_name)
                if not spell:
                    spell = aSpell._not_yet_unlocked(spell_name,self.town_hall.level)
                if spell:
                    spells_ph.append(spell)
            self._spells = spells_ph
            self._spells_cached = True
        return self._spells
    @spells.setter
    def spells(self,value:List[Union[coc.Spell,aSpell]]):
        self._spells = value
    
    @property
    def pets(self) -> List[aPet]:
        if not self._pets_cached:
            pets_ph = []
            for pet_name in PetAvailability.return_all_unlocked(self.town_hall.level):
                pet = self.get_pet(name=pet_name)
                if pet:
                    pet = aPet(pet,self.town_hall.level)
                else:
                    pet = aPet._not_yet_unlocked(pet_name,self.town_hall.level)
                pets_ph.append(pet)
            self._pets = pets_ph
            self._pets_cached = True
        return self._pets
    @pets.setter
    def pets(self,value:List[Union[coc.Pet,aPet]]):
        self._pets = value
    
    @cached_property
    def league_icon(self):
        return self.league.icon.medium if self.league.name != "Unranked" else None
    
    @cached_property
    def war_opt_status(self):
        return 'IN' if self.war_opted_in else 'OUT'
    
    @cached_property
    def elixir_troops(self):
        return [troop for troop in self.troops if troop.is_elixir_troop and not troop.is_super_troop]
    
    @cached_property
    def darkelixir_troops(self):
        return [troop for troop in self.troops if troop.is_dark_troop and not troop.is_super_troop]
    
    @cached_property
    def siege_machines(self):
        return [troop for troop in self.troops if troop.is_siege_machine and not troop.is_super_troop]
    
    @cached_property
    def elixir_spells(self):
        return [spell for spell in self.spells if spell.is_elixir_spell]
    
    @cached_property
    def darkelixir_spells(self):
        return [spell for spell in self.spells if spell.is_dark_spell]
    
    @cached_property
    def super_troops(self):
        return [troop for troop in self.troops if troop.is_super_troop] 
    
    @cached_property
    def hero_strength(self) -> int:
        return sum([hero.level for hero in self.heroes])
    @cached_property
    def max_hero_strength(self) -> int:
        return sum([hero.max_level for hero in self.heroes])    
    @cached_property
    def min_hero_strength(self) -> int:
        return sum([hero.min_level for hero in self.heroes])
    @cached_property
    def hero_strength_pct(self) -> float:
        try:
            return round((self.hero_strength / self.max_hero_strength)*100,2)
        except ZeroDivisionError:
            return 0
    @cached_property
    def hero_rushed_pct(self) -> float:
        try:
            rushed_levels = sum([(h.min_level - h.level) for h in self.heroes if h.is_rushed])
            return round((rushed_levels / self.min_hero_strength)*100,2)
        except ZeroDivisionError:
            return 0
    
    @cached_property
    def barbarian_king(self) -> aHero:
        return next((hero for hero in self.heroes if hero.name == 'Barbarian King'),None)    
    @cached_property
    def archer_queen(self) -> aHero:
        return next((hero for hero in self.heroes if hero.name == 'Archer Queen'),None)
    @cached_property
    def grand_warden(self) -> aHero:
        return next((hero for hero in self.heroes if hero.name == 'Grand Warden'),None)    
    @cached_property
    def royal_champion(self) -> aHero:
        return next((hero for hero in self.heroes if hero.name == 'Royal Champion'),None)
    
    @cached_property
    def troop_strength(self) -> int:
        strg = sum([troop.level for troop in self.troops if not troop.is_super_troop])
        if len(self.pets) > 0:
            strg += sum([pet.level for pet in self.pets])
        return strg
    @cached_property
    def max_troop_strength(self) -> int:
        strg = sum([troop.max_level for troop in self.troops if not troop.is_super_troop])
        if len(self.pets) > 0:
            strg += sum([pet.max_level for pet in self.pets])
        return strg
    @cached_property
    def min_troop_strength(self) -> int:
        strg = sum([troop.min_level for troop in self.troops if not troop.is_super_troop])
        if len(self.pets) > 0:
            strg += sum([pet.min_level for pet in self.pets])
        return strg
    @cached_property
    def troop_strength_pct(self) -> float:
        try:
            return round((self.troop_strength / self.max_troop_strength)*100,2)
        except ZeroDivisionError:
            return 0
    @cached_property
    def troop_rushed_pct(self) -> float:
        try:
            rushed_troops = sum([(t.min_level - t.level) for t in self.troops if t.is_rushed and not t.is_super_troop]) + sum([(p.min_level - p.level) for p in self.pets if p.is_rushed])
            return round((rushed_troops / self.min_troop_strength)*100,2)
        except ZeroDivisionError:
            return 0
    
    @cached_property
    def spell_strength(self) -> int:
        return sum([spell.level for spell in self.spells])
    @cached_property
    def max_spell_strength(self) -> int:
        return sum([spell.max_level for spell in self.spells])
    @cached_property
    def min_spell_strength(self) -> int:
        return sum([spell.min_level for spell in self.spells])
    @cached_property
    def spell_strength_pct(self) -> float:
        try:
            return round((self.spell_strength / self.max_spell_strength)*100,2)
        except ZeroDivisionError:
            return 0
    @cached_property
    def spell_rushed_pct(self) -> float:
        try:
            rushed_spells = sum([(s.min_level - s.level) for s in self.spells if s.is_rushed])
            return round((rushed_spells / self.min_spell_strength)*100,2)
        except ZeroDivisionError:
            return 0
    
    @cached_property
    def overall_rushed_pct(self) -> float:
        rushed_levels = 0
        min_levels = 0
        if self.min_troop_strength > 0:
            rushed_levels += sum([(t.min_level - t.level) for t in self.troops if t.is_rushed and not t.is_super_troop]) + sum([(p.min_level - p.level) for p in self.pets if p.is_rushed])
            min_levels += self.min_troop_strength
        if self.min_hero_strength > 0:
            rushed_levels += sum([(h.min_level - h.level) for h in self.heroes if h.is_rushed])
            min_levels += self.min_hero_strength
        if self.min_spell_strength > 0:
            rushed_levels += sum([(s.min_level - s.level) for s in self.spells if s.is_rushed])
            min_levels += self.min_spell_strength
        try:
            return round((rushed_levels / min_levels)*100,2)
        except ZeroDivisionError:
            return 0
    
    @cached_property
    def loot_gold(self) -> int:
        achievement = self.get_achievement('Gold Grab')
        return achievement.value if achievement else 0
    @cached_property
    def loot_elixir(self) -> int:
        achievement = self.get_achievement('Elixir Escapade')
        return achievement.value if achievement else 0
    @cached_property
    def loot_darkelixir(self) -> int:
        achievement = self.get_achievement('Heroic Heist')
        return achievement.value if achievement else 0
    @cached_property
    def clan_games(self) -> int:
        achievement = self.get_achievement('Games Champion')
        return achievement.value if achievement else 0
    @cached_property
    def capital_gold_looted(self) -> int:
        achievement = self.get_achievement('Aggressive Capitalism')
        return achievement.value if achievement else 0    
    
    ##################################################
    ### DATA FORMATTERS
    ##################################################
    @property
    def short_description(self):
        return f"{self.town_hall.emote} {self.town_hall.description}\u3000{self.member_description}"
    
    @property
    def long_description(self):
        d = f"{EmojisClash.EXP} {self.exp_level}\u3000{EmojisClash.CLAN} {self.clan_description}"
        d += f"\n{self.town_hall.emote} {self.town_hall.description}\u3000{EmojisLeagues.get(self.league.name)} {self.trophies} (best: {self.best_trophies})"
        if self.town_hall.level >= 7:
            d += f"\n{self.hero_description}"
        d += f"\n[Open In-Game: {self.tag}]({self.share_link})"
        return d
    
    @property
    def clan_description(self):
        return f"{str(self.role)} of {self.clan.name}" if self.clan else "No Clan"
    
    @property
    def hero_description(self):
        d = ""
        if self.town_hall.level >= 7:
            d += f"{EmojisHeroes.get('Barbarian King')} {sum([h.level for h in self.heroes if h.name=='Barbarian King'])}"
        if self.town_hall.level >= 9:
            d += f"\u3000{EmojisHeroes.get('Archer Queen')} {sum([h.level for h in self.heroes if h.name=='Archer Queen'])}"
        if self.town_hall.level >= 11:
            d += f"\u3000{EmojisHeroes.get('Grand Warden')} {sum([h.level for h in self.heroes if h.name=='Grand Warden'])}"
        if self.town_hall.level >= 13:
            d += f"\u3000{EmojisHeroes.get('Royal Champion')} {sum([h.level for h in self.heroes if h.name=='Royal Champion'])}"
        return d
    
    @property
    def hero_description_no_emoji(self):
        d = ""
        if self.town_hall.level >= 7:
            d += f"BK {sum([h.level for h in self.heroes if h.name=='Barbarian King'])}"
        if self.town_hall.level >= 9:
            d += f"\u3000AQ {sum([h.level for h in self.heroes if h.name=='Archer Queen'])}"
        if self.town_hall.level >= 11:
            d += f"\u3000GW {sum([h.level for h in self.heroes if h.name=='Grand Warden'])}"
        if self.town_hall.level >= 13:
            d += f"\u3000RC {sum([h.level for h in self.heroes if h.name=='Royal Champion'])}"
        return d    
    
    @property
    def member_description(self):
        if self.is_member:
            return f"{self.home_clan.emoji} {self.alliance_rank} of {self.home_clan.name}"
        else:
            return f"{EmojisClash.CLAN} " + f"{str(self.role)} of {self.clan.name}" if self.clan else "No Clan"
        
    @property
    def member_description_no_emoji(self):
        if self.is_member:
            return f"{self.alliance_rank} of {self.home_clan.name}"
        else:
            return f"{str(self.role)} of {self.clan.name}" if self.clan else "No Clan"       
         
    ##################################################
    ### PLAYER SEASON STATS
    ##################################################
    async def get_current_season(self) -> aPlayerSeason:
        season = aClashSeason.current()
        return await self.get_season_stats(season)
    
    async def get_season_stats(self,season:aClashSeason) -> aPlayerSeason:
        stats = aPlayerSeason(self.tag,season)
        await stats.load()
        if season.is_current_season:
            stats.name = self.name
            stats.town_hall = self.town_hall.level      
            stats.home_clan_tag = getattr(self.home_clan,'tag',None)
            stats.home_clan = self.home_clan
            stats.is_member = self.is_member      
        return stats

    def get_hero(self,hero_name:str) -> aHero:
        hero = next((hero for hero in self._heroes if hero.name == hero_name),None)
        return aHero(hero,self.town_hall.level) if hero else None
    
    def get_troop(self,name:str,is_home_troop:bool=True) -> aTroop:
        if is_home_troop:
            troop = next((troop for troop in self._troops if troop.name == name and troop.village == 'home'),None)
        else:
            troop = next((troop for troop in self._troops if troop.name == name),None)
        return aTroop(troop,self.town_hall.level) if troop else None
    
    def get_spell(self,name:str) -> aSpell:
        spell = next((spell for spell in self._spells if spell.name == name),None)
        return aSpell(spell,self.town_hall.level) if spell else None
    
    def get_pet(self,name:str) -> aPet:
        pet = next((pet for pet in self._pets if pet.name == name),None)
        return aPet(pet,self.town_hall.level) if pet else None
    
    async def _update_snapshots(self):
        current_season = await self.get_current_season()
        await current_season.save_member_snapshot()

        seasons = aClashSeason.all_seasons()
        snapshot_tasks = [aPlayerSeason.create_stats_snapshot(self.tag,season) for season in seasons]
        await asyncio.gather(*snapshot_tasks)

    @classmethod
    async def _sync_cache(cls,player:'aPlayer',force:bool=False):
        basic_player = await BasicPlayer(player.tag)
        await basic_player._attributes.load_data()

        if not force:
            if basic_player._attributes._last_sync and pendulum.now().int_timestamp - basic_player._attributes._last_sync.int_timestamp <= 3600:
                return
        
        async with basic_player._attributes._sync_lock:
            if basic_player._attributes._last_sync and basic_player._attributes._last_sync.int_timestamp >= player.timestamp.int_timestamp:
                return
            
            await basic_player._attributes.update_last_sync(player.timestamp)

            if basic_player.is_new:
                await BasicPlayer.player_first_seen(player.tag)
            
            tasks = []

            if basic_player.name != player.name:
                tasks.append(basic_player.set_name(player.name))

            if basic_player.exp_level != player.exp_level:
                tasks.append(basic_player.set_exp_level(player.exp_level))

            if basic_player.town_hall_level != player.town_hall_level:
                tasks.append(basic_player.set_town_hall_level(player.town_hall_level))
            
            if tasks:
                await asyncio.gather(*tasks)