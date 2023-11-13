import coc
import pendulum

from typing import *

from functools import cached_property

from ...api_client import BotClashClient as client

from .townhall import aTownHall
from .hero import aHero
from .troop import aTroop
from .spell import aSpell
from .pet import aPet

from .base_player import BasicPlayer, db_Player
from .player_season import aPlayerSeason, db_PlayerStats

from ..season.season import aClashSeason
from ..clans.player_clan import aPlayerClan
from ..events.clan_war_leagues import WarLeaguePlayer

from ...utils.constants.coc_constants import HeroAvailability, TroopAvailability, SpellAvailability, PetAvailability
from ...utils.constants.coc_constants import EmojisHeroes, EmojisLeagues

bot_client = client()

##################################################
#####
##### DATABASE
#####
##################################################
class aPlayer(coc.Player,BasicPlayer):
    def __init__(self,**kwargs):

        self._name = None
        self._exp_level = None
        self._town_hall_level = None
        
        coc.Player.__init__(self,**kwargs)
        BasicPlayer.__init__(self,self.tag)

        self.timestamp = pendulum.now()

        self.town_hall_level = self.town_hall
        self.label_ids = [label.id for label in self.labels]

        self.town_hall = aTownHall(level=self.town_hall_level,weapon=self.town_hall_weapon)
        self.clan_castle = sum([a.value for a in self.achievements if a.name=='Empire Builder'])
        self.clan_tag = getattr(self.clan,'tag',None)

        if self.clan:
            clan_ph = aPlayerClan(
                tag=getattr(self.clan,'tag',None),
                name=self.clan.name,
                badge=self.clan.badge,
                level=self.clan.level
                )
        else:
            clan_ph = None
        self.clan = clan_ph

        hero_ph = []
        for hero_name in HeroAvailability.return_all_unlocked(self.town_hall.level):
            hero = self.get_hero(hero_name)
            if hero:
                hero = aHero(hero,self.town_hall.level)
            else:
                hero = aHero._not_yet_unlocked(hero_name,self.town_hall.level)
            hero_ph.append(hero)
        self.heroes = hero_ph

        troops_ph = []
        for troop_name in TroopAvailability.return_all_unlocked(self.town_hall.level):
            troop = self.get_troop(name=troop_name,is_home_troop=True)
            if troop:
                troop = aTroop(troop,self.town_hall.level)
            else:
                if troop_name not in coc.SUPER_TROOP_ORDER:
                    troop = aTroop._not_yet_unlocked(troop_name,self.town_hall.level)
            if troop:
                troops_ph.append(troop)
        self.troops = troops_ph

        spells_ph = []
        for spell_name in SpellAvailability.return_all_unlocked(self.town_hall.level):
            spell = self.get_spell(name=spell_name)
            if spell:
                spell = aSpell(spell,self.town_hall.level)
            else:
                spell = aSpell._not_yet_unlocked(spell_name,self.town_hall.level)
            spells_ph.append(spell)
        self.spells = spells_ph

        pets_ph = []
        for pet_name in PetAvailability.return_all_unlocked(self.town_hall.level):
            pet = self.get_pet(name=pet_name)
            if pet:
                pet = aPet(pet,self.town_hall.level)
            else:
                pet = aPet._not_yet_unlocked(pet_name,self.town_hall.level)
            pets_ph.append(pet)
        self.pets = pets_ph
    
    def __str__(self):
        return f"{self.name} ({self.tag})"
    
    def __eq__(self,other):
        return isinstance(other,aPlayer) and self.tag == other.tag
    
    def __hash__(self):
        return hash(self.tag)
    
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
    @town_hall_level.setter
    def town_hall_level(self,value:int):
        self._town_hall_level = value
    
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
        return sum([troop.level for troop in self.troops if not troop.is_super_troop]) + sum([pet.level for pet in self.pets])
    @cached_property
    def max_troop_strength(self) -> int:
        return (sum([troop.max_level for troop in self.troops if not troop.is_super_troop]) + sum([pet.max_level for pet in self.pets]))
    @cached_property
    def min_troop_strength(self) -> int:
        return (sum([troop.min_level for troop in self.troops if not troop.is_super_troop]) + sum([pet.min_level for pet in self.pets]))
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
    
    ##################################################
    ### DATA FORMATTERS
    ##################################################
    @property
    def short_description(self):
        return f"{self.town_hall.emote} {self.town_hall.description}\u3000{self.member_description}"
    
    @property
    def long_description(self):
        d = f"<:Exp:825654249475932170> {self.exp_level}\u3000<:Clan:825654825509322752> {self.clan_description}"
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
            return f"<:Clan:825654825509322752> " + f"{str(self.role)} of {self.clan.name}" if self.clan.tag else "No Clan"
        
    @property
    def member_description_no_emoji(self):
        if self.is_member:
            return f"{self.alliance_rank} of {self.home_clan.name}"
        else:
            return f"{str(self.role)} of {self.clan.name}" if self.clan.tag else "No Clan"       
         
    ##################################################
    ### PLAYER SEASON STATS
    ##################################################    
    async def _sync_cache(self):
        if BasicPlayer(self.tag).is_new:
            await BasicPlayer.player_first_seen(self.tag)

        if BasicPlayer(self.tag).name != self.name:
            await self.set_name(self.name)
        if BasicPlayer(self.tag).exp_level != self.exp_level:
            await self.set_exp_level(self.exp_level)
        if BasicPlayer(self.tag).town_hall_level != self.town_hall_level:
            await self.set_town_hall_level(self.town_hall_level)
        
        if self.name != self.current_season.name:
            await self.current_season.update_name(self.name)
        if self.town_hall_level != self.current_season.town_hall:
            await self.current_season.update_townhall(self.town_hall_level)
        if getattr(self.home_clan,'tag',None) != getattr(self.current_season.home_clan,'tag',None):
            await self.current_season.update_home_clan(getattr(self.home_clan,'tag',None))
        if self.is_member != self.current_season.is_member:
            await self.current_season.update_member(self.is_member)

    @property
    def current_season(self):
        return aPlayerSeason(self.tag,bot_client.current_season)
    
    @property
    def season_data(self):
        return {season.id:aPlayerSeason(self.tag,season) for season in bot_client.tracked_seasons}
    
    def get_season_stats(self,season:aClashSeason):
        return aPlayerSeason(self.tag,season)
            
    def war_league_season(self,season:aClashSeason) -> WarLeaguePlayer:
        return WarLeaguePlayer(self.tag,season)

    def get_hero(self,hero_name:str):
        return next((hero for hero in self.heroes if hero.name == hero_name),None)
    
    def get_troop(self,name:str,is_home_troop:bool=False):
        if is_home_troop:
            return next((troop for troop in self.troops if troop.name == name),None)
        else:
            return next((troop for troop in self.troops if troop.name == name and not troop.village == 'home'),None)
    
    def get_spell(self,name:str):
        return next((spell for spell in self.spells if spell.name == name),None)
    
    def get_pet(self,name:str):
        return next((pet for pet in self.pets if pet.name == name),None)
    
    # @property
    # def notes(self):
    #     try:
    #         self._notes = dPlayer.objects.get(tag=self.tag).notes
    #     except DoesNotExist:
    #         self._notes = []
    #     return self._notes
    # @notes.setter
    # def notes(self,new_note):
    #     self._notes.append(new_note)
    #     try:
    #         player_data = dPlayer.objects.get(tag=self.tag)
    #     except DoesNotExist:
    #         player_data = dPlayer(tag=self.tag)
    #     player_data.notes=list(set(self._notes))
    #     player_data.save()

    # def add_note(self,ctx,message):
    #         new_note = await aNote.new_note(ctx,message)
    #         new_note_id = new_note.save_note_to_db()
    #         self.notes.append(new_note_id)
    #         self.save_player_to_db()
