import coc
import asyncio
import discord
import hashlib
import pendulum
import logging

from typing import *

from collections import defaultdict
from functools import cached_property
from async_property import AwaitLoader

from .war_attack import bWarAttack
from .war_players import bWarPlayer, bWarLeaguePlayer

from ...client.db_client import MotorClient

from ..season.season import aClashSeason
from ..clans.base_clan import BasicClan
from ..players.base_player import BasicPlayer

from ...utils.constants.coc_constants import ClanWarType, WarResult, WarState
from ...utils.constants.coc_emojis import EmojisClash
from ...utils.constants.ui_emojis import EmojisUI

LOG = logging.getLogger("coc.main")

##################################################
#####
##### WAR CLAN
#####
##################################################
class bWarClan(coc.WarClan,BasicClan):
    def __init__(self,**kwargs):
        self._name = None
        self._badge = None
        self._level = None
        self._result = None

        kwargs['member_cls'] = bWarPlayer
        coc.WarClan.__init__(self,**kwargs)
        BasicClan.__init__(self,self.tag)

    async def load(self):
        await BasicClan.load(self)
        member_load = [m.load() for m in self.members]
        await asyncio.gather(*member_load)
    
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
    def war(self):
        return self._war
    
    ##################################################
    ##### EXTEND PARENT CLASS
    ##################################################    
    @property
    def name(self) -> str:
        return self._name
    @name.setter
    def name(self,value:str):
        self._name = value
    @property
    def badge(self) -> str:
        return self._badge.url
    @badge.setter
    def badge(self,value:coc.Badge):
        self._badge = value   
    @property
    def level(self) -> int:
        return self._level
    @level.setter
    def level(self,value:int):
        self._level = value
    @property
    def members(self) -> List['bWarPlayer']:
        return super().members
    @property
    def attacks(self) -> List['bWarAttack']:
        return super().attacks
    @property
    def defenses(self) -> List['bWarAttack']:
        return super().defenses
    @property
    def unused_attacks(self) -> int:
        return self.total_attacks - self.attacks_used

    ##################################################
    ##### LINEUP ATTRIBUTES
    ##################################################
    @cached_property
    def lineup(self) -> Dict[int,int]:
        th_levels = defaultdict(int)        
        for player in self.members:
            th_levels[player.town_hall] += 1
        return th_levels
    @cached_property
    def available_hits_by_townhall(self) -> Dict[int,int]:
        th_levels = defaultdict(int)        
        for player in self.members:
            if player.unused_attacks > 0:
                th_levels[player.town_hall] += player.unused_attacks
        return th_levels
    @cached_property
    def average_townhall(self) -> float:
        return round(sum([player.town_hall for player in self.members]) / len(self.members),2)
    
    ##################################################
    ##### CLAN RESULT
    ##################################################
    @property
    def result(self) -> str:
        if self._result is None:
            self.compute_result()
        return self._result

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

##################################################
#####
##### CLAN IN CLAN WAR LEAGUE
#####
##################################################
class bWarLeagueClan(coc.ClanWarLeagueClan,BasicClan,MotorClient):
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
        #league
        if kwargs.get('league',None):
            query_doc['$and'].append({'league':kwargs['league']})        
        #is participating
        if isinstance(kwargs.get('participating',None),bool):
            query_doc['$and'].append({'is_participating':kwargs['participating']})        
        #roster open
        if isinstance(kwargs.get('roster_open',None),bool):
            query_doc['$and'].append({'roster_open':kwargs['roster_open']})        
        #league channel
        if kwargs.get('league_channel',None):
            query_doc['$and'].append({'league_channel':kwargs['league_channel']})        
        #league_role
        if kwargs.get('league_role',None):
            query_doc['$and'].append({'league_role':kwargs['league_role']})            

        return await MotorClient.database.db__war_league_clan.find(query_doc).to_list(None)

    def __init__(self,**kwargs):
        kwargs['member_cls'] = bWarLeaguePlayer

        self._from_api = kwargs.get('from_api',True)
        self._season = None
        self._from_data(kwargs.get('data',{}))

        coc.ClanWarLeagueClan.__init__(self,**kwargs)
        BasicClan.__init__(self,self.tag)

        self._iter_members = (
            bWarLeaguePlayer(data=mdata, season=self.season, client=self._client) for mdata in kwargs['data'].get("members", [])
        ) 

    async def load(self):
        await BasicClan.load(self)

        if self._from_api:
            db = await self.database.db__war_league_player.find_one({'_id':self._id})
            if db:
                self._from_data(db)
        
        if self.is_participating:
            query = {
                'season':pendulum.from_format(self.season.id,'M-YYYY').format('YYYY-MM'),
                'roster_clan':self.tag
                }
            find_participants = await self.database.db__war_league_player.find(query).to_list(None)

            if len(find_participants) > 0:
                self._iter_participants = (
                    self._member_cls(data=mdata,season=self.season, client=self._client, from_api=False) for mdata in find_participants
                )
        
        tasks = [m.load() for m in self.members] + [m.load() for m in self.participants]
        await asyncio.gather(*tasks)

    def _from_data(self,data:dict):
        data_get = data.get

        self._name = data_get('name',None)
        self._level = data_get('level',None)
        self._badge = data_get('badge',None)
        self._league = data_get('league',None)

        self.is_participating = data_get('is_participating',False)
        self.roster_open = data_get('roster_open',True) if self.is_participating else data_get('roster_open',False)

        self._league_channel = data_get('league_channel',None)
        self._league_role = data_get('league_role',None)

        self.stars = data_get('stars',0)
        self.destruction = data_get('destruction',0)
    
    ##################################################
    ##### DATABASE HELPERS
    ##################################################    
    def _api_json(self) -> dict:
        r_json = {
            'tag': self.tag,
            'name': self.name,
            'season': pendulum.from_format(self.season.id,'M-YYYY').format('YYYY-MM'),
            'league': self.league,
            'stars': self.stars,
            'destruction': self.destruction,
            'clanLevel': self.level,
            'badgeUrls': {
                'small': self.badge,
                'medium': self.badge,
                'large': self.badge
                },
            'members': [p._api_json() for p in self.master_roster],
            }
        return r_json

    async def sync_database(self):
        await self.database.db__war_league_clan.update_one(
            {'_id':self._id},
            {'$set': self._api_json()},
            upsert=True)
        await asyncio.gather(*[m.sync_database() for m in self.members])
    
    def assistant_json(self) -> dict:
        ret = {
            'tag': self.tag,
            'name': self.name,
            'level': self.level,
            'share_link': self.share_link,
            'season': self.season.description,
            'clan_war_league': self.league,
            'is_participating': self.is_participating,
            'roster_open': self.roster_open
            }
        if self.abbreviation:
            ret['abbreviation'] = self.abbreviation
        return ret
    
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
            return BasicClan(self.tag).name
        return self._name
    @name.setter
    def name(self,value:str):
        self._name = value

    @property
    def level(self) -> str:
        if not self._level:
            return BasicClan(self.tag).level
        return self._level
    @level.setter
    def level(self,value:int):
        self._level = value
    
    @property
    def badge(self) -> int:
        if not self._badge:
            return BasicClan(self.tag).badge
        return self._badge
    @badge.setter
    def badge(self,value:coc.Badge):
        self._badge = value.url
    
    @property
    def league(self):
        if not self._league:
            return BasicClan(self.tag).war_league_name
        return self._league
    @league.setter
    def league(self,value:str):
        self._league = value
    @property
    def war_league_name(self):
        return self.league
    
    @property
    def status(self) -> str:
        if len(self.members):
            return "CWL Started"
        if not self.roster_open:
            return "Roster Finalized"
        if self.is_participating:
            return "Roster Pending"
        return "Not Participating"
    
    @cached_property
    def lineup(self) -> Dict[int,int]:
        th_levels = defaultdict(int)
        if len(self.members) > 0:
            for player in self.members:
                th_levels[player.town_hall] += 1
        else:
            for player in self.participants:
                th_levels[player.town_hall] += 1
        return th_levels
    
    @cached_property
    def average_townhall(self) -> float:
        if len(self.members) > 0:
            return round(sum([player.town_hall for player in self.members]) / len(self.members),2)
        else:
            return round(sum([player.town_hall for player in self.participants]) / len(self.participants),2)
    
    ##################################################
    ### CLAN WAR LEAGUE ATTRIBUTES
    ### These are usable when CWL is active for the clan
    ##################################################
    @property
    def cwl_started(self) -> bool:
        return len(self.members) > 0
    
    @property
    def members(self) -> List[bWarLeaguePlayer]:
        return super().members
    @property
    def master_roster(self) -> List[bWarLeaguePlayer]:
        return super().members
    
    ##################################################
    ### CLAN WAR LEAGUE SETUP ATTRIBUTES
    ### These are usable during CWL setup
    ##################################################
    @cached_property
    def participants(self) -> List[bWarLeaguePlayer]:
        if hasattr(self,'_iter_participants'):
            return list(self._iter_participants)
        return []
    
    @property
    def league_channel(self) -> Optional[discord.TextChannel]:
        if self._league_channel:
            return self.bot.get_channel(self._league_channel)
        return None
    
    @property
    def league_role(self) -> Optional[discord.Role]:
        if self.league_channel and self._league_role:
            return self.league_channel.guild.get_role(self._league_role)
        return None
    
    async def set_league_discord(self,channel:discord.TextChannel,role:discord.Role):
        self._league_channel = channel.id
        self._league_role = role.id
        api_json = self._api_json()
        api_json['league_channel'] = self._league_channel
        api_json['league_role'] = self._league_role

        await self.database.db__war_league_clan.update_one(
            {'_id':self.db_id},
            {'$set': api_json},
            upsert=True
            )
    
    async def enable_for_war_league(self):
        async with self._lock:
            self.is_participating = True
            api_json = self._api_json()
            api_json['is_participating'] = self.is_participating
            await self.database.db__war_league_clan.update_one(
                {'_id':self._id},
                {'$set': api_json},
                upsert=True)
            LOG.info(f"{str(self)} was activated for CWL.")

    async def disable_for_war_league(self):
        async with self._lock:
            self.is_participating = False
            api_json = self._api_json()
            api_json['is_participating'] = self.is_participating

            await self.database.db__war_league_clan.update_one(
                {'_id':self._id},
                {'$set': api_json},
                upsert=True)
            LOG.info(f"{str(self)} was removed from CWL.")

    async def open_roster(self,skip_lock:bool=False):
        if not skip_lock:
            await self._lock.acquire()

        try:
            self.roster_open = True
            api_json = self._api_json()
            api_json['roster_open'] = self.roster_open
            
            await self.database.db__war_league_clan.update_one(
                {'_id':self._id},
                {'$set': api_json},
                upsert=True)
            LOG.info(f"{str(self)} opened roster for CWL.")
        
        except:
            raise

        finally:
            if not skip_lock:
                self._lock.release()
    
    async def close_roster(self,skip_lock:bool=False):
        if not skip_lock:
            await self._lock.acquire()        
        try:
            self.roster_open = False
            api_json = self._api_json()
            api_json['roster_open'] = self.roster_open

            await self.database.db__war_league_clan.update_one(
                {'_id':self.db_id},
                {'$set': api_json},
                upsert=True)
            LOG.info(f"{str(self)} closed roster for CWL.")
        
        except:
            raise
        finally:
            if not skip_lock:
                self._lock.release()

    async def finalize_roster(self) -> bool:
        async with self._lock:
            if not self.roster_open:
                return False
            if len(self.participants) < 15:
                return False
            
            await self.close_roster(skip_lock=True)

            for member in self.participants:
                await member.finalize(self)
            
            cog = self.bot.get_cog("ClanWarLeagues")
            if cog:
                try:
                    await cog.create_clan_channel(self)
                except Exception:
                    LOG.exception(f"Error finalizing CWL Roster for {str(self)}")
                    return False
            return True