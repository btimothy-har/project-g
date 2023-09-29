import coc
import pendulum
import random
import asyncio

from typing import *

from functools import cached_property
from mongoengine import *
from redbot.core.utils import AsyncIter

from coc_client.api_client import BotClashClient

from .player_season import aPlayerSeason

from ..season.season import aClashSeason
from ..clans.clan import aClan
from ..events.clan_war_leagues import WarLeaguePlayer

from ...constants.coc_constants import *
from ...constants.coc_emojis import *
from ...constants.ui_emojis import *
from ...exceptions import *

##################################################
#####
##### DATABASE
#####
##################################################
class db_Player(Document):
    tag = StringField(primary_key=True,required=True)
    name = StringField(default="",required=True)
    discord_user = IntField(default=0)
    is_member = BooleanField(default=False)
    home_clan = StringField(default="")
    first_seen = IntField(default=0)
    last_joined = IntField(default=0)
    last_removed = IntField(default=0)

class aPlayer(coc.Player):
    def __init__(self,**kwargs):
        self.bot = kwargs.get('bot',None)
        self.client = BotClashClient()
        self.timestamp = pendulum.now()

        super().__init__(**kwargs)
        self.town_hall = aTownHall(level=self.town_hall,weapon=self.town_hall_weapon)
        self.clan_castle = sum([a.value for a in self.achievements if a.name=='Empire Builder'])
        self.clan_tag = getattr(self.clan,'tag',None)

        hero_ph = []
        for hero_name in HeroAvailability.return_all_unlocked(self.town_hall.level):
            try:
                hero = self.get_hero(hero_name)
            except:
                hero = None
            if not hero:
                hero = self.bot.coc_client.get_hero(name=hero_name,townhall=self.town_hall.level)
            hero = aHero(hero,self.town_hall.level)
            hero_ph.append(hero)
        self.heroes = hero_ph

        troops_ph = []
        for troop_name in TroopAvailability.return_all_unlocked(self.town_hall.level):
            try:
                try:
                    troop = self.get_troop(name=troop_name,is_home_troop=True)
                except:
                    troop = None
                if troop_name == 'Apprentice Warden':
                    troop = aTroop.apprentice_warden(self.town_hall.level,troop)
                    troops_ph.append(troop)
                elif troop_name == 'Super Hog Rider':
                    if troop and troop.is_active:
                        troop = aTroop.super_hog_rider(self,self.town_hall.level,troop)
                        troops_ph.append(troop)
                else:
                    if not troop and troop_name not in coc.SUPER_TROOP_ORDER:
                        troop = self.bot.coc_client.get_troop(name=troop_name,is_home_village=True,townhall=self.town_hall.level)
                    if troop:
                        troop = aTroop(data=troop,townhall_level=self.town_hall.level)
                        troops_ph.append(troop)
            except:
                self.client.cog.coc_main_log.exception(f"Error getting troop {troop_name} for {self.name}")
        self.troops = troops_ph

        spells_ph = []
        for spell_name in SpellAvailability.return_all_unlocked(self.town_hall.level):
            try:
                spell = self.get_spell(name=spell_name)
            except:
                spell = None
            if not spell:
                spell = self.bot.coc_client.get_spell(name=spell_name,townhall=self.town_hall.level)
            spell = aSpell(spell,self.town_hall.level)
            spells_ph.append(spell)
        self.spells = spells_ph

        pets_placeholder = []
        for pet_name in PetAvailability.return_all_unlocked(self.town_hall.level):
            get_pet = [pet for pet in self.pets if pet.name == pet_name]
            if len(get_pet) == 0:
                pet = self.bot.coc_client.get_pet(name=pet_name,townhall=self.town_hall.level)
            else:
                pet = get_pet[0]
            pet = aHeroPet(pet,self.town_hall.level)
            pets_placeholder.append(pet)
        self.hero_pets = pets_placeholder
        self.pets = self.hero_pets

        self.hero_strength = sum([hero.level for hero in self.heroes])
        self.max_hero_strength = sum([hero.maxlevel_for_townhall for hero in self.heroes])
        self.min_hero_strength = sum([hero.minlevel_for_townhall for hero in self.heroes])

        self.hero_rushed_pct = 0
        rushed_heroes = sum([(h.minlevel_for_townhall - h.level) for h in self.heroes if h.is_rushed])
        if self.min_hero_strength > 0:
            self.hero_rushed_pct = round((rushed_heroes / self.min_hero_strength)*100,2)

        self.troop_strength = sum([troop.level for troop in self.troops if not troop.is_super_troop]) + sum([pet.level for pet in self.hero_pets])
        self.max_troop_strength = (sum([troop.maxlevel_for_townhall for troop in self.troops if not troop.is_super_troop]) + sum([pet.maxlevel_for_townhall for pet in self.hero_pets]))
        self.min_troop_strength = (sum([troop.minlevel_for_townhall for troop in self.troops if not troop.is_super_troop]) + sum([pet.minlevel_for_townhall for pet in self.hero_pets]))

        self.troop_rushed_pct = 0
        rushed_troops = sum([(t.minlevel_for_townhall - t.level) for t in self.troops if t.is_rushed and not t.is_super_troop]) + sum([(p.minlevel_for_townhall - p.level) for p in self.hero_pets if p.is_rushed])
        if self.min_troop_strength > 0:
            self.troop_rushed_pct = round((rushed_troops / self.min_troop_strength)*100,2)

        self.spell_strength = sum([spell.level for spell in self.spells])
        self.max_spell_strength = (sum([spell.maxlevel_for_townhall for spell in self.spells]))
        self.min_spell_strength = (sum([spell.minlevel_for_townhall for spell in self.spells]))

        self.spell_rushed_pct = 0
        rushed_spells = sum([(s.minlevel_for_townhall - s.level) for s in self.spells if s.is_rushed])
        if self.min_spell_strength > 0:
            self.spell_rushed_pct = round((rushed_spells / self.min_spell_strength)*100,2)

        self.overall_rushed_pct = 0
        if self.min_hero_strength + self.min_troop_strength + self.min_spell_strength > 0:
            rushed_pct = (rushed_heroes + rushed_troops + rushed_spells) / (self.min_hero_strength + self.min_troop_strength + self.min_spell_strength)
            self.overall_rushed_pct = round(rushed_pct*100,2)
        
        self._attributes = _PlayerAttributes(player=self)
    
    #convenience function to retrieve from the cache
    @classmethod
    def from_cache(cls,tag):
        client = BotClashClient()
        n_tag = coc.utils.correct_tag(tag)        
        player = client.player_cache.get(n_tag)
        if player:
            return player        
        client.player_cache.add_to_queue(tag)
        #client.cog.coc_data_log.warning(f"Player {tag} not found in cache."
        #    + (f" Already in queue." if tag in client.player_cache.queue else " Added to queue."))
        raise CacheNotReady
        
    @classmethod
    async def create(cls,tag,no_cache=False,bot=None):        

        n_tag = coc.utils.correct_tag(tag)
        if not coc.utils.is_valid_tag(tag):
            raise InvalidTag(tag)
        
        if bot:
            bot = bot
            client = bot.get_cog("ClashOfClansClient").client
        else:
            client = BotClashClient()
            bot = client.bot
        
        try:
            cached = client.player_cache.get(n_tag)
        except:
            cached = None

        if not no_cache and isinstance(cached,aPlayer):
            if pendulum.now().int_timestamp - cached.timestamp.int_timestamp < 3600:
                return cached

        try:
            player = await bot.coc_client.get_player(n_tag,cls=aPlayer,bot=bot)           
        except coc.NotFound as exc:
            raise InvalidTag(tag) from exc
        except (coc.InvalidArgument,coc.InvalidCredentials,coc.Maintenance,coc.Forbidden,coc.GatewayError) as exc:
            if cached:
                return cached
            else:
                raise ClashAPIError(exc) from exc

        if player._attributes._new_player:
            player.first_seen = pendulum.now()
            client.cog.coc_data_log.info(f"Player {player}: New Player Detected")

        player.clan = await aClan.create(player.clan_tag) if player.clan_tag else aClan()
        
        await client.player_cache.set(player.tag,player)        
        return player
    
    def cwl_player(self,season:aClashSeason):
        return WarLeaguePlayer(self.tag,season)
    
    async def fetch_season_data(self):
        await aPlayerSeason.fetch_all_for_player(self.tag)

    ##################################################
    ### PLAYER ATTRIBUTES
    ##################################################    
    @property
    def discord_user(self) -> int:
        return self._attributes.discord_user
    @discord_user.setter
    def discord_user(self,discord_user_id:int):
        self._attributes.discord_user = discord_user_id

    @property
    def is_member(self) -> bool:
        return self._attributes.is_member        
    @is_member.setter
    def is_member(self,member_boolean:bool):
        self._attributes.is_member = member_boolean
    
    @property
    def home_clan(self):
        return self._attributes.home_clan
    @home_clan.setter
    def home_clan(self,clan): #accepts aClan object
        self._attributes.home_clan = clan
    
    @property
    def first_seen(self):
        return self._attributes.first_seen
    @first_seen.setter
    def first_seen(self,datetime:pendulum.datetime):
        self._attributes.first_seen = datetime

    @property
    def last_joined(self):
        return self._attributes.last_joined
    @last_joined.setter
    def last_joined(self,datetime:pendulum.datetime):
        self._attributes.last_joined = datetime

    @property
    def last_removed(self):
        return self._attributes.last_removed
    @last_removed.setter
    def last_removed(self,datetime:pendulum.datetime):
        self._attributes.last_removed = datetime
    
    ##################################################
    ### PLAYER SEASON STATS
    ##################################################
    @property
    def current_season(self):
        return aPlayerSeason(self,self.client.cog.current_season)
    
    @property
    def season_data(self):
        return {season.id:aPlayerSeason(self,season) for season in self.client.cog.tracked_seasons}
    
    def get_season_stats(self,season:aClashSeason):
        return aPlayerSeason(self,season)

    async def stat_update(self):        
        async with self.current_season._update_lock:
            if self.timestamp <= self.current_season.update_time:
                return
            
            update_data = await self.current_season.update_data(self)
            update_seen = await self.current_season.compute_last_seen(self)
            self.current_season.update_time = self.timestamp
            self.current_season.player = self
            if update_data > 0 or update_seen > 0 or random.random() < 0.05:
                self.current_season.save()
    
    ##################################################
    ### DATA FORMATTERS
    ##################################################
    def __str__(self):
        return f"{self.name} ({self.tag})"
    
    def __eq__(self,other):
        return isinstance(other,aPlayer) and self.tag == other.tag
    
    def __hash__(self):
        return hash(self.tag)
        
    @property
    def title(self):
        return f"{self.town_hall.emote} {self.name} ({self.tag})"    
    
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
        return f"{str(self.role)} of {self.clan.name}" if self.clan.tag else "No Clan"
    
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
    def alliance_rank(self):
        if self.is_member:
            if self.discord_user == self.home_clan.leader:
                rank = 'Leader'
            elif self.discord_user in self.home_clan.coleaders:
                rank = 'Co-Leader'
            elif self.discord_user in self.home_clan.elders:
                rank = 'Elder'
            else:
                rank = 'Member'
        else:
            rank = 'Non-Member'
        return rank
    
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
        
    @property
    def discord_user_str(self):
        return f"{EmojisUI.DISCORD} <@{str(self.discord_user)}>" if self.discord_user else ""
    
    @property
    def league_icon(self):
        return self.league.icon.medium if self.league.name != "Unranked" else None
    
    @property
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
    
    ##################################################
    ### PLAYER METHODS
    ##################################################
    def get_hero(self,hero_name:str):
        return next((hero for hero in self.heroes if hero.name == hero_name),None)
    
    def get_cwl_player(self,season:aClashSeason):
        return WarLeaguePlayer(self.tag,season)
    
    def new_member(self,user_id:int,home_clan): #home_clan param accepts aClan object
        if not self.is_member or not self.last_joined:
            self.last_joined = pendulum.now()

        self.home_clan = home_clan
        self.discord_user = user_id
        self.is_member = True
        self.client.cog.coc_data_log.info(f"Player {self} is now an Alliance member!")

    def remove_member(self):
        self.home_clan = aClan()
        self.is_member = False
        self.last_removed = pendulum.now()
        self.client.cog.coc_data_log.info(f"Player {self} has been removed as a member.")
    
    async def add_link(self):
        client = BotClashClient()
        await client.add_link(self.tag,self.discord_user)

    # def add_note(self,ctx,message):
    #         new_note = await aNote.new_note(ctx,message)
    #         new_note_id = new_note.save_note_to_db()
    #         self.notes.append(new_note_id)
    #         self.save_player_to_db()

class aTownHall():
    def __init__(self,level=1,weapon=0):
        self.level = level
        self.weapon = weapon    
    @property
    def emoji(self):
        return EmojisTownHall.get(self.level)    
    @property
    def emote(self):
        return EmojisTownHall.get(self.level)    
    @property
    def description(self):
        if self.level >= 12:
            return f"**{self.level}**-{self.weapon}"
        else:
            return f"**{self.level}**"

class aHero():
    def __init__(self,data:coc.Hero,townhall_level:int):
        self.id = data.id
        self.name = data.name
        self.emoji = EmojisHeroes.get(self.name)
        try:
            self.level = int(data.level)
        except:
            self.level = 0
        self.village = getattr(data,'village','home')
        self.maxlevel_for_townhall = int(0 if data.get_max_level_for_townhall(max(townhall_level,3)) is None else data.get_max_level_for_townhall(max(townhall_level,3)))
        if townhall_level == 15:
            if self.name in ['Barbarian King','Archer Queen']:
                self.maxlevel_for_townhall = 90
            elif self.name in ['Grand Warden']:
                self.maxlevel_for_townhall = 65
            elif self.name in ['Royal Champion']:
                self.maxlevel_for_townhall = 40

        if townhall_level == HeroAvailability.unlocked_at(self.name):
            self.minlevel_for_townhall = 0
        else:
            try:
                self.minlevel_for_townhall = data.get_max_level_for_townhall(max(townhall_level-1,3))
            except:
                self.minlevel_for_townhall = 0
            if self.minlevel_for_townhall == None:
                self.minlevel_for_townhall = 0

        if self.level < self.minlevel_for_townhall:
            self.is_rushed = True
        else:
            self.is_rushed = False

class aHeroPet():
    def __init__(self,data:coc.Pet,townhall_level:int):
        self.id = data.id
        self.name = data.name
        self.emoji = EmojisPets.get(self.name)
        if not isinstance(getattr(data,'level',0),int):
            self.level = 0
        else:
            self.level = int(getattr(data,'level',0))
        self.village = getattr(data,'village','home')

        self.maxlevel_for_townhall = 10 #all pets have max level of 10
        if self.name in ['L.A.S.S.I','Mighty Yak'] and townhall_level == 15:
            self.maxlevel_for_townhall = 15
        if townhall_level <= PetAvailability.unlocked_at(self.name):
            self.minlevel_for_townhall = 0
        else:
            self.minlevel_for_townhall = int(0 if data.get_max_level_for_townhall(max(townhall_level-1,3)) is None else data.get_max_level_for_townhall(max(townhall_level-1,3)))
        
        if self.level < self.minlevel_for_townhall:
            self.is_rushed = True
        else:
            self.is_rushed = False

class aTroop():
    def __init__(self,**kwargs):
        data = kwargs.get('data',None)
        townhall_level = kwargs.get('townhall_level',1)
        init = kwargs.get('init',True)

        if init:
            self.id = getattr(data,'id',0)
            self.name = getattr(data,'name','')
            self.emoji = EmojisTroops.get(self.name)

            if not isinstance(getattr(data,'level',0),int):
                self.level = 0
            else:
                self.level = int(getattr(data,'level',0))

            self.village = getattr(data,'village','home')

            self.is_elixir_troop = getattr(data,'is_elixir_troop',False)
            self.is_dark_troop = getattr(data,'is_dark_troop',False)
            self.is_siege_machine = getattr(data,'is_siege_machine',False)
            self.is_super_troop = getattr(data,'is_super_troop',False)

            if self.is_super_troop:
                self.original_troop = aTroop(
                    data=data.original_troop,
                    townhall_level=townhall_level
                    )
            else:
                self.original_troop = None

            self.maxlevel_for_townhall = int(0 if data.get_max_level_for_townhall(max(townhall_level,3)) is None else data.get_max_level_for_townhall(max(townhall_level,3)))
            if townhall_level == 15 and self.name in ['Goblin','P.E.K.K.A','Valkyrie','Healer','Dragon','Hog Rider','Bowler','Baby Dragon','Yeti','Ice Golem','Wall Wrecker','Stone Slammer']:
                self.maxlevel_for_townhall += 1

            if townhall_level <= TroopAvailability.unlocked_at(self.name):
                self.minlevel_for_townhall = 0
            else:
                self.minlevel_for_townhall = int(0 if data.get_max_level_for_townhall(max(townhall_level-1,3)) is None else data.get_max_level_for_townhall(max(townhall_level-1,3)))

            if self.level < self.minlevel_for_townhall:
                self.is_rushed = True
            else:
                self.is_rushed = False
    
    @classmethod
    def apprentice_warden(cls,townhall_level:int,data:Optional[coc.Troop]=None):
        min_level = {13:0,14:2,15:3}
        max_level = {13:2,14:3,15:4}

        troop = cls(init=False)
        troop.id = 0
        troop.name = 'Apprentice Warden'
        troop.emoji = EmojisTroops.APPRENTICE_WARDEN
        troop.level = getattr(data,'level',0)
        troop.village = 'home'
        troop.is_elixir_troop = False
        troop.is_dark_troop = True
        troop.is_siege_machine = False
        troop.is_super_troop = False
        troop.original_troop = None
        troop.maxlevel_for_townhall = max_level.get(townhall_level,0)
        troop.minlevel_for_townhall = min_level.get(townhall_level,0)

        if troop.level < troop.minlevel_for_townhall:
            troop.is_rushed = True
        else:
            troop.is_rushed = False
        return troop

    @classmethod
    def super_hog_rider(cls,api_player:coc.Player,townhall_level:int,data:Optional[coc.Troop]=None):
        min_level = {13:1,14:2,15:3}
        max_level = {13:1,14:2,15:3}

        troop = cls(init=False)
        troop.id = 0
        troop.name = 'Super Hog Rider'
        troop.emoji = EmojisTroops.SUPER_HOG_RIDER
        troop.level = getattr(data,'level',0)
        troop.village = 'home'
        troop.is_elixir_troop = False
        troop.is_dark_troop = True
        troop.is_siege_machine = False
        troop.is_super_troop = True
        troop.original_troop = aTroop(
            data=api_player.get_troop('Hog Rider'),
            townhall_level=townhall_level
            )
        troop.maxlevel_for_townhall = max_level.get(townhall_level,0)
        troop.minlevel_for_townhall = min_level.get(townhall_level,0)
        troop.is_rushed = False
        return troop

class aSpell():
    def __init__(self,data:coc.Spell,townhall_level:int):
        self.id = getattr(data,'id',0)
        self.name = getattr(data,'name','')
        self.emoji = EmojisSpells.get(self.name)

        if not isinstance(getattr(data,'level',0),int):
            self.level = 0
        else:
            self.level = int(getattr(data,'level',0))
        self.village = getattr(data,'village','home')

        self.is_elixir_spell = getattr(data,'is_elixir_spell',False)
        self.is_dark_spell = getattr(data,'is_dark_spell',False)

        self.maxlevel_for_townhall = int(0 if data.get_max_level_for_townhall(max(townhall_level,3)) is None else data.get_max_level_for_townhall(max(townhall_level,3)))

        if townhall_level == 15 and self.name in ['Clone Spell','Skeleton Spell']:
            self.maxlevel_for_townhall += 1

        if townhall_level <= SpellAvailability.unlocked_at(self.name):
            self.minlevel_for_townhall = 0
        else:
            self.minlevel_for_townhall = int(0 if data.get_max_level_for_townhall(max(townhall_level-1,3)) is None else data.get_max_level_for_townhall(max(townhall_level-1,3)))

        if self.level < self.minlevel_for_townhall:
            self.is_rushed = True
        else:
            self.is_rushed = False

##################################################
#####
##### PLAYER ATTRIBUTES OBJECT
#####
##################################################
class _PlayerAttributes():
    _cache = {}

    def __new__(cls,player:aPlayer):        
        if player.tag not in cls._cache:
            instance = super().__new__(cls)
            instance._is_new = True
            cls._cache[player.tag] = instance
        return cls._cache[player.tag]
    
    def __init__(self,player:aPlayer):
        self.client = BotClashClient()
        self.bot = self.client.bot

        self.player = player

        self.tag = self.player.tag
        self.name = self.player.name

        if self._is_new:
            player_database = None
            try:
                player_database = db_Player.objects.get(tag=self.tag).to_mongo().to_dict()
            except DoesNotExist:
                self._new_player = True
                self._discord_user = 0
                self._is_member = False
                self._home_clan_tag = None
                self._first_seen = self.player.timestamp.int_timestamp
                self._last_joined = None
                self._last_removed = None
            else:
                player_database = db_Player.objects.get(tag=self.tag).to_mongo().to_dict()
            
            if player_database:
                self._new_player = False
                self._discord_user = player_database.get('discord_user',0)
                self._is_member = player_database.get('is_member',False)
                self._home_clan_tag = player_database.get('home_clan',None)
                self._first_seen = player_database.get('first_seen',0)
                self._last_joined = player_database.get('last_joined',0)
                self._last_removed = player_database.get('last_removed',0)
        
            self._is_new = False
    
    def __str__(self):
        return f"{self.name} ({self.tag})"
    def __eq__(self,other):
        return isinstance(other,_PlayerAttributes) and self.tag == other.tag    
    def __hash__(self):
        return hash(self.tag)
    
    def save(self):
        self._new_player = False
        player_data = db_Player(
            tag=self.tag,
            name=self.name,
            discord_user=self._discord_user,
            is_member=self._is_member,
            home_clan=self._home_clan_tag,
            first_seen=self._first_seen,
            last_joined=self._last_joined,
            last_removed=self._last_removed
            )
        player_data.save()
        self.client.cog.coc_data_log.info(
            f'Player {self.name} ({self.tag}): attributes saved to database.'
            )
    
    @property
    def discord_user(self) -> int:
        return getattr(self,'_discord_user',0)
    @discord_user.setter
    def discord_user(self,discord_user_id:int):
        self.client.cog.coc_data_log.info(
            f"Player {self}: discord_user set to {discord_user_id}. Previous value: {getattr(self,'_discord_user',0)}."
            )
        self._discord_user = discord_user_id
        self.save()

    @property
    def is_member(self) -> bool:
        val = getattr(self,'_is_member',False)
        try:
            home_clan = self.home_clan
        except CacheNotReady:
            return val
        else:
            if self.player:
                if val and not getattr(home_clan,'is_alliance_clan',False):
                    self.client.cog.coc_data_log.info(
                        f"Player {self}: Removing as Member as their previous Home Clan is no longer recognized as an Alliance clan."
                        )
                    self.player.remove_member()
            return val
    @is_member.setter
    def is_member(self,member_boolean:bool):
        self.client.cog.coc_data_log.info(
            f"Player {self}: is_member set to {member_boolean}. Previous value: {getattr(self,'_is_member',False)}."
            )
        self._is_member = member_boolean
        self.save()
    
    @property
    def home_clan(self):
        tag = getattr(self,'_home_clan_tag',None)
        if tag:
            return aClan.from_cache(tag)
        return aClan()
    @home_clan.setter
    def home_clan(self,clan):
        self.client.cog.coc_data_log.info(
            f"Player {self}: home_clan set to {getattr(clan,'tag')}. Previous value: {getattr(self.home_clan,'tag',None)}."
            )
        self._home_clan_tag = getattr(clan,'tag',None)
        self.save()
    
    @property
    def first_seen(self):
        ts = getattr(self,'_first_seen',0)
        return None if ts == 0 else pendulum.from_timestamp(ts)
    @first_seen.setter
    def first_seen(self,datetime:pendulum.datetime):
        self._first_seen = datetime.int_timestamp
        self.client.cog.coc_data_log.info(
            f"Player {self}: first_seen set to {datetime}."
            )
        self.save()

    @property
    def last_joined(self):
        ts = getattr(self,'_last_joined',0)
        return None if ts == 0 else pendulum.from_timestamp(ts)
    @last_joined.setter
    def last_joined(self,datetime:pendulum.datetime):
        self._last_joined = datetime.int_timestamp
        self.client.cog.coc_data_log.info(
            f"Player {self}: last_joined set to {datetime}."
            )
        self.save()

    @property
    def last_removed(self):
        ts = getattr(self,'_last_removed',0)
        return None if ts == 0 else pendulum.from_timestamp(ts)
    @last_removed.setter
    def last_removed(self,datetime:pendulum.datetime):
        self._last_removed = datetime.int_timestamp
        self.client.cog.coc_data_log.info(
            f"Player {self}: last_removed set to {datetime}."
            )
        self.save()