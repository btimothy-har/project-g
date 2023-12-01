import asyncio
import coc
import discord
import hashlib
import pendulum

from typing import *
from mongoengine import *

from functools import cached_property
from collections import defaultdict
from functools import cached_property
from redbot.core.utils import AsyncIter,bounded_gather
from async_property import AwaitLoader

from ...api_client import BotClashClient as client
from .clan_war import aClanWar
from .war_summary import aClanWarSummary

from ..season.season import aClashSeason
from ..clans.base_clan import BasicClan
from ..players.base_player import BasicPlayer

from .mongo_events import db_WarLeagueGroup, db_WarLeagueClan, db_WarLeaguePlayer

from ...utils.constants.coc_constants import ClanWarType, WarResult, MultiplayerLeagues, WarState, CWLLeagueGroups

from ...exceptions import InvalidTag, ClashAPIError

bot_client = client()

class WarLeagueGroup(AwaitLoader):
    __slots__ = [
        'id',
        'season',
        'league',
        'number_of_rounds',
        'rounds',
        'clans',
        'wars'
        ]
    
    def __init__(self,group_id:str):
        self.id = group_id
        self.season = None
        self.league = None
        self.number_of_rounds = 0
        self.rounds = []
        self.clans = []
    
    async def load(self):
        query = await bot_client.coc_db.db__war_league_group.find_one({'_id':self.id})
        self._is_loaded = True
        if not query:
            return
        self.season = await aClashSeason(query['season'])
        self.league = query['league']
        self.number_of_rounds = query['number_of_rounds']
        self.rounds = query['rounds']

        clan_tags = query['clans']
        self.clans = [await WarLeagueClan(tag,self.season) for tag in clan_tags]
        self.wars = [await aClanWar(war_id) for round in self.rounds for war_id in round]

    def __str__(self) -> str:
        return self.season.description + ': ' + ', '.join([f"{clan.name} {clan.tag}" for clan in self.clans])

    def __hash__(self) -> int:
        return self.id
    
    ##################################################
    ### OBJECT ATTRIBUTES
    ##################################################    
    @cached_property
    def state(self) -> str:
        if len([w for w in self.wars if w.state == WarState.INWAR]) > 0:
            return WarState.INWAR
        if len([w for w in self.wars if w.state == WarState.PREPARATION]) > 0:
            return WarState.INWAR
        return WarState.WAR_ENDED        
    
    @cached_property
    def current_round(self) -> int:
        for i, round in enumerate(reversed(self.rounds)):
            if any([w for w in self.wars if w._id in round]):
                return len(self.rounds) - i
    
    ##################################################
    ### CLASS / STATIC METHODS
    ##################################################
    @classmethod
    async def by_season(cls,season:aClashSeason):
        query = bot_client.coc_db.db__war_league_group.find({'season':season.id},{'_id':1})
        return [await cls(db['_id'],season) async for db in query]
  
    def get_clan(self,tag:str) -> Optional['WarLeagueClan']:
        return next((clan for clan in self.clans if clan.tag == tag),None)
    
    def get_round_from_war(self,war) -> Optional[int]:
        return next((i for i,round in enumerate(self.rounds,start=1) if war._id in round),None)
    
    def get_round(self,round:int) -> List[aClanWar]:
        r = self.rounds[round-1]
        return [w for w in self.wars if w._id in r]
    
    ##################################################
    ### CREATE FROM API
    ##################################################
    @staticmethod
    async def get_league_war(group_id:str,war_tag:str) -> Optional[aClanWar]:
        api_war = None
        try:
            api_war = await bot_client.coc.get_league_war(war_tag)
        except coc.NotFound as exc:
            raise InvalidTag(war_tag) from exc
        except (coc.Maintenance,coc.GatewayError) as exc:
            raise ClashAPIError(exc) from exc
        if api_war.clan and api_war.opponent:
            clan_war = await aClanWar.create_from_api(api_war,league_group_id=group_id)
            return clan_war
        return None
    
    @classmethod
    async def from_api(cls,clan:BasicClan,api_data:coc.ClanWarLeagueGroup):
        season = await aClashSeason(pendulum.from_format(api_data.season, 'YYYY-MM').format('M-YYYY'))

        combined = f"{season.id}-{''.join(sorted([clan.tag for clan in api_data.clans]))}"
        group_id = hashlib.sha256(combined.encode()).hexdigest()

        war_ids_by_rounds = []
        async for round in AsyncIter(api_data.rounds):
            a_iter = AsyncIter(round)
            tasks = [cls.get_league_war(group_id,tag) async for tag in a_iter]
            wars_in_round = await bounded_gather(*tasks,limit=1)
            war_ids_by_rounds.append([war._id for war in wars_in_round if war is not None])
        
        await bot_client.coc_db.db__war_league_group.update_one(
            {'_id':group_id},
            {'$set':{
                'group_id':group_id,
                'season':season.id,
                'league':clan.war_league.name,
                'number_of_rounds':api_data.number_of_rounds,
                'clans':[clan.tag for clan in api_data.clans],
                'rounds':war_ids_by_rounds
                }},
            upsert=True
            )        
        tasks = [WarLeagueClan.from_api(season.id,group_id,clan) async for clan in AsyncIter(api_data.clans)]
        await bounded_gather(*tasks,limit=1)
        
        group = await cls(group_id)
        bot_client.coc_data_log.debug(f"CWL Group: {group_id}"
            + f"\nLeague: {group.league}"
            + f"\nClans: {'; '.join([f'{clan.name} {clan.tag}' for clan in group.clans])}"
            )
        return group
    
##################################################
#####
##### WAR LEAGUE CLAN
#####
##################################################
class WarLeagueClan(BasicClan):
    _locks = defaultdict(asyncio.Lock)

    def __init__(self,clan_tag:str,season:aClashSeason):
        self.tag = clan_tag
        self.season = season            
        super().__init__(tag=self.tag)
    
    def __str__(self):
        return f"CWL Clan {self.name} {self.tag} ({self.season.id})"
    
    @property
    def db_id(self) -> dict:
        return {'season':self.season.id,'tag':self.tag}    
    @property
    def _lock(self) -> asyncio.Lock:
        return self._locks[self.db_id]
    
    async def load(self):
        await BasicClan.load(self)
        db = await bot_client.coc_db.db__war_league_clan.find_one({'_id':self.db_id})

        self._name = db.get('name',super().name) if db else super().name

        self.is_participating = db.get('is_participating',False) if db else False
        self.roster_open = db.get('roster_open',False) if db else False

        league_group_id = db.get('league_group',None) if db else None
        self.league_group = await WarLeagueGroup(league_group_id) if league_group_id else None

        master_roster_tags = db.get('master_roster',[]) if db else []
        self.master_roster = sorted(
            [await WarLeaguePlayer(tag,self.season) async for tag in AsyncIter(master_roster_tags)],
            key=lambda x:(x.town_hall_level),
            reverse=True
            )
    
    ##################################################
    ### GLOBAL ATTRIBUTES
    ##################################################
    @cached_property
    def status(self) -> str:
        if self.league_group:
            return "CWL Started"
        if not self.roster_open:
            return "Roster Finalized"
        if self.is_participating:
            return "Roster Pending"
        return "Not Participating"    
    @property
    def league(self) -> str:
        return self.league_group.league if self.league_group else self.war_league_name
    @property
    def name(self) -> str:
        return self._name
    
    ##################################################
    ### CWL ATTRIBUTES
    ### These are usable only during CWL
    ##################################################    
    @cached_property
    def master_lineup(self) -> Dict[int,int]:
        th_levels = defaultdict(int)
        for player in self.master_roster:
            th_levels[player.town_hall] += 1
        return th_levels
    
    @cached_property
    def master_average_th(self) -> float:
        return round(sum([p.town_hall for p in self.master_roster])/len(self.master_roster),1)
    
    @cached_property
    def league_wars(self) -> List[aClanWar]:
        def pred_clan_wars(war):
            return war.clan_1.tag == self.tag or war.clan_2.tag == self.tag
        if self.league_group:
            clan_wars = [war for war in self.league_group.wars if pred_clan_wars(war)]
            if len(clan_wars) > 0:
                return clan_wars
        return None
    
    @cached_property
    def current_war(self) -> Optional[aClanWar]:
        if self.league_wars:
            active_war = [war for war in self.league_wars if war.state == 'inWar']
            if active_war:
                return max(active_war, key=lambda war: war.end_time)
            prep_war = [war for war in self.league_wars if war.state == 'preparation']
            if prep_war:
                return max(prep_war, key=lambda war: war.end_time)
            return max(self.league_wars, key=lambda war: war.end_time)
        return None
    
    @cached_property
    def current_round(self) -> Optional[int]:
        if self.current_war:
            for i,round in enumerate(self.league_group.rounds):
                if self.current_war._id in round:
                    return i+1
        return None
    
    @cached_property
    def total_score(self) -> int:
        if self.league_group:
            return sum(war.get_clan(self.tag).stars + (10 if war.get_clan(self.tag).result in ['won'] else 0) for war in self.league_wars)
        return 0
    
    @cached_property
    def total_destruction(self) -> int:
        if self.league_group:
            return round(sum(getattr(member.best_opponent_attack,'destruction',0) for war in self.league_wars for member in war.get_opponent(self.tag).members))
        return 0
    
    ##################################################
    ### CWL SETUP ATTRIBUTES
    ### These are usable during CWL setup
    ##################################################
    async def get_participants(self):
        q_doc = {
            'season':self.season.id,
            'registered':True,
            'roster_clan':self.tag
            }
        query = bot_client.coc_db.db__war_league_player.find(q_doc,{'_id':1,'tag':1})
        return [await WarLeaguePlayer(db_player.tag,self.season) async for db_player in AsyncIter(query)]
    
    ##################################################
    ### CLAN METHODS
    ##################################################
    async def enable_for_war_league(self):
        async with self._lock:
            self.is_participating = True
            await bot_client.coc_db.db__war_league_clan.update_one(
                {'_id':self.db_id},
                {'$set': {
                    'season':self.season.id,
                    'tag':self.tag,
                    'is_participating':self.is_participating
                    }
                },
                upsert=True)
            bot_client.coc_data_log.info(f"{str(self)} was activated for CWL.")

    async def disable_for_war_league(self):
        async with self._lock:
            self.is_participating = False
            await bot_client.coc_db.db__war_league_clan.update_one(
                {'_id':self.db_id},
                {'$set': {
                    'season':self.season.id,
                    'tag':self.tag,
                    'is_participating':self.is_participating
                    }
                },
                upsert=True)
            bot_client.coc_data_log.info(f"{str(self)} was removed from CWL.")

    async def open_roster(self):
        async with self._lock:
            self.roster_open = True
            await bot_client.coc_db.db__war_league_clan.update_one(
                {'_id':self.db_id},
                {'$set': {
                    'season':self.season.id,
                    'tag':self.tag,
                    'roster_open':self.roster_open
                    }
                },
                upsert=True)
            bot_client.coc_data_log.info(f"{str(self)} opened roster for CWL.")
    
    async def close_roster(self):
        async with self._lock:
            self.roster_open = False
            await bot_client.coc_db.db__war_league_clan.update_one(
                {'_id':self.db_id},
                {'$set': {
                    'season':self.season.id,
                    'tag':self.tag,
                    'roster_open':self.roster_open
                    }
                },
                upsert=True)
            bot_client.coc_data_log.info(f"{str(self)} opened roster for CWL.")

    async def finalize_roster(self):
        async with self._lock:
            await self.close_roster()
            role = self.league_clan_role
            async for m in AsyncIter(role.members):
                await m.remove_roles(role,reason='CWL Roster Finalized')

            participants = await self.get_participants()
            a_iter = AsyncIter(participants)
            tasks = [m.finalize() async for m in a_iter]
            await bounded_gather(*tasks,limit=1)
    
    ##################################################
    ### CREATE FROM API
    ##################################################    
    @classmethod
    async def from_api(cls,season_id:str,group_id:str,api_data:coc.ClanWarLeagueClan):            
        cwl_id = {'season':season_id,'tag':api_data.tag}
        await bot_client.coc_db.db__war_league_clan.update_one(
            {'_id':cwl_id},
            {'$set':{
                'season':season_id,
                'tag':api_data.tag,
                'name':api_data.name,
                'league_group':group_id,
                'master_roster':[m.tag for m in api_data.members]
                }},
            upsert=True
            )
        a_iter = AsyncIter(api_data.members)
        tasks = [WarLeaguePlayer.from_api(season_id,api_data.tag,member) async for member in a_iter]
        await bounded_gather(*tasks,limit=1)

    ##################################################
    ### CLASS QUERIES
    ##################################################
    @classmethod
    async def participating_by_season(cls,season:aClashSeason):
        q_doc = {
            'season':season.id,
            'is_participating':True
            }        
        query = bot_client.coc_db.db__war_league_clan.find(q_doc,{'_id':1,'tag':1})
        ret_clans = [await cls(t,season) async for t in query]

        return sorted(list(set(ret_clans)),
            key=lambda x:(x.level,MultiplayerLeagues.get_index(x.war_league_name)),
            reverse=True)

##################################################
#####
##### WAR LEAGUE CLAN
#####
##################################################
class WarLeaguePlayer(BasicPlayer):
    _locks = defaultdict(asyncio.Lock)

    def __init__(self,player_tag:str,season:aClashSeason):
        self.tag = player_tag
        self.season = season        
        super().__init__(tag=self.tag)
    
    def __str__(self):
        return f"CWL Player {self.name} {self.tag} ({self.season.id})"

    @property
    def db_id(self):
        return {'season':self.season.id,'tag':self.tag}
    
    @property
    def _lock(self) -> asyncio.Lock:
        return self._locks[self.db_id]
    
    async def load(self):
        await BasicPlayer.load(self)
        db = await bot_client.coc_db.db__war_league_player.find_one({'_id':self.db_id})

        self._name = db.get('name',super().name) if db else super().name
        self._discord_user = db.get('discord_user',super().discord_user) if db else super().discord_user
        self.town_hall = db.get('townhall',super().town_hall_level) if db else super().town_hall_level

        self.is_registered = db.get('registered',False) if db else False
        
        roster_clan_tag = db.get('roster_clan',None) if db else None
        self.roster_clan = await WarLeagueClan(roster_clan_tag,self.season) if roster_clan_tag else None

        league_clan_tag = db.get('league_clan',None) if db else None
        self.league_clan = await WarLeagueClan(league_clan_tag,self.season) if league_clan_tag else None
        
        #This is the league group that the player has registered to participate in.
        self.league_group = db.get('league_group',0) if db else 0
    
    ##################################################
    ### GLOBAL ATTRIBUTES
    ##################################################
    @property
    def name(self) -> str:
        return self._name    
    @property
    def town_hall_level(self) -> int:
        return self.town_hall
    @property
    def discord_user(self) -> int:
        return self._discord_user    
    @property
    def league(self):
        if self.league_clan:
            return self.league_clan.league
        elif self.roster_clan:
            return self.roster_clan.league
        else:
            return None        
    @property
    def league_or_roster_clan(self) -> Optional[WarLeagueClan]:
        if self.league_clan:
            return self.league_clan
        elif self.roster_clan:
            return self.roster_clan
        return None
    
    ##################################################
    ### CWL ATTRIBUTES
    ### These are usable only during CWL
    ##################################################    
    @cached_property
    def current_war(self):
        def pred_current_war(war):
            return war.state == 'inWar' and war.get_member(self.tag)
        active_war = [war for war in self.league_clan.league_wars if pred_current_war(war)]
        return active_war[0] if len(active_war) == 1 else None
    
    @cached_property
    def war_log(self):
        def pred_clan_wars(war):
            return war.get_member(self.tag) and war.state in ['warEnded','inWar']
        if self.league_clan:
            clan_wars = [war for war in self.league_clan.league_wars if pred_clan_wars(war)]
            if len(clan_wars) > 0:
                return sorted(clan_wars,key=lambda war: war.end_time.int_timestamp,reverse=True)
        return None
    
    @cached_property
    def war_stats(self):
        return aClanWarSummary.for_player(
            player_tag=self.tag,
            war_log=self.war_log if self.war_log else []
            )
    
    ##################################################
    ### PLAYER METHODS
    ##################################################
    async def register(self,discord_user:int,league_group:int):
        async with self._lock:
            self.is_registered = True
            self.league_group = league_group
            self._discord_user = discord_user

            await bot_client.coc_db.db__war_league_player.update_one(
                {'_id':self.db_id},
                {'$set':{
                    'season':self.season.id,
                    'tag':self.tag,
                    'registered':self.is_registered,
                    'discord_user':self._discord_user,
                    'league_group':self.league_group
                    }},
                upsert=True
                )
            bot_client.coc_data_log.info(
                f"{str(self)}: {self.discord_user} registered for CWL in {CWLLeagueGroups.get_description_no_emoji(league_group)} (Group {league_group})."
                )
    
    async def unregister(self):
        async with self._lock:
            self.is_registered = False
            self.league_group = 0
            self.roster_clan = None

            await bot_client.coc_db.db__war_league_player.update_one(
                {'_id':self.db_id},
                {'$set':{
                    'season':self.season.id,
                    'tag':self.tag,
                    'registered':self.is_registered,
                    'league_group':self.league_group,
                    'roster_clan':getattr(self.roster_clan,'tag',None)
                    }},
                upsert=True
                )
            bot_client.coc_data_log.info(f"{str(self)} unregistered for CWL.")
    
    async def admin_add(self,league_clan:str):
        async with self._lock:
            self.is_registered = True
            self.roster_clan = await WarLeagueClan(league_clan,self.season)

            await bot_client.coc_db.db__war_league_player.update_one(
                {'_id':self.db_id},
                {'$set':{
                    'season':self.season.id,
                    'tag':self.tag,
                    'registered':self.is_registered,
                    'roster_clan':getattr(self.roster_clan,'tag',None)
                    }},
                upsert=True
                )
            bot_client.coc_data_log.info(
                f"{str(self)} was added by an admin to CWL with {self.roster_clan.name} ({self.roster_clan.tag})."
                )
    
    async def admin_remove(self):            
        async with self._lock:
            self.is_registered = False
            self.league_group = 0
            self.roster_clan = None

            await bot_client.coc_db.db__war_league_player.update_one(
                {'_id':self.db_id},
                {'$set':{
                    'season':self.season.id,
                    'tag':self.tag,
                    'registered':self.is_registered,
                    'league_group':self.league_group,
                    'roster_clan':getattr(self.roster_clan,'tag',None)
                    }},
                upsert=True
                )
            bot_client.coc_data_log.info(f"{str(self)} was removed by an admin from CWL.")
    
    async def save_roster_clan(self):
        async with self._lock: 
            await bot_client.coc_db.db__war_league_player.update_one(
                {'_id':self.db_id},
                {'$set':{
                    'season':self.season.id,
                    'tag':self.tag,
                    'roster_clan':getattr(self.roster_clan,'tag',None)
                    }},
                upsert=True
                )
            bot_client.coc_data_log.info(
                f"{str(self)} was rostered in CWL: {self.roster_clan.name} ({self.roster_clan.tag})."
            )
    
    async def finalize(self):        
        async with self._lock:
            await bot_client.coc_db.db__war_league_player.update_one(
                {'_id':self.db_id},
                {'$set':{
                    'season':self.season.id,
                    'tag':self.tag,
                    'registered':self.is_registered,
                    'discord_user':self.discord_user,
                    'roster_clan':getattr(self.roster_clan,'tag',None),
                    'league_group':self.league_group
                    }},
                upsert=True
                )
            cwl_role = self.roster_clan.league_clan_role
            if cwl_role:
                try:
                    member = await bot_client.bot.get_or_fetch_member(cwl_role.guild,self.discord_user)
                except discord.NotFound:
                    pass
                else:
                    await member.add_roles(
                        *[cwl_role],
                        reason='CWL Roster Finalized'
                        )
    
    ##################################################
    ### CLASS / STATIC METHODS
    ##################################################
    @classmethod
    async def from_api(cls,season_id:str,clan_tag:str,api_data:coc.ClanWarLeagueClanMember):            
        cwl_id = {'season':season_id,'tag':api_data.tag}
        await bot_client.coc_db.db__war_league_player.update_one(
            {'_id':cwl_id},
            {'$set':{
                'season':season_id,
                'tag':api_data.tag,
                'name':api_data.name,
                'townhall':api_data.town_hall,
                'league_clan':clan_tag
                }},
            upsert=True
            )

    ##################################################
    ### CLASS QUERIES
    ##################################################
    @classmethod
    async def get_by_user(cls,season:aClashSeason,user_id:int,only_registered=False):
        if only_registered:
            q_doc = {
                'season':season.id,
                'discord_user':user_id,
                'registered':True
                }
        else:
            q_doc = {
                'season':season.id,
                'discord_user':user_id
                }
        query = bot_client.coc_db.db__war_league_player.find(q_doc,{'_id':1,'tag':1})
        ret_players = [await cls(q['tag'],season) async for q in query]
        return sorted(ret_players, key=lambda x:(x.town_hall_level,x.exp_level),reverse=True)
    
    @classmethod
    async def signups_by_group(cls,season:aClashSeason,group:int):
        q_doc = {
            "$and":[
                {"season":season.id},{"registered":True},{"league_group":{"$gt":0}},
                {"$or": [
                    {"league_group":{"$lte":group}},{"league_group":99}
                    ]}
                ]
            }
        query = await bot_client.coc_db.db__war_league_player.find(q_doc,{'_id':1,'tag':1})
        ret_players = [await cls(q['tag'],season) async for q in query]
        return sorted(ret_players, key=lambda x:(x.town_hall_level,x.exp_level),reverse=True)

    @classmethod
    async def signups_by_season(cls,season:aClashSeason):        
        query = await bot_client.coc_db.db__war_league_player.find({'season':season.id,'registered':True},{'_id':1,'tag':1})
        ret_players = [await cls(q['tag'],season) async for q in query]
        return sorted(ret_players, key=lambda x:(x.town_hall_level,x.exp_level),reverse=True)