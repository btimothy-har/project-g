import coc
import hashlib
import pendulum

from typing import *
from mongoengine import *

from collections import defaultdict
from redbot.core.utils import AsyncIter

from ...api_client import BotClashClient as client

from ..season.season import aClashSeason
from ..clans.base_clan import BasicClan
from ..players.base_player import BasicPlayer

from .mongo_events import db_ClanWar

from ...utils.constants.coc_constants import ClanWarType, WarResult, WarState
from ...utils.constants.coc_emojis import EmojisClash
from ...utils.constants.ui_emojis import EmojisUI

bot_client = client()

class aClanWar():
    _cache = {}

    @classmethod
    async def load_all(cls) -> List['aClanWar']:
        query = db_ClanWar.objects()
        ret = []
        async for war in AsyncIter(query):
            ret.append(cls(war_id=war.war_id))
        return sorted(ret, key=lambda w:(w.preparation_start_time),reverse=True)

    @classmethod
    def for_player(cls,player_tag:str,season:aClashSeason):
        if season:
            query = db_ClanWar.objects(
                Q(members__tag=player_tag) &
                Q(type=ClanWarType.RANDOM) &
                Q(preparation_start_time__gte=season.season_start.int_timestamp) &
                Q(preparation_start_time__lte=season.season_end.int_timestamp)
                ).only('war_id')
        else:
            query = db_ClanWar.objects(
                Q(members__tag=player_tag) & Q(type=ClanWarType.RANDOM)
                ).only('war_id')        
        ret_wars = [cls(war_id=war.war_id) for war in query]
        return sorted(ret_wars, key=lambda w:(w.preparation_start_time),reverse=True)

    @classmethod
    def for_clan(cls,clan_tag:str,season:aClashSeason):
        if season:
            query = db_ClanWar.objects(
                Q(clans__tag=clan_tag) &
                Q(type=ClanWarType.RANDOM) &
                Q(preparation_start_time__gte=season.season_start.int_timestamp) &
                Q(preparation_start_time__lte=season.season_end.int_timestamp)
                ).only('war_id')
        else:
            query = db_ClanWar.objects(
                Q(clans__tag=clan_tag) & Q(type=ClanWarType.RANDOM)
                ).only('raid_id')        
        ret_war = [cls(war_id=war.war_id) for war in query]
        return sorted(ret_war, key=lambda w:(w.preparation_start_time),reverse=True)

    def __new__(cls,war_id:str):
        if war_id not in cls._cache:
            instance = super().__new__(cls)
            instance._is_new = True
            cls._cache[war_id] = instance
        return cls._cache[war_id]
    
    def __init__(self,war_id:str):
        self.war_id = war_id

        if self._is_new:
            self._found_in_db = False

            self.type = ""
            self._state = ""
            self.war_tag = ""        
            self.preparation_start_time = None
            self.start_time = None
            self.end_time = None
            self.team_size = 0
            self.attacks_per_member = 0
            self.clan_1 = None
            self.clan_2 = None
            self._league_group = ""
            self._members = []
            self._attacks = []

            self.is_alliance_war = False

            self._last_save = None
            
            try:
                war_data = db_ClanWar.objects.get(war_id=war_id).to_mongo().to_dict()
            except DoesNotExist:
                war_data = None
            else:
                self._found_in_db = True
                self.type = war_data['type']
                self._state = war_data['state']
                self.war_tag = war_data['war_tag']
                
                self.preparation_start_time = pendulum.from_timestamp(war_data['preparation_start_time'])
                self.start_time = pendulum.from_timestamp(war_data['start_time'])
                self.end_time = pendulum.from_timestamp(war_data['end_time'])
                self.team_size = war_data['team_size']
                self.attacks_per_member = war_data['attacks_per_member']
                self.clan_1 = aWarClan(self,json=war_data['clans'][0])
                self.clan_2 = aWarClan(self,json=war_data['clans'][1])
                self._league_group = war_data.get('league_group','')
                self._members = [aWarPlayer(self,json=member) for member in war_data['members']]
                self._attacks = [aWarAttack(self,json=attack) for attack in war_data['attacks']]
                self.is_alliance_war = war_data['is_alliance_war']
                self._last_save = pendulum.from_timestamp(war_data.get('last_save',0)) if war_data.get('last_save',0) > 0 else None

    @classmethod
    async def create_from_api(cls,data:coc.ClanWar,league_group_id:str=None) -> 'aClanWar':
        base_war_id = ''.join(sorted([data.clan.tag,data.opponent.tag])) + str(pendulum.instance(data.preparation_start_time.time).int_timestamp)
        war_id = hashlib.sha256(base_war_id.encode()).hexdigest()

        clan_war = cls(war_id=war_id)

        if league_group_id:
            clan_war._league_group = league_group_id
        
        if data.type in ['classic','random']:
            clan_war.type = ClanWarType.RANDOM
        else:
            clan_war.type = data.type

        if data.state != clan_war._state:
            clan_war._found_in_db = False

        clan_war._state = data.state
        clan_war.war_tag = data.war_tag

        clan_war.preparation_start_time = pendulum.instance(data.preparation_start_time.time)
        clan_war.start_time = pendulum.instance(data.start_time.time)
        clan_war.end_time = pendulum.instance(data.end_time.time)

        clan_war.team_size = data.team_size
        clan_war.attacks_per_member = data.attacks_per_member

        clan_war.clan_1 = aWarClan(war=clan_war,data=data.clan)
        clan_war.clan_2 = aWarClan(war=clan_war,data=data.opponent)

        clan_war._members = [aWarPlayer(war=clan_war,data=mem) for mem in data.members]
        clan_war._attacks = [aWarAttack(war=clan_war,data=att) for att in data.attacks]

        if clan_war.clan_1.is_alliance_clan or clan_war.clan_2.is_alliance_clan:
            clan_war.is_alliance_war = True
        else:
            clan_war.is_alliance_war = False
        
        if clan_war.do_i_save:
            clan_war.save_to_database()
        return clan_war

    def save_to_database(self):
        self._last_save = pendulum.now()
        db_war = db_ClanWar(
            war_id=self.war_id,
            type=self.type,
            state=self.state,
            war_tag=self.war_tag,
            league_group=self._league_group,
            preparation_start_time=self.preparation_start_time.int_timestamp,
            start_time=self.start_time.int_timestamp,
            end_time=self.end_time.int_timestamp,
            team_size=self.team_size,
            attacks_per_member=self.attacks_per_member,
            clans=[self.clan_1.to_json(),self.clan_2.to_json()],
            members=[m.to_json() for m in self._members],
            attacks=[a.to_json() for a in self._attacks],
            is_alliance_war=self.is_alliance_war,
            last_save=self._last_save.int_timestamp
            )
        db_war.save()
    
    @property
    def do_i_save(self) -> bool:
        now = pendulum.now()
        if not self._found_in_db:
            return True
        if self._state == 'inWar':
            if not self._last_save:
                return True
            if now.int_timestamp - getattr(self._last_save,'int_timestamp',0) > 60:
                return True
        if self.end_time <= pendulum.now() <= self.end_time.add(hours=2):
            return True
        return False
    
    @property
    def state(self) -> WarState:
        if self.preparation_start_time <= pendulum.now() < self.start_time:
            return WarState.PREPARATION
        elif self.start_time <= pendulum.now() < self.end_time:
            return WarState.INWAR
        elif self.end_time <= pendulum.now():
            return WarState.WAR_ENDED

    ##################################################
    ##### DATA FORMATTERS
    ##################################################    
    def __str__(self) -> str:
        return f"{self.preparation_start_time.format('DD MMM YYYY')} {self.clan_1.name} vs {self.clan_2.name}"
    
    def __eq__(self, __value: object) -> bool:
        return isinstance(__value, aClanWar) and self.preparation_start_time == __value.preparation_start_time and __value.clan_1.tag in [self.clan_1.tag,self.clan_2.tag] and __value.clan_2.tag in [self.clan_1.tag,self.clan_2.tag]
    
    def __hash__(self):
        return self.war_id

    @property
    def emoji(self) -> str:
        if self.type == ClanWarType.CWL:
            return EmojisClash.WARLEAGUES
        elif self.type == ClanWarType.FRIENDLY:
            return EmojisUI.HANDSHAKE
        else:
            return EmojisClash.CLANWAR
    
    ##################################################
    ##### CLASS HELPERS
    ##################################################        
    @property
    def league_group_id(self) -> Optional[str]:
        if self._league_group:
            return self._league_group
        return None

    # @property
    # def league_round(self) -> Optional[int]:
    #     return self.league_group.get_round_from_war(self)
    
    @property
    def members(self) -> List['aWarPlayer']:
        return sorted(self._members,key=lambda x:(x.map_position,(x.town_hall*-1)))
    
    @property
    def attacks(self) -> List['aWarAttack']:
        return sorted(self._attacks,key=lambda x: x.order)

    def get_member(self,tag:str) -> Optional['aWarPlayer']:
        find_member = [wm for wm in self.members if wm.tag == tag]
        if len(find_member) == 0:
            return None
        else:
            return find_member[0]
        
    def get_clan(self,tag:str) -> Optional['aWarClan']:
        if self.clan_1.tag == tag:
            return self.clan_1
        elif self.clan_2.tag == tag:
            return self.clan_2
        else:
            return None
 
    def get_opponent(self,tag:str) -> Optional['aWarClan']:
        if self.clan_1.tag == tag:
            return self.clan_2
        elif self.clan_2.tag == tag:
            return self.clan_1
        else:
            return None

class aWarClan(BasicClan):
    def __init__(self,war,**kwargs):
        self.war = war

        json_data = kwargs.get('json',None)
        game_data = kwargs.get('data',None)

        BasicClan.__init__(self)

        self.exp_earned = 0

        if json_data:
            self.tag = json_data['tag']
            self.name = json_data['name']
            self.badge = json_data.get('badge',None)
            self.level = json_data.get('level',None)
            self.stars = json_data['stars']
            self.destruction = json_data['destruction']
            self.average_attack_duration = json_data['average_attack_duration']
            self.exp_earned = json_data.get('exp_earned',0)

            if 'attacks_used' in list(json_data.keys()):
                self.attacks_used = json_data['attacks_used']
            else:
                self.attacks_used = json_data['total_attacks']

        if game_data:
            self.tag = game_data.tag
            self.name = game_data.name
            self.badge = game_data.badge.url
            self.level = game_data.level
            self.stars = game_data.stars
            self.destruction = game_data.destruction
            self.average_attack_duration = game_data.average_attack_duration
            self.attacks_used = game_data.attacks_used

        self.max_stars = self.war.team_size * self.war.attacks_per_member
        self._result = None

    def to_json(self) -> dict:
        return {
            'tag': self.tag,
            'name': self.name,
            'badge': self.badge,
            'level': self.level,
            'stars': self.stars,
            'destruction': self.destruction,
            'average_attack_duration': self.average_attack_duration,
            'exp_earned': self.exp_earned,
            'attacks_used': self.attacks_used
            }
        
    @property
    def lineup(self) -> Dict[int,int]:
        th_levels = defaultdict(int)        
        for player in self.members:
            th_levels[player.town_hall] += 1
        return th_levels
    
    @property
    def available_hits_by_townhall(self) -> Dict[int,int]:
        th_levels = defaultdict(int)        
        for player in self.members:
            if player.unused_attacks > 0:
                th_levels[player.town_hall] += player.unused_attacks
        return th_levels
    
    @property
    def average_townhall(self) -> float:
        return round(sum([player.town_hall for player in self.members]) / len(self.members),2)    
    
    @property
    def emoji(self) -> str:
        if self.war.type == ClanWarType.CWL:
            return EmojisClash.WARLEAGUES
        elif self.war.type == ClanWarType.FRIENDLY:
            return EmojisUI.HANDSHAKE
        elif self.war.type == ClanWarType.RANDOM:
            if self.is_alliance_clan:
                return self._emoji
            else:
                return EmojisClash.CLANWAR    
    @property
    def result(self) -> WarResult:
        if self._result is None or pendulum.now() < self.war.end_time:
            self.compute_result()
        return self._result
    
    @property
    def members(self) -> List['aWarPlayer']:
        return [m for m in self.war.members if m.clan_tag == self.tag]
    
    @property
    def attacks(self) -> List['aWarAttack']:
        return [a for a in self.war.attacks if a.attacker.clan_tag == self.tag]
    
    @property
    def unused_attacks(self) -> int:
        return sum([player.unused_attacks for player in self.members])
    
    @property
    def defenses(self) -> List['aWarAttack']:
        return [a for a in self.war.attacks if a.defender.clan_tag == self.tag]
    
    # @property
    # def war_stats(self):
    #     if hasattr(self, '_war_stats') and self._war_stats.timestamp < self.war.end_time:
    #         if pendulum.now().int_timestamp - self._war_stats.timestamp.int_timestamp > 3600:
    #             del self._war_stats
    #     return self._war_stats
    
    # @cached_property
    # def _war_stats(self):
    #     return aSummaryWarStats.for_clan(
    #         clan_tag=self.tag,
    #         war_log=[self.war]
    #         )

    def compute_result(self):
        opponent = self.war.get_opponent(self.tag)
        
        if self.stars == opponent.stars:
            if self.destruction > opponent.destruction:
                self._result = WarResult.ended(WarResult.WON) if pendulum.now() > self.war.end_time else WarResult.ongoing(WarResult.WON)
            elif self.destruction < opponent.destruction:
                self._result = WarResult.ended(WarResult.LOST) if pendulum.now() > self.war.end_time else WarResult.ongoing(WarResult.LOST)
            else:
                self._result = WarResult.ended(WarResult.TIED) if pendulum.now() > self.war.end_time else WarResult.ongoing(WarResult.TIED)
        elif self.stars > opponent.stars:
            self._result = WarResult.ended(WarResult.WON) if pendulum.now() > self.war.end_time else WarResult.ongoing(WarResult.WON)
        elif self.stars < opponent.stars:
            self._result = WarResult.ended(WarResult.LOST) if pendulum.now() > self.war.end_time else WarResult.ongoing(WarResult.LOST)
        else:
            self._result = WarResult.ended(WarResult.TIED) if pendulum.now() > self.war.end_time else WarResult.ongoing(WarResult.TIED)

class aWarPlayer(BasicPlayer):
    def __init__(self,war,**kwargs):
        self.war = war

        BasicPlayer.__init__(self)

        json_data = kwargs.get('json',None)
        game_data = kwargs.get('data',None)
        clan_tag = kwargs.get('clan_tag',None)

        if json_data:
            self.tag = json_data['tag']
            self.name = json_data['name']
            self.town_hall = json_data['town_hall']
            self.map_position = json_data['map_position']

            self.clan_tag = json_data.get('clan_tag',clan_tag)

        if game_data:
            self.tag = game_data.tag
            self.name = game_data.name
            self.town_hall = game_data.town_hall
            self.map_position = game_data.map_position
            self.clan_tag = game_data.clan.tag
    
    def to_json(self):
        return {
            'tag': self.tag,
            'name': self.name,
            'town_hall': self.town_hall,
            'map_position': self.map_position,
            'clan_tag': self.clan_tag
            }
    
    @property
    def clan(self) -> aWarClan:
        return self.war.get_clan(self.clan_tag)
    
    @property
    def opponent(self) -> aWarClan:
        return self.war.get_opponent(self.clan_tag)
    
    @property
    def attacks(self) -> List['aWarAttack']:
        return sorted([att for att in self.war.attacks if att.attacker_tag == self.tag],key=lambda x:x.order)
    
    @property
    def defenses(self) -> List['aWarAttack']:
        return sorted([att for att in self.war.attacks if att.defender_tag == self.tag],key=lambda x:x.order)
    
    @property
    def unused_attacks(self) -> int:
        return self.war.attacks_per_member - len(self.attacks)
    @property
    def defense_count(self) -> int:
        return len(self.defenses)
    
    @property
    def total_stars(self) -> int:
        return sum([a.stars for a in self.attacks])
    
    @property
    def total_destruction(self) -> float:
        return sum([a.destruction for a in self.attacks])
    
    @property
    def star_count(self) -> int:
        return sum([a.new_stars for a in self.attacks])
    
    @property
    def best_opponent_attack(self) -> Optional['aWarAttack']:
        best_defense = sorted(self.defenses,key=lambda x:(x.stars,x.destruction,(x.order*-1)),reverse=True)
        if len(best_defense) > 0:
            return best_defense[0]
        return None

class aWarAttack():
    def __init__(self,war,**kwargs):
        self.war = war

        json_data = kwargs.get('json',None)
        game_data = kwargs.get('data',None)

        if json_data:
            self.order = json_data.get('order',None)
            if 'attacker_tag' in list(json_data.keys()):
                self.attacker_tag = json_data['attacker_tag']
            else:
                self.attacker_tag = json_data['attacker']

            if 'defender_tag' in list(json_data.keys()):
                self.defender_tag = json_data['defender_tag']
            else:
                self.defender_tag = json_data['defender']

            self.stars = json_data['stars']
            self.destruction = json_data['destruction']
            self.duration = json_data['duration']

            if 'is_fresh_attack' in list(json_data.keys()):
                self.is_fresh_attack = json_data['is_fresh_attack']
            else:
                self.is_fresh_attack = json_data['is_fresh_hit']

        if game_data:
            self.order = game_data.order
            self.attacker_tag = game_data.attacker_tag
            self.defender_tag = game_data.defender_tag

            self.stars = game_data.stars
            self.destruction = game_data.destruction
            self.duration = game_data.duration

            self.is_fresh_attack = game_data.is_fresh_attack

        self._new_stars = None
        self._new_destruction = None
    
    def to_json(self):
        if self.order:
            return {
                'warID': self.war.war_id,
                'order': self.order,
                'stars': self.stars,
                'destruction': self.destruction,
                'duration': self.duration,
                'attacker_tag': self.attacker_tag,
                'defender_tag': self.defender_tag,
                'is_fresh_attack': self.is_fresh_attack
                }
        return None
    
    @property
    def attacker(self) -> aWarPlayer:
        return self.war.get_member(self.attacker_tag)
    
    @property
    def defender(self) -> aWarPlayer:
        return self.war.get_member(self.defender_tag)
    
    @property
    def is_triple(self) -> bool:
        if self.war.type == 'cwl':
            return self.stars==3
        return self.stars==3 and self.attacker.town_hall <= self.defender.town_hall
    
    @property
    def is_best_attack(self) -> bool:
        if len(self.defender.defenses) == 0:
            return False
        return self.defender.best_opponent_attack.order == self.order
    
    @property
    def new_stars(self) -> int:
        if pendulum.now() < self.war.end_time or self._new_stars is None:
            self.compute_attack_stats()
        return self._new_stars
    
    @property
    def new_destruction(self) -> float:
        if pendulum.now() < self.war.end_time or self._new_destruction is None:
            self.compute_attack_stats()
        return self._new_destruction
    
    def compute_attack_stats(self):
        base_stars = 0
        base_destruction = 0
        for attack in [att for att in self.defender.defenses if att.order < self.order]:
            if attack.stars > base_stars:
                base_stars = attack.stars
            if attack.destruction > base_destruction:
                base_destruction = attack.destruction
        self._new_stars = max(0,self.stars - base_stars)
        self._new_destruction = max(0,self.destruction - base_destruction)