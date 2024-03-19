import coc
import asyncio
import hashlib
import pendulum
import logging

from typing import *

from async_property import AwaitLoader

from ...client.db_client import MotorClient

from .war_attack import bWarAttack
from .war_clans import bWarClan, bWarLeagueClan, bWarPlayer

from ..season.season import aClashSeason

from ...utils.constants.coc_constants import ClanWarType, WarResult, WarState
from ...utils.constants.coc_emojis import EmojisClash
from ...utils.constants.ui_emojis import EmojisUI

LOG = logging.getLogger("coc.main")

##################################################
#####
##### CLAN WAR
#####
##################################################
class bClanWar(coc.ClanWar,MotorClient,AwaitLoader):
    
    @classmethod
    async def _search_by_tag(cls,war_tag:str) -> dict:
        query = await MotorClient.database.db__nclan_war.find_one({'tag':war_tag})
        return query

    @classmethod
    async def _search_for_player(cls,player_tag:str,season:aClashSeason=None) -> dict:
        if season:
            query_doc = {
                '$and': [
                    {'type': ClanWarType.RANDOM},
                    {'preparationStartTimeISO': {
                        '$gte': season.season_start,
                        '$lte': season.season_end
                        }
                    },
                    {'$or': [
                        {'clan.members.tag': player_tag},
                        {'opponent.members.tag': player_tag}
                        ]
                    }
                ]
            }
        else:
            query_doc = {
                '$and': [
                    {'type': ClanWarType.RANDOM},
                    {'$or': [
                        {'clan.members.tag': player_tag},
                        {'opponent.members.tag': player_tag}
                        ]
                    }
                ]
            }
        query = await MotorClient.database.db__nclan_war.find(query_doc).to_list(None)
        return query
    
    @classmethod
    async def _search_for_clan(cls,clan_tag:str,season:aClashSeason=None) -> dict:
        if season:
            query_doc = {
                '$and': [
                    {'type': ClanWarType.RANDOM},
                    {'preparationStartTimeISO': {
                        '$gte': season.season_start,
                        '$lte': season.season_end
                        }
                    },
                    {'$or': [
                        {'clan.tag': clan_tag},
                        {'opponent.tag': clan_tag}
                        ]
                    }
                ]
            }
        else:
            query_doc = {
                '$and': [
                    {'type': ClanWarType.RANDOM},
                    {'$or': [
                        {'clan.tag': clan_tag},
                    {'opponent.tag': clan_tag}
                        ]
                    }
                ]
            }
        query = await MotorClient.database.db__nclan_war.find(query_doc).to_list(None)
        return query
       
    def __init__(self,**kwargs):

        self._preparation_start_time = None
        self._start_time = None
        self._end_time = None

        self.is_alliance_war = kwargs['data'].get('isAllianceWar',False)
        self.league_group = kwargs['data'].get('leagueGroup',None)
        self._type = kwargs['data'].get('type',None)

        kwargs['clan_cls'] = bWarClan
        coc.ClanWar.__init__(self,**kwargs)

    def __str__(self) -> str:
        return f"{self.preparation_start_time.format('DD MMM YYYY')} {self.clan.name} vs {self.opponent.name}"    
    def __eq__(self, __value: object) -> bool:
        return isinstance(__value,bClanWar) and self._id == getattr(__value,'_id')    
    def __hash__(self):
        return self._id
    
    async def load(self):        
        await asyncio.gather(*[self.clan_1.load(),self.clan_2.load()])        
    
    @property
    def _id(self) -> Optional[str]:
        if self.state == 'notInWar':
            return None
        base_war_id = ''.join(sorted([self.clan.tag,self.opponent.tag])) + str(self.preparation_start_time.int_timestamp)
        return hashlib.sha256(base_war_id.encode()).hexdigest()
    
    @property
    def emoji(self) -> str:
        if self.type == ClanWarType.CWL:
            return EmojisClash.WARLEAGUES
        elif self.type == ClanWarType.FRIENDLY:
            return EmojisUI.HANDSHAKE
        else:
            return EmojisClash.CLANWAR
    
    ##################################################
    ##### EXTEND PARENT ATTRIBUTES
    ##################################################    
    @property
    def preparation_start_time(self) -> pendulum.DateTime:
        return self._preparation_start_time
    @preparation_start_time.setter
    def preparation_start_time(self,value:coc.Timestamp):
        if value:
            self._preparation_start_time = pendulum.instance(value.time)    

    @property
    def start_time(self) -> Optional[pendulum.DateTime]:
        return self._start_time
    @start_time.setter
    def start_time(self,value:coc.Timestamp):
        if value:
            self._start_time = pendulum.instance(value.time)

    @property
    def end_time(self) -> Optional[pendulum.DateTime]:
        return self._end_time
    @end_time.setter
    def end_time(self,value:coc.Timestamp):
        if value:
            self._end_time = pendulum.instance(value.time)    

    @property
    def type(self) -> Optional[str]:
        if self._type:
            return self._type
        if self.war_tag:
            return "cwl"
        if not self.start_time:
            return None
        prep_list = [
            5 * 60,
            15 * 60,
            30 * 60,
            60 * 60,
            2 * 60 * 60,
            4 * 60 * 60,
            6 * 60 * 60,
            8 * 60 * 60,
            12 * 60 * 60,
            16 * 60 * 60,
            20 * 60 * 60,
            24 * 60 * 60,
        ]
        if self.start_time.int_timestamp - self.preparation_start_time.int_timestamp in prep_list:
            return "friendly"
        return "random"

    @property
    def clan_1(self) -> 'bWarClan':
        return self.clan
    @property
    def clan_2(self) -> 'bWarClan':
        return self.opponent
    
    @property
    def attacks(self) -> List['bWarAttack']:
        return super().attacks
    
    @property
    def members(self) -> List['bWarPlayer']:
        return super().members
    
    def get_member(self,tag:str) -> Optional['bWarPlayer']:
        return super().get_member(tag)    
    
    def get_member_by(self,**attrs) -> Optional['bWarPlayer']:
        return super().get_member_by(**attrs)
    
    def get_attack(self, attacker_tag: str, defender_tag: str) -> Optional['bWarAttack']:
        return super().get_attack(attacker_tag,defender_tag)
    
    def get_defenses(self,defender_tag:str) -> List['bWarAttack']:
        return super().get_defenses(defender_tag)    

    ##################################################
    ##### EXTEND PARENT ATTRIBUTES
    ##################################################
    def get_clan(self,tag:str) -> 'bWarClan':
        if self.clan.tag == tag:
            return self.clan
        return self.opponent

    def get_opponent(self,tag:str) -> 'bWarClan':
        if self.clan.tag == tag:
            return self.opponent
        return self.clan
    
    ##################################################
    ##### DATABASE METHODS
    ##################################################    
    def _api_json(self):
        json_data = {
            'type': self.type,
            'isAllianceWar': self.is_alliance_war,
            'state': self.state,
            'teamSize': self.team_size,
            'attacksPerMember': self.attacks_per_member,
            'preparationStartTime': self.preparation_start_time.format('YYYYMMDDTHHmmss') + '.000Z',
            'startTime': self.start_time.format('YYYYMMDDTHHmmss') + '.000Z',
            'endTime': self.end_time.format('YYYYMMDDTHHmmss') + '.000Z',
            
            'clan': self.clan_1._api_json(),
            'opponent': self.clan_2._api_json()
            }

        if self.type == ClanWarType.CWL:
            json_data['leagueGroup'] = self.league_group
            json_data['tag'] = self.war_tag        
        return json_data
    
    async def save_to_database(self):
        await self.database.db__nclan_war.update_one(
            {'_id':self._id},
            {'$set':self._api_json()},
            upsert=True
            )

##################################################
#####
##### CLAN WAR LEAGUE GROUP
#####
##################################################
class bWarLeagueGroup(coc.ClanWarLeagueGroup,AwaitLoader,MotorClient):

    @classmethod
    async def get_for_clan_by_season(cls,clan_tag:str,season:aClashSeason) -> dict:
        query = await cls.database.db__nwar_league_group.find_one({
            'clans.tag':clan_tag,
            'season':pendulum.from_format(season.id,'M-YYYY').format('YYYY-MM')
            })
        return query
    
    @classmethod
    async def get_by_war_tag(cls,war_tag:str) -> dict:
        query_doc = {'rounds.warTags': war_tag}
        query = await cls.database.db__nwar_league_group.find_one(query_doc)
        return query

    def __init__(self,**kwargs):        
        kwargs['clan_cls'] = bWarLeagueClan
        self._season = None
        self._league = kwargs['data'].get('league',None)

        coc.ClanWarLeagueGroup.__init__(self,**kwargs)
    
    async def load(self):
        await asyncio.gather(*[clan.load() for clan in self.clans])

    def __str__(self) -> str:
        return self.season.description + ': ' + ', '.join([f"{clan.name} {clan.tag}" for clan in self.clans])
    def __eq__(self, __value: object) -> bool:
        return isinstance(__value,bWarLeagueGroup) and self._id == getattr(__value,'_id')    
    def __hash__(self) -> int:
        return self._id

    @property
    def _id(self) -> str:
        combined = f"{self.season.id}-{''.join(sorted([clan.tag for clan in self.clans]))}"
        return hashlib.sha256(combined.encode()).hexdigest()
    
    @property
    def season(self) -> aClashSeason:
        return aClashSeason(self._season)
    @season.setter
    def season(self,value:str):
        self._season = pendulum.from_format(value,'YYYY-MM').format('M-YYYY')
    
    @property
    def clans(self) -> List[bWarLeagueClan]:
        return super().clans
    
    @property
    def league(self) -> str:
        if self._league:
            return self._league
        return self.clans[-1].league
    
    @property
    def current_round(self) -> int:
        if self.state == 'ended':
            return self.number_of_rounds
        return len(self.rounds) - 1
    
    ##################################################
    ### DATABASE INTERACTIONS
    ##################################################
    def _api_json(self) -> dict:
        raw = self._raw_data
        raw['league'] = self.league
        return raw
    
    async def save_to_database(self):
        await self.database.db__nwar_league_group.update_one(
            {'_id':self._id},
            {'$set':self._api_json()},
            upsert=True
            )
        await asyncio.gather(*[clan.sync_database() for clan in self.clans])
    
    def get_wars_for_clan(self,clan_tag:str,cls:Type[coc.ClanWar]=bClanWar) -> AsyncIterator[bClanWar]:
        return super().get_wars_for_clan(clan_tag,cls)
    
    def get_wars_for_player(self,player_tag:str,cls:Type[coc.ClanWar]=bClanWar) -> AsyncIterator[bClanWar]:
        return super().get_wars_for_player(player_tag,cls)
    
    def get_wars(self,cwl_round:coc.WarRound=coc.WarRound.current_war,cls:Type[coc.ClanWar]=bClanWar) -> AsyncIterator[bClanWar]:
        return super().get_wars(cwl_round,cls)
    
    def get_clan(self,tag:str) -> Optional[bWarLeagueClan]:
        return next((clan for clan in self.clans if clan.tag == tag),None)
    
    def get_round_from_war(self,war:bClanWar) -> Optional[int]:
        return next((i for i,round in enumerate(self.rounds,start=1) if war.war_tag in round),None)
    
    async def compute_group_results(self):
        for clan in self.clans:
            wars = [w async for w in self.get_wars_for_clan(clan.tag)]
            clan.stars = sum([w.clan.stars for w in wars]) + sum([10 if w.clan.result == WarResult.WON else 0 for w in wars])
            clan.destruction = sum([w.clan.destruction for w in wars])
