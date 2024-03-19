import coc
import hashlib
import pendulum
import logging

from typing import *

from collections import defaultdict
from async_property import AwaitLoader

from ...client.db_client import MotorClient

from ..season.season import aClashSeason
from ..clans.base_clan import BasicClan
from ..players.base_player import BasicPlayer

from ...utils.constants.coc_constants import ClanWarType, WarResult, WarState
from ...utils.constants.coc_emojis import EmojisClash
from ...utils.constants.ui_emojis import EmojisUI

LOG = logging.getLogger("coc.main")

class aClanWar(MotorClient,AwaitLoader):
    _cache = {}
    __slots__ = [
        '_id',
        '_found_in_db',
        '_loaded_from_db',
        '_is_new',
        '_last_save',
        'type',
        '_state',
        'war_tag',
        'preparation_start_time',
        'start_time',
        'end_time',
        'team_size',
        'attacks_per_member',
        'clan_1',
        'clan_2',
        '_league_group',
        '_members',
        '_attacks',
        'is_alliance_war',
        ]

    @classmethod
    async def for_player(cls,player_tag:str,season:Optional[aClashSeason]=None):
        if season:
            query_doc = {
                'members.tag': player_tag,
                'type': ClanWarType.RANDOM,
                'preparation_start_time': {
                    '$gte': season.season_start.int_timestamp,
                    '$lte': season.season_end.int_timestamp
                    }
                }
        else:
            query_doc = {
                'members.tag': player_tag,
                'type': ClanWarType.RANDOM
                }        
        query = cls.database.db__clan_war.find(query_doc,{'_id':1})   
        ret_wars = [await cls(war_id=d['_id']) async for d in query]
        return sorted(ret_wars, key=lambda w:(w.preparation_start_time),reverse=True)

    @classmethod
    async def for_clan(cls,clan_tag:str,season:Optional[aClashSeason]=None):
        if season:
            query_doc = {
                'clans.tag': clan_tag,
                'type': ClanWarType.RANDOM,
                'preparation_start_time': {
                    '$gte': season.season_start.int_timestamp,
                    '$lte': season.season_end.int_timestamp
                    }
                }
        else:
            query_doc = {
                'clans.tag': clan_tag,
                'type': ClanWarType.RANDOM
                }
        query = cls.database.db__clan_war.find(query_doc,{'_id':1})
        ret_wars = [await cls(war_id=d['_id']) async for d in query]
        return sorted(ret_wars, key=lambda w:(w.preparation_start_time),reverse=True)

    def __new__(cls,war_id:str):
        if war_id not in cls._cache:
            instance = super().__new__(cls)
            instance._is_new = True
            cls._cache[war_id] = instance
        return cls._cache[war_id]
    
    def __init__(self,war_id:str):
        self._id = war_id

        if self._is_new:
            self._found_in_db = False
            self._loaded_from_db = False
            self._last_save = None

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

            self._is_new = False
    
    async def _convert(self):
        await self.load()
        await self.database.db__nclan_war.update_one(
            {'_id':self._id},
            {'$set':self._api_json()},
            upsert=True
            )
    
    def _api_json(self):
        json_data = {
            'type': self.type,
            'isAllianceWar': self.is_alliance_war,
            'state': self._state,
            'teamSize': self.team_size,
            'attacksPerMember': self.attacks_per_member,
            'preparationStartTime': self.preparation_start_time.format('YYYYMMDDTHHmmss') + '.000Z',
            'preparationStartTimeISO': self.preparation_start_time,
            'startTime': self.start_time.format('YYYYMMDDTHHmmss') + '.000Z',
            'startTimeISO': self.start_time,
            'endTime': self.end_time.format('YYYYMMDDTHHmmss') + '.000Z',
            'endTimeISO': self.end_time,
            'clan': self.clan_1._api_json(),
            'opponent': self.clan_2._api_json()
            }

        if self.type == ClanWarType.CWL:
            json_data['leagueGroup'] = self._league_group
            json_data['tag'] = self.war_tag
        
        return json_data
    
    async def load(self):
        if self._loaded_from_db:
            return
        
        query = await self.database.db__clan_war.find_one({'_id':self._id})
        self._loaded_from_db = True
        if not query:
            return
            
        self._found_in_db = True

        self.type = query['type']
        self._state = query['state']
        self.war_tag = query.get('war_tag','')
        
        self.preparation_start_time = pendulum.from_timestamp(query['preparation_start_time'])
        self.start_time = pendulum.from_timestamp(query['start_time'])
        self.end_time = pendulum.from_timestamp(query['end_time'])

        self.team_size = query['team_size']
        self.attacks_per_member = query['attacks_per_member']

        self.clan_1 = await aWarClan(self,json=query['clans'][0])
        self.clan_2 = await aWarClan(self,json=query['clans'][1])
        
        self._league_group = query.get('league_group','')

        self._members = [await aWarPlayer(self,json=member) for member in query['members']]
        self._attacks = [aWarAttack(self,json=attack) for attack in query['attacks']]

        self.is_alliance_war = query['is_alliance_war']

        self._last_save = pendulum.from_timestamp(query.get('last_save',0)) if query.get('last_save',0) > 0 else None

    @classmethod
    async def create_from_api(cls,data:coc.ClanWar,league_group_id:str=None) -> 'aClanWar':
        base_war_id = ''.join(sorted([data.clan.tag,data.opponent.tag])) + str(pendulum.instance(data.preparation_start_time.time).int_timestamp)
        war_id = hashlib.sha256(base_war_id.encode()).hexdigest()

        clan_war = await cls(war_id=war_id)

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

        clan_war.clan_1 = await aWarClan(war=clan_war,data=data.clan)
        clan_war.clan_2 = await aWarClan(war=clan_war,data=data.opponent)

        clan_war._members = [await aWarPlayer(war=clan_war,data=mem) for mem in data.members]
        clan_war._attacks = [aWarAttack(war=clan_war,data=att) for att in data.attacks]

        if clan_war.clan_1.is_alliance_clan or clan_war.clan_2.is_alliance_clan:
            clan_war.is_alliance_war = True
        else:
            clan_war.is_alliance_war = False
        
        return clan_war
    
    def to_json(self):
        return {
            'type': self.type,
            'state': self.state,
            'war_tag': self.war_tag,
            'preparation_start_time': self.preparation_start_time.int_timestamp,
            'start_time': self.start_time.int_timestamp,
            'end_time': self.end_time.int_timestamp,
            'team_size': self.team_size,
            'attacks_per_member': self.attacks_per_member,
            'clans': [self.clan_1.to_json(),self.clan_2.to_json()],
            'members': [m.to_json() for m in self._members],
            'attacks': [a.to_json() for a in self._attacks],
            'is_alliance_war': self.is_alliance_war,
            'last_save': self._last_save.int_timestamp if self._last_save else 0
            }

    async def save_to_database(self):
        self._last_save = pendulum.now()
        self._found_in_db = True
        await self.database.db__clan_war.update_one(
            {'_id':self._id},
            {'$set':self.to_json()},
            upsert=True
            )

    @property
    def do_i_save(self) -> bool:
        now = pendulum.now()
        if not self._found_in_db:
            return True
        if self.state == 'inWar':
            if not self._last_save:
                return True
            if now.int_timestamp - getattr(self._last_save,'int_timestamp',0) > 60:
                return True
        if self.end_time <= pendulum.now() <= self.end_time.add(hours=2):
            return True
        return False
    
    @property
    def state(self) -> WarState:
        try:
            if self.preparation_start_time <= pendulum.now() < self.start_time:
                return WarState.PREPARATION
            elif self.start_time <= pendulum.now() < self.end_time:
                return WarState.INWAR
            elif self.end_time <= pendulum.now():
                return WarState.WAR_ENDED
        except:
            return self._state

    ##################################################
    ##### DATA FORMATTERS
    ##################################################    
    def __str__(self) -> str:
        return f"{self.preparation_start_time.format('DD MMM YYYY')} {self.clan_1.name} vs {self.clan_2.name}"
    
    def __eq__(self, __value: object) -> bool:
        return isinstance(__value, aClanWar) and self.preparation_start_time == __value.preparation_start_time and __value.clan_1.tag in [self.clan_1.tag,self.clan_2.tag] and __value.clan_2.tag in [self.clan_1.tag,self.clan_2.tag]
    
    def __hash__(self):
        return self._id

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

        self.tag = json_data['tag'] if json_data else game_data.tag if game_data else None
        super().__init__(self.tag)
        self.exp_earned = 0

        if json_data:
            self._name = json_data['name']
            self._badge = json_data.get('badge',None)
            self._level = json_data.get('level',None)
            self.stars = json_data['stars']
            self.destruction = json_data['destruction']
            self.average_attack_duration = json_data['average_attack_duration']
            self.exp_earned = json_data.get('exp_earned',0)

            if 'attacks_used' in list(json_data.keys()):
                self.attacks_used = json_data['attacks_used']
            else:
                self.attacks_used = json_data['total_attacks']

        if game_data:
            self._name = game_data.name
            self._badge = game_data.badge.url
            self._level = game_data.level
            self.stars = game_data.stars
            self.destruction = game_data.destruction
            self.average_attack_duration = game_data.average_attack_duration
            self.attacks_used = game_data.attacks_used        

        self.max_stars = self.war.team_size * self.war.attacks_per_member
        self._result = None
    
    def _api_json(self):
        return {
            'tag': self.tag,
            'name': self.name,
            'badgeUrls': {
                'small': self.badge,
                'medium': self.badge,
                'large': self.badge
                },
            'clanLevel': self.level,
            'attacks': self.attacks_used,
            'stars': self.stars,
            'destructionPercentage': self.destruction,
            'members': [m._api_json() for m in self.members]
            }
    
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
    def name(self) -> str:
        return self._name
    @property
    def badge(self) -> int:
        return self._badge    
    @property
    def level(self) -> int:
        return self._level
    
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
                return BasicClan(self.tag).emoji
            else:
                return EmojisClash.CLANWAR    
    @property
    def result(self) -> WarResult:
        if self._result is None or pendulum.now() < self.war.end_time:
            self.compute_result()
        return self._result
    
    @property
    def members(self) -> List['aWarPlayer']:
        return sorted([m for m in self.war.members if m.clan_tag == self.tag],key=lambda x:(x.map_position))
    
    @property
    def attacks(self) -> List['aWarAttack']:
        return sorted([a for a in self.war.attacks if a.attacker.clan_tag == self.tag],key=lambda x:x.order)
    
    @property
    def unused_attacks(self) -> int:
        return sum([player.unused_attacks for player in self.members])
    
    @property
    def defenses(self) -> List['aWarAttack']:
        return sorted([a for a in self.war.attacks if a.defender.clan_tag == self.tag],key=lambda x:x.order)

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

        json_data = kwargs.get('json',None)
        game_data = kwargs.get('data',None)
        clan_tag = kwargs.get('clan_tag',None)

        self.tag = json_data['tag'] if json_data else game_data.tag if game_data else None

        super().__init__(self.tag)        

        if json_data:
            self._name = json_data['name']
            self._town_hall = json_data['town_hall']
            self.map_position = json_data['map_position']

            self.clan_tag = json_data.get('clan_tag',clan_tag)

        if game_data:
            self._name = game_data.name
            self._town_hall = game_data.town_hall
            self.map_position = game_data.map_position
            self.clan_tag = game_data.clan.tag
    
    def _api_json(self):
        json_data = {
            'tag': self.tag,
            'name': self.name,
            'townhallLevel': self.town_hall,
            'mapPosition': self.map_position,
            'opponentAttacks': len(self.defenses),
            }
        if len(self.attacks) > 0:
            json_data['attacks'] = [att._api_json() for att in self.attacks]

        if self.best_opponent_attack:
            json_data['bestOpponentAttack'] = self.best_opponent_attack._api_json()
        return json_data            
    
    def to_json(self):
        return {
            'tag': self.tag,
            'name': self.name,
            'town_hall': self.town_hall,
            'map_position': self.map_position,
            'clan_tag': self.clan_tag
            }
        
    @property
    def name(self) -> str:
        return self._name
    @property
    def town_hall(self) -> int:
        return self._town_hall    
    @property
    def town_hall_level(self) -> int:
        return self._town_hall    
    
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
    __slots__ = [
        'war',
        'order',
        'attacker_tag',
        'defender_tag',
        'stars',
        'destruction',
        'duration',
        'is_fresh_attack',
        '_new_stars',
        '_new_destruction'
        ]
    
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
    
    def _api_json(self):
        return {
            'attackerTag': self.attacker_tag,
            'defenderTag': self.defender_tag,
            'stars': self.stars,
            'destructionPercentage': self.destruction,
            'order': self.order,
            'duration': self.duration,
            }
    
    def to_json(self):
        if self.order:
            return {
                'warID': self.war._id,
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