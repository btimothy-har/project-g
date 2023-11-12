import urllib
import asyncio
import discord

import coc
import hashlib
import pendulum

from typing import *
from mongoengine import *

from redbot.core.utils import AsyncIter

from ...api_client import BotClashClient as client

from ..season.season import aClashSeason
from ..clans.base_clan import BasicClan
from ..players.base_player import BasicPlayer

from .mongo_events import db_RaidWeekend

from ...utils.constants.coc_emojis import EmojisClash
from ...utils.constants.ui_emojis import EmojisUI

bot_client = client()

##################################################
#####
##### DATABASE
#####
##################################################
class aRaidWeekend():
    _cache = {}

    @classmethod
    async def load_all(cls):
        query = db_RaidWeekend.objects().only('raid_id')
        ret = []
        async for raid in AsyncIter(query):
            ret.append(cls(raid_id=raid.raid_id))
        return sorted(ret, key=lambda w:(w.start_time),reverse=True)

    @classmethod
    async def for_player(cls,player_tag:str,season:aClashSeason):
        def _db_query():
            if season:
                query = db_RaidWeekend.objects(
                    Q(members__tag=player_tag) &
                    Q(start_time__gte=season.season_start.int_timestamp) &
                    Q(start_time__lte=season.season_end.int_timestamp)
                    ).only('raid_id')
            else:
                query = db_RaidWeekend.objects(
                    Q(members__tag=player_tag)
                    ).only('raid_id')
            return [q.raid_id for q in query]
        
        raids = await bot_client.run_in_thread(_db_query)
        ret_raids = [cls(raid_id=r) for r in raids]
        return sorted(ret_raids, key=lambda w:(w.start_time),reverse=True)

    @classmethod
    async def for_clan(cls,clan_tag:str,season:aClashSeason):
        def _db_query():
            if season:
                query = db_RaidWeekend.objects(
                    Q(clan_tag=clan_tag) &
                    Q(start_time__gte=season.season_start.int_timestamp) &
                    Q(start_time__lte=season.season_end.int_timestamp)
                    ).only('raid_id')
            else:
                query = db_RaidWeekend.objects(
                    Q(clan_tag=clan_tag)
                    ).only('raid_id')
            return [q.raid_id for q in query]
        
        raids = await bot_client.run_in_thread(_db_query)
        ret_raids = [cls(raid_id=r) for r in raids]
        return sorted(ret_raids, key=lambda w:(w.start_time),reverse=True)

    def __new__(cls,raid_id:str):
        if raid_id not in cls._cache:
            instance = super().__new__(cls)
            instance._is_new = True
            cls._cache[raid_id] = instance
        return cls._cache[raid_id]
    
    def __init__(self,raid_id:str):
        self.raid_id = raid_id

        if self._is_new:
            self._found_in_db = False

            self.clan_tag = ""
            self.clan_name = ""
            self.clan_badge = ""
            self.clan_level = 0

            self.starting_trophies = 0
            self.ending_trophies = 0

            self.is_alliance_raid = False

            self.state = ""
            self.start_time = None
            self.end_time = None
            self.total_loot = 0
            self.attack_count = 0
            self.destroyed_district_count = 0

            self.offensive_reward = 0
            self.defensive_reward = 0

            self.attack_log = []
            self.defense_log = []
            
            self.members = []

            self._last_save = None

            try:
                raid_data = db_RaidWeekend.objects.get(raid_id=raid_id).to_mongo().to_dict()
            except DoesNotExist:
                pass
            else:
                self._found_in_db = True
                self.clan_tag = raid_data['clan_tag']
                self.clan_name = raid_data['clan_name']
                self.clan_badge = raid_data['clan_badge']
                self.clan_level = raid_data['clan_level']

                self.starting_trophies = raid_data['starting_trophies']
                self.ending_trophies = raid_data['ending_trophies']

                self.is_alliance_raid = raid_data['is_alliance_raid']

                self.state = raid_data['state']
                self.start_time = pendulum.from_timestamp(raid_data['start_time'])
                self.end_time = pendulum.from_timestamp(raid_data['end_time'])
                self.total_loot = raid_data['total_loot']
                self.attack_count = raid_data['attack_count']
                self.destroyed_district_count = raid_data['destroyed_district_count']

                self.offensive_reward = raid_data['offensive_reward']
                self.defensive_reward = raid_data['defensive_reward']

                self.attack_log = [aRaidClan(self,json=a) for a in raid_data['attack_log']]
                self.defense_log = [aRaidClan(self,json=a) for a in raid_data['defense_log']]
                
                self.members = [aRaidMember(self,json=m) for m in raid_data['members']]

                self._last_save = pendulum.from_timestamp(raid_data.get('last_save',0)) if raid_data.get('last_save',0) > 0 else None
    
    @classmethod
    async def create_from_api(cls,clan:BasicClan,data:coc.RaidLogEntry) -> 'aRaidWeekend':
        base_raid_id = clan.tag + str(pendulum.instance(data.start_time.time).int_timestamp)
        raid_id = hashlib.sha256(base_raid_id.encode()).hexdigest()

        raid_weekend = cls(raid_id=raid_id)
            
        raid_weekend.clan_tag = clan.tag
        raid_weekend.clan_name = clan.name
        raid_weekend.clan_badge = clan.badge
        raid_weekend.clan_level = clan.level

        raid_weekend.is_alliance_raid = clan.is_alliance_clan

        raid_weekend.state = data.state
        raid_weekend.start_time = pendulum.instance(data.start_time.time)
        raid_weekend.end_time = pendulum.instance(data.end_time.time)
        raid_weekend.total_loot = data.total_loot
        raid_weekend.attack_count = data.attack_count
        raid_weekend.destroyed_district_count = data.destroyed_district_count
        raid_weekend.offensive_reward = data.offensive_reward
        raid_weekend.defensive_reward = data.defensive_reward

        raid_weekend.attack_log = [aRaidClan(raid_weekend,data=attack) for attack in data.attack_log]
        raid_weekend.defense_log = [aRaidClan(raid_weekend,data=defe) for defe in data.defense_log]

        raid_weekend.members = [aRaidMember(raid_weekend,data=member) for member in data.members]

        if raid_weekend.do_i_save:
            await raid_weekend.save_to_database()
        
        return raid_weekend
    
    async def save_to_database(self):
        def _db_save():
            db_raid = db_RaidWeekend(
                raid_id = self.raid_id,
                clan_tag = self.clan_tag,
                clan_name = self.clan_name,
                clan_badge = self.clan_badge,
                clan_level = self.clan_level,
                starting_trophies = self.starting_trophies,
                ending_trophies = self.ending_trophies,
                is_alliance_raid = self.is_alliance_raid,
                state = self.state,
                start_time = self.start_time.int_timestamp,
                end_time = self.end_time.int_timestamp,
                total_loot = self.total_loot,
                attack_count = self.attack_count,
                destroyed_district_count = self.destroyed_district_count,
                offensive_reward = self.offensive_reward,
                defensive_reward = self.defensive_reward,
                attack_log = [r.to_json() for r in self.attack_log],
                defense_log = [r.to_json() for r in self.defense_log],
                members = [m.to_json() for m in self.members],
                last_save = timestamp.int_timestamp
                )
            db_raid.save()
            return db_raid
        
        timestamp = pendulum.now()
        db_raid = await bot_client.run_in_thread(_db_save)
        self._last_save = timestamp
        self._found_in_db = True
        return db_raid

    @property
    def do_i_save(self):
        now = pendulum.now()
        if not self._found_in_db:
            return True
        if self.state == 'ongoing':
            if self._last_save is None:
                return True
            if now.int_timestamp - getattr(self._last_save,'int_timestamp',0) > 60:
                return True
        if self.end_time <= pendulum.now() <= self.end_time.add(hours=2):
            return True
        return False

    ##################################################
    ### DATA FORMATTERS
    ##################################################
    def __str__(self) -> str:
        return f"{self.clan_name} Capital Raid {self.start_time.format('DD MMM YYYY')}"
    
    def __eq__(self, __value: object) -> bool:
        return isinstance(__value, aRaidWeekend) and self.clan_tag == __value.clan_tag and self.start_time == __value.start_time
    
    def __hash__(self):
        return self.raid_id
    
    ##################################################
    ### DATA HELPERS
    ##################################################
    @property
    def offense_raids_completed(self) -> int:
        return len([a for a in self.attack_log if a.destroyed_district_count == a.district_count])
    
    @property
    def defense_raids_completed(self) -> int:
        return len([a for a in self.defense_log if a.destroyed_district_count == a.district_count])
    
    def get_member(self,tag) -> ['aRaidMember']:
        find_member = [rm for rm in self.members if rm.tag == tag]
        if len(find_member) == 0:
            return None
        else:
            return find_member[0]

class aRaidClan(BasicClan):
    def __init__(self,raid_entry,**kwargs):
        self.raid = raid_entry

        json = kwargs.get('json',None)
        game = kwargs.get('data',None)

        if json:
            self.tag = json['tag']
            self._name = json['name']
            self._badge = json.get('badge',None)
            self._level = json.get('level',0)
            self.attack_count = json['attack_count']
            self.district_count = json['district_count']
            self.destroyed_district_count = json['districts_destroyed']
            self.districts = [aRaidDistrict(self.raid,self,json=district) for district in json['districts']]
            self.attacks = [aRaidAttack(self.raid,self,json=attack) for attack in json.get('attacks',[])]

        if game:
            self.tag = game.tag
            self._name = game.name
            self._badge = game.badge.url
            self._level = game.level
            self.attack_count = game.attack_count
            self.district_count = game.district_count
            self.destroyed_district_count = game.destroyed_district_count
            self.districts = [aRaidDistrict(self.raid,self,data=district) for district in game.districts]
            self.attacks = [aRaidAttack(self.raid, self, data=attack) for district in game.districts for attack in district.attacks]
        
        super().__init__(self.tag)
    
    @property
    def name(self) -> str:
        return self._name

    @property
    def badge(self) -> str:
        return self._badge

    @property
    def level(self) -> int:
        return self._level
    
    def to_json(self):
        return {
            'tag': self.tag,
            'name': self.name,
            'badge': self.badge,
            'level': self.level,
            'attack_count': self.attack_count,
            'district_count': self.district_count,
            'districts_destroyed': self.destroyed_district_count,
            'districts': [d.to_json() for d in self.districts],
            'attacks': [a.to_json() for a in self.attacks]
            }
    
    def get_district(self,district_id) -> ['aRaidDistrict']:
        find_district = [rd for rd in self.districts if rd.id == district_id]
        if len(find_district) == 0:
            return None
        else:
            return find_district[0]

class aRaidDistrict():
    def __init__(self,raid_entry,raid_clan,**kwargs):
        self.raid = raid_entry
        self.clan = raid_clan

        json_data = kwargs.get('json',None)
        game_data = kwargs.get('data',None)

        if json_data:
            self.id = json_data['id']
            self.name = json_data['name']
            self.hall_level = json_data['hall_level']
            self.destruction = json_data['destruction']
            self.attack_count = json_data['attack_count']
            self.looted = json_data['resources_looted']
        if game_data:
            data = game_data
            self.id = data.id
            self.name = data.name

            self.hall_level = data.hall_level
            self.destruction = data.destruction
            self.attack_count = data.attack_count
            self.looted = data.looted

    def to_json(self):
        return {
            'id': self.id,
            'name': self.name,
            'hall_level': self.hall_level,
            'destruction': self.destruction,
            'attack_count': self.attack_count,
            'resources_looted': self.looted
            }
        
    @property
    def attacks(self) -> List['aRaidAttack']:
        return [attack for attack in self.clan.attacks if self.id == attack.district_id]    

class aRaidAttack():
    def __init__(self,raid_entry,raid_clan,**kwargs):
        self.raid = raid_entry
        self.clan = raid_clan

        json_data = kwargs.get('json',None)
        game_data = kwargs.get('data',None)

        if json_data:
            self.clan_tag = json_data['raid_clan']
            self.district_id = json_data['district']
            self.attacker_tag = json_data['attacker_tag']
            self.attacker_name = json_data['attacker_name']
            self.stars = json_data.get('stars',0)
            self.destruction = json_data['destruction']
        if game_data:
            data = game_data
            self.clan_tag = data.raid_clan.tag
            self.district_id = data.district.id
            self.attacker_tag = data.attacker_tag
            self.attacker_name = data.attacker_name
            self.stars = data.stars
            self.destruction = data.destruction

        self._new_stars = None
        self._new_destruction = None
    
    def to_json(self):
        return {
            'raid_clan': self.clan_tag,
            'district': self.district_id,
            'attacker_tag': self.attacker_tag,
            'attacker_name': self.attacker_name,
            'stars': self.stars,
            'destruction': self.destruction
            }
    
    @property
    def district(self) -> ['aRaidDistrict']:
        return self.clan.get_district(self.district_id)
    
    @property
    def attacker(self) -> ['aRaidMember']:
        return self.raid.get_member(self.attacker_tag)
    
    @property
    def new_stars(self) -> int:
        if self._new_stars is None or pendulum.now() < self.raid.end_time:
            self.compute_stats()
        return self._new_stars
    
    @property
    def new_destruction(self) -> int:
        if self._new_destruction is None or pendulum.now() < self.raid.end_time:
            self.compute_stats()
        return self._new_destruction

    def compute_stats(self):
        base_stars = 0
        base_destruction = 0
        all_attacks = sorted(self.district.attacks,key=lambda x: (x.stars,x.destruction))
        
        for attack in all_attacks:
            if attack == self:
                break

            if attack.stars > base_stars:
                base_stars = attack.stars
            if attack.destruction > base_destruction:
                base_destruction = attack.destruction
            
        self._new_stars = max(0,self.stars - base_stars)
        self._new_destruction = max(0,self.destruction - base_destruction)

class aRaidMember(BasicPlayer):
    def __init__(self,raid_entry,**kwargs):
        self.raid = raid_entry

        json_data = kwargs.get('json',None)
        game_data = kwargs.get('data',None)

        if json_data:
            self.tag = json_data['tag']
            self._name = json_data['name']
            self.attack_count = json_data['attack_count']
            self.capital_resources_looted = json_data['resources_looted']
        if game_data:
            data = game_data
            self.tag = data.tag
            self._name = data.name
            self.attack_count = data.attack_count
            self.capital_resources_looted = data.capital_resources_looted

        self.medals_earned = (self.raid.offensive_reward * self.attack_count) + self.raid.defensive_reward
        self._attacks = None

        super().__init__(self.tag)
    
    @property
    def name(self) -> str:
        return self._name
    
    def to_json(self) -> dict:
        return {
            'tag': self.tag,
            'name': self.name,
            'attack_count': self.attack_count,
            'resources_looted': self.capital_resources_looted,
            }
        
    @property
    def attacks(self) -> List[aRaidAttack]:
        if self._attacks is None or pendulum.now() < self.raid.end_time:
            self._attacks = []
            for offense_clan in self.raid.attack_log:
                self._attacks.extend([a for a in offense_clan.attacks if a.attacker_tag == self.tag])        
        return sorted(self._attacks, key=lambda x:(x.clan.tag,x.district_id,x.stars,x.destruction),reverse=True)