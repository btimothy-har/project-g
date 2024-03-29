import coc
import logging
import asyncio
import pendulum

from typing import *
from collections import defaultdict

from .war_attack import bWarAttack

from ...client.db_client import MotorClient
from ..season.season import aClashSeason
from ..players.base_player import BasicPlayer

from ...utils.constants.coc_constants import MultiplayerLeagues, WarState, CWLLeagueGroups, EmojisTownHall

LOG = logging.getLogger("coc.main")

class bWarPlayer(coc.ClanWarMember,BasicPlayer):
    def __init__(self,**kwargs):

        self._name = None 
        self._town_hall = None

        kwargs['attack_cls'] = bWarAttack
        

        coc.ClanWarMember.__init__(self,**kwargs)
        BasicPlayer.__init__(self,self.tag)
    
    async def load(self):
        await BasicPlayer.load(self)
        
    @property
    def name(self) -> str:
        return self._name
    @name.setter
    def name(self,value:str):
        self._name = value
    @property
    def town_hall(self) -> int:
        return self._town_hall
    @town_hall.setter
    def town_hall(self,value:int):
        self._town_hall = value
    @property
    def town_hall_level(self) -> int:
        return self.town_hall
    
    @property
    def attacks(self) -> List[bWarAttack]:
        return super().attacks
    @property
    def defenses(self) -> List[bWarAttack]:
        return super().defenses
    @property
    def best_opponent_attack(self) -> bWarAttack:
        return super().best_opponent_attack
    
    @property
    def unused_attacks(self) -> int:
        return self.war.attacks_per_member - len(self.attacks)
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
    def opponent(self) -> 'bWarPlayer':
        return self.war.get_opponent(self.clan.tag)

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
    
##################################################
#####
##### WAR LEAGUE PLAYER
#####
##################################################
class bWarLeaguePlayer(coc.ClanWarLeagueClanMember,BasicPlayer,MotorClient):
    _locks = defaultdict(asyncio.Lock)

    @classmethod
    async def search_by_attributes(cls,season:aClashSeason,**kwargs) -> List[dict]:
        query_doc = {
            '$and':[
                {'season':pendulum.from_format(season.id,'M-YYYY').format('YYYY-MM')}
                ]
            }
        
        if kwargs.get('tag',None):
            query_doc['$and'].append({'tag':kwargs['tag']})
        
        if isinstance(kwargs.get('registered',None),bool):
            query_doc['$and'].append({'registered':True})

        if kwargs.get('discord_user',None):
            query_doc['$and'].append({'discord_user':kwargs['discord_user']})

        if kwargs.get('roster_clan',None):
            query_doc['$and'].append({'roster_clan':kwargs['roster_clan']})

        if kwargs.get('league_group',0) > 0:
            group_query = {
                '$or':[
                    {'league_group':{"$lte":kwargs['league_group']}},
                    {'league_group':99}
                    ]
                }
            query_doc['$and'].append(group_query)

        return await MotorClient.database.db__war_league_player.find(query_doc).to_list(None)

    def __init__(self,**kwargs):
        self._from_api = kwargs.pop('from_api',True)
        self._season = None

        self._from_data(kwargs.get('data',{}))

        coc.ClanWarLeagueClanMember.__init__(self,**kwargs)
        BasicPlayer.__init__(self,self.tag)

    async def load(self):
        await BasicPlayer.load(self)

        if self._from_api:
            db = await self.database.db__war_league_player.find_one({'_id':self._id})
            if db:
                self._from_data(db)
    
    def _from_data(self,data:dict):
        data_get = data.get
        self._name = data_get('name',None)
        self._town_hall = data_get('townhall',None)
        self._discord_user = data_get('discord_user',None)

        self.league_group = data_get('league_group',0)
        self.roster_clan_tag = data_get('roster_clan',None)
        self.league_clan_tag = data_get('league_clan',None)
        
        self.is_registered = data_get('registered',False)
        self.elo_change = data_get('elo_change',0)

    ##################################################
    ##### DATABASE HELPERS
    ##################################################
    def _api_json(self) -> dict:
        r_json = {
            'tag': self.tag,
            'name': self.name,
            'townHallLevel': self.town_hall,
            'season': pendulum.from_format(self.season.id,'M-YYYY').format('YYYY-MM'),
            }
        return r_json
    
    async def sync_database(self):
        await self.database.db__war_league_player.update_one(
            {'_id':self._id},
            {'$set':self._api_json()},
            upsert=True
            )
    
    ##################################################
    ##### PRIMARY ATTRIBUTES
    ##################################################
    def __str__(self):
        return f"CWL Player {self.name} {self.tag} ({self.season.id})"    
    @property
    def _id(self):
        return {'season':self.season.id,'tag':self.tag}    
    @property
    def _lock(self) -> asyncio.Lock:
        return self._locks[(self.season.id,self.tag)]
    
    @property
    def season(self) -> aClashSeason:
        return aClashSeason(self._season)
    @season.setter
    def season(self,value:str):
        if isinstance(value,aClashSeason):
            self._season = value.id
        else:
            self._season = pendulum.from_format(value,'YYYY-MM').format('M-YYYY')
    
    @property
    def name(self) -> str:
        if not self._name:
            return BasicPlayer(self.tag).name
        return self._name
    @name.setter
    def name(self,value:str):
        self._name = value

    @property
    def town_hall(self) -> str:
        if not self._town_hall:
            return BasicPlayer(self.tag).town_hall
        return self._town_hall
    @town_hall.setter
    def town_hall(self,value:int):
        self._town_hall = value
    @property
    def town_hall_level(self) -> int:
        return self._town_hall
    
    @property
    def discord_user(self) -> int:
        if not self._discord_user:
            return BasicPlayer(self.tag).discord_user
        return self._discord_user
    @discord_user.setter
    def discord_user(self,value:int):
        self._discord_user = value
    
    def assistant_cwl_json(self) -> dict:
        if self.is_registered:
            return {
                'tag': self.tag,
                'name': self.name,
                'townhall': self.town_hall_level,
                'is_registered': self.is_registered,
                'registered_group': CWLLeagueGroups.get_description_no_emoji(self.league_group),
                'roster_clan': self.roster_clan_tag,
                'discord_user': self.discord_user,
                'rank_change': self.elo_change
                }
        else:
            return {
                'tag': self.tag,
                'name': self.name,
                'townhall': self.town_hall_level,
                'is_registered': self.is_registered
                }
    
    ##################################################
    ### REGISTRATION / ROSTERING METHODS
    ##################################################    
    async def register(self,discord_user:int,league_group:int):
        async with self._lock:
            self.is_registered = True
            self.discord_user = discord_user
            self.league_group = league_group            

            api_json = self._api_json()
            api_json['registered'] = self.is_registered
            api_json['league_group'] = self.league_group
            api_json['discord_user'] = self.discord_user

            await self.database.db__war_league_player.update_one(
                {'_id':self._id},
                {'$set':api_json},
                upsert=True
                )
            LOG.info(
                f"{str(self)}: {self.discord_user} registered for CWL in {CWLLeagueGroups.get_description_no_emoji(league_group)} (Group {league_group})."
                )
    
    async def unregister(self):
        async with self._lock:
            self.is_registered = False
            self.roster_clan_tag = None
            self.league_group = 0

            api_json = self._api_json()
            api_json['registered'] = self.is_registered
            api_json['league_group'] = self.league_group
            api_json['roster_clan'] = self.roster_clan_tag

            await self.database.db__war_league_player.update_one(
                {'_id':self._id},
                {'$set':api_json},
                upsert=True
                )
            LOG.info(f"{str(self)} unregistered for CWL.")
    
    async def admin_add(self,league_clan:coc.ClanWarLeagueClan):
        async with self._lock:
            self.is_registered = True
            self.roster_clan_tag = league_clan.tag

            api_json = self._api_json()
            api_json['registered'] = self.is_registered
            api_json['roster_clan'] = self.roster_clan_tag
            api_json['discord_user'] = self.discord_user

            await self.database.db__war_league_player.update_one(
                {'_id':self._id},
                {'$set':api_json},                    
                upsert=True
                )
            LOG.info(
                f"{str(self)} was added by an admin to CWL with {self.roster_clan.name} ({self.roster_clan.tag})."
                )
    
    async def admin_remove(self):            
        async with self._lock:
            self.is_registered = False
            self.roster_clan_tag = None
            self.league_group = 0

            api_json = self._api_json()
            api_json['registered'] = self.is_registered
            api_json['league_group'] = self.league_group
            api_json['roster_clan'] = self.roster_clan_tag

            await self.database.db__war_league_player.update_one(
                {'_id':self.db_id},
                {'$set':api_json},
                upsert=True
                )
            LOG.info(f"{str(self)} was removed by an admin from CWL.")
    
    async def roster_to_clan(self,clan:coc.ClanWarLeagueClan):
        async with self._lock:
            #check current roster: if roster closed, skip
            if self.roster_clan_tag:
                _id = {'season':self.season.id,'tag':self.roster_clan_tag}
                search_clan = await self.database.db__war_league_clan.find_one({'_id':_id})
                if search_clan and search_clan.get('roster_open',True) == False:
                    LOG.info(f"{str(self)}: Current Roster closed for {search_clan.name} ({search_clan.tag}).")
                    return
            
            #check new roster: if roster closed, skip
            _id = {'season':self.season.id,'tag':clan.tag}
            search_clan = await self.database.db__war_league_clan.find_one({'_id':_id})
            if search_clan and search_clan.get('roster_open',True) == False:
                LOG.info(f"{str(self)}: New Roster closed for {clan.name} ({clan.tag}).")
                return
            
            self.roster_clan_tag = clan.tag
            api_json = self._api_json()
            api_json['roster_clan'] = self.roster_clan_tag
            
            await self.database.db__war_league_player.update_one(
                {'_id':self._id},
                {'$set':api_json},
                upsert=True
                )
            LOG.info(
                f"{str(self)} was rostered in CWL: {getattr(clan,'name','No Clan')} {'(' + getattr(clan,'tag','' + ')')}."
                )
    
    async def unroster(self):
        async with self._lock:
            #check current roster: if roster closed, skip            
            if self.roster_clan_tag:
                _id = {'season':self.season.id,'tag':self.roster_clan_tag}
                search_clan = await self.database.db__war_league_clan.find_one({'_id':_id})
                if search_clan and search_clan.get('roster_open',True) == False:
                    return            
                
            self.roster_clan_tag = None
            api_json = self._api_json()
            api_json['roster_clan'] = self.roster_clan_tag
            
            await self.database.db__war_league_player.update_one(
                {'_id':self._id},
                {'$set':api_json},
                upsert=True
                )
            LOG.info(
                f"{str(self)} was removed from CWL."
                )
    
    async def finalize(self,clan:coc.ClanWarLeagueClan):
        async with self._lock:
            self.roster_clan_tag = clan.tag
            
            api_json = self._api_json()
            api_json['roster_clan'] = self.roster_clan_tag
            api_json['registered'] = self.is_registered
            api_json['league_group'] = self.league_group
            api_json['discord_user'] = self.discord_user

            await self.database.db__war_league_player.update_one(
                {'_id':self.db_id},
                {'$set':api_json},
                upsert=True
                )
                        
            LOG.info(
                f"{str(self)}: Roster finalized in {getattr(clan,'name','No Clan')}" + (f" ({getattr(clan,'tag',None)})" if getattr(clan,'tag',None) else '') + "."
                )
    
    ##################################################
    ### ELO METHODS
    ##################################################    
    async def set_elo_change(self,chg:float):
        async with self._lock:
            self.elo_change = chg

            api_json = self._api_json()
            api_json['elo_change'] = self.elo_change

            await self.database.db__war_league_player.update_one(
                {'_id':self.db_id},
                {'$set':api_json},
                upsert=True
                )
            LOG.info(f"{str(self)}: ELO Change: {self.elo_change}")    