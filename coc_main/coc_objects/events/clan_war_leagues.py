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
from redbot.core.utils import AsyncIter

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

class WarLeagueGroup():
    _cache = {}

    def __new__(cls,group_id:str):
        if group_id not in cls._cache:
            instance = super().__new__(cls)
            instance._is_new = True
            cls._cache[group_id] = instance
        return cls._cache[group_id]
    
    def __init__(self,group_id:str):
        if self._is_new:
            self.id = group_id

            if not self._database:
                raise Exception
        
        self._is_new = False

    def __str__(self) -> str:
        return self.season.description + ': ' + ', '.join([f"{clan.name} {clan.tag}" for clan in self.clans])

    def __hash__(self) -> int:
        return self.id
    
    ##################################################
    ### DATABASE ATTRIBUTES
    ##################################################
    @property
    def _database(self) -> Optional[db_WarLeagueGroup]:
        try:
            return db_WarLeagueGroup.objects.get(group_id=self.id)
        except DoesNotExist:
            return None
    
    @cached_property
    def season(self) -> aClashSeason:
        return aClashSeason(self._database.season)
    
    @cached_property
    def league(self) -> str:
        return self._database.league
    
    @cached_property
    def number_of_rounds(self) -> int:
        return self._database.number_of_rounds
    
    @cached_property
    def rounds(self) -> List[List[str]]:
        return self._database.rounds
    
    @cached_property
    def clan_tags(self) -> List[str]:
        return self._database.clans
    
    ##################################################
    ### OBJECT ATTRIBUTES
    ##################################################
    @property
    def clans(self) -> List['WarLeagueClan']:
        return [WarLeagueClan(c,self.season) for c in self._database.clans]
    
    @property
    def wars(self) -> List[aClanWar]:
        return [aClanWar(war_id) for round in self.rounds for war_id in round]
    
    @property
    def state(self) -> str:
        if len([w for w in self.wars if w.state == WarState.INWAR]) > 0:
            return WarState.INWAR
        if len([w for w in self.wars if w.state == WarState.PREPARATION]) > 0:
            return WarState.INWAR
        return WarState.WAR_ENDED        
    
    @property
    def current_round(self) -> int:
        for i, round in enumerate(reversed(self.rounds)):
            if any([aClanWar(war_id).state in self.state for war_id in round]):
                return len(self.rounds) - i
    
    ##################################################
    ### CLASS / STATIC METHODS
    ##################################################
    @classmethod
    def by_season(cls,season:aClashSeason):
        query = db_WarLeagueGroup.objects(season=season.id).only('group_id')
        return [cls(db_group.group_id,season) for db_group in query]
  
    def get_clan(self,tag:str) -> Optional['WarLeagueClan']:
        if tag in self.clan_tags:
            return WarLeagueClan(tag,self.season)
        return None    
    
    def get_round_from_war(self,war) -> Optional[int]:
        return next((i for i,round in enumerate(self.rounds,start=1) if war.war_id in round),None)
    
    def get_round(self,round:int) -> List[aClanWar]:
        return [aClanWar(war_id) for war_id in self.rounds[round-1]]
    
    ##################################################
    ### CREATE FROM API
    ##################################################
    @classmethod
    async def from_api(cls,clan:BasicClan,api_data:coc.ClanWarLeagueGroup):
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
        
        def _save_to_db():
            db_WarLeagueGroup.objects(group_id=group_id).update_one(
                set__season=pendulum.from_format(api_data.season, 'YYYY-MM').format('M-YYYY'),
                set__league=clan.war_league.name,
                set__number_of_rounds=api_data.number_of_rounds,
                set__clans=[clan.tag for clan in api_data.clans],
                set__rounds=war_ids_by_rounds,
                upsert=True
                )
    
        combined = f"{pendulum.from_format(api_data.season, 'YYYY-MM').format('M-YYYY')}-{''.join(sorted([clan.tag for clan in api_data.clans]))}"
        group_id = hashlib.sha256(combined.encode()).hexdigest()

        war_ids_by_rounds = []
        async for round in AsyncIter(api_data.rounds):
            wars_in_round = await asyncio.gather(*(get_league_war(group_id,tag) for tag in round))
            war_ids_by_rounds.append([war.war_id for war in wars_in_round if war is not None])
        
        await bot_client.run_in_thread(_save_to_db)        
        
        group = cls(group_id)
        group.rounds = war_ids_by_rounds

        await asyncio.gather(*(WarLeagueClan.from_api(group,league_clan) for league_clan in api_data.clans))

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
    _cache = {}

    def __new__(cls,clan_tag:str,season:aClashSeason):
        if (clan_tag,season.id) not in cls._cache:
            instance = super().__new__(cls)
            instance._is_new = True
            cls._cache[(clan_tag,season.id)] = instance
        return cls._cache[(clan_tag,season.id)]
    
    def __init__(self,clan_tag:str,season:aClashSeason):
        if self._is_new:
            self.tag = clan_tag
            self.season = season
            self._lock = asyncio.Lock()
            
            super().__init__(tag=self.tag)
    
        self._is_new = False
    
    def __str__(self):
        return f"CWL Clan {self.season.id} {self.name} ({self.tag})"
    
    ##################################################
    ### GLOBAL ATTRIBUTES
    ##################################################
    @property
    def db_id(self) -> dict:
        return {
            'season':self.season.id,
            'tag':self.tag
            }
    
    @property
    def _database(self) -> Optional[db_WarLeagueClan]:
        try:
            return db_WarLeagueClan.objects.get(cwl_id=self.db_id)
        except DoesNotExist:
            return None

    @property
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
    
    @cached_property
    def _name(self) -> str:
        return getattr(self._database,'name',None)

    @property
    def name(self) -> str:
        if self._name:
            return self._name
        return BasicClan(self.tag).name
    
    ##################################################
    ### CWL ATTRIBUTES
    ### These are usable only during CWL
    ##################################################
    @cached_property
    def league_group_id(self) -> str:
        return getattr(self._database,'league_group','')
    
    @property
    def league_group(self) -> Optional[WarLeagueGroup]:
        return WarLeagueGroup(self.league_group_id) if self.league_group_id else None    
    
    @cached_property
    def master_roster_tags(self) -> List[str]:
        return getattr(self._database,'master_roster',[])
    
    @property
    def master_roster(self) -> List['WarLeaguePlayer']:
        return sorted([WarLeaguePlayer(tag,self.season) for tag in self.master_roster_tags],
            key=lambda x:(x.town_hall_level),
            reverse=True)

    @property
    def master_lineup(self) -> Dict[int,int]:
        th_levels = defaultdict(int)
        for player in self.master_roster:
            th_levels[player.town_hall] += 1
        return th_levels
    
    @property
    def master_average_th(self) -> float:
        return round(sum([p.town_hall for p in self.master_roster])/len(self.master_roster),1)
    
    @property
    def league_wars(self) -> List[aClanWar]:
        def pred_clan_wars(war):
            return war.clan_1.tag == self.tag or war.clan_2.tag == self.tag
        if self.league_group:
            clan_wars = [war for war in self.league_group.wars if pred_clan_wars(war)]
            if len(clan_wars) > 0:
                return clan_wars
        return None
    
    @property
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
    
    @property
    def current_round(self) -> Optional[int]:
        if self.current_war:
            for i,round in enumerate(self.league_group.rounds):
                if self.current_war.war_id in round:
                    return i+1        
        return None
    
    @property
    def total_score(self) -> int:
        if self.league_group:
            return sum(war.get_clan(self.tag).stars + (10 if war.get_clan(self.tag).result in ['won'] else 0) for war in self.league_wars)
        return 0
    
    @property
    def total_destruction(self) -> int:
        if self.league_group:
            return round(sum(getattr(member.best_opponent_attack,'destruction',0) for war in self.league_wars for member in war.get_opponent(self.tag).members))
        return 0
    
    ##################################################
    ### CWL SETUP ATTRIBUTES
    ### These are usable during CWL setup
    ##################################################
    @cached_property
    def is_participating(self) -> bool:
        return getattr(self._database,'is_participating',False)
    
    @cached_property
    def roster_open(self) -> bool:
        return getattr(self._database,'roster_open',False)
    
    @cached_property
    def _participant_tags(self) -> List[str]:
        query = db_WarLeaguePlayer.objects(
            (Q(season=self.season.id) & Q(registered=True) & Q(roster_clan=self.tag))
            ).only('tag')
        return [db_player.tag for db_player in query]
    
    @property
    def participant_tags(self) -> List[str]:
        return list(set(self._participant_tags))
    
    @property
    def participants(self) -> List['WarLeaguePlayer']:
        ret_players = [WarLeaguePlayer(tag,self.season) for tag in self.participant_tags]
        
        in_memory = [p for p in WarLeaguePlayer._cache.values() if p.season == self.season and p.roster_clan_tag == self.tag]
        ret_players.extend(in_memory)
        return sorted(list(set(ret_players)), key=lambda x:(x.town_hall_level),reverse=True)
    
    ##################################################
    ### CLAN METHODS
    ##################################################
    async def enable_for_war_league(self):
        def _save_to_db():
            db_WarLeagueClan.objects(cwl_id=self.db_id).update_one(
                set__season=self.season.id,
                set__tag=self.tag,
                set__is_participating=self.is_participating,
                upsert=True
                )
            bot_client.coc_data_log.info(
                f"{str(BasicClan(self.tag))} was activated for {self.season.description} CWL."
                )
        async with self._lock:
            self.is_participating = True
            await bot_client.run_in_thread(_save_to_db)

    async def disable_for_war_league(self):
        def _save_to_db():
            db_WarLeagueClan.objects(cwl_id=self.db_id).update_one(
                set__season=self.season.id,
                set__tag=self.tag,
                set__is_participating=self.is_participating,
                upsert=True
                )
            bot_client.coc_data_log.info(
                f"{str(BasicClan(self.tag))} was removed from {self.season.description} CWL."
                )
        async with self._lock:
            self.is_participating = False
            await bot_client.run_in_thread(_save_to_db)

    async def open_roster(self):
        def _save_to_db():
            db_WarLeagueClan.objects(cwl_id=self.db_id).update_one(
                set__season=self.season.id,
                set__tag=self.tag,
                set__roster_open=self.roster_open,
                upsert=True
                )
            bot_client.coc_data_log.info(
                f"{str(BasicClan(self.tag))} opened roster for {self.season.description} CWL."
                )
        async with self._lock:
            self.roster_open = True
            await bot_client.run_in_thread(_save_to_db)
    
    async def close_roster(self):
        def _save_to_db():
            db_WarLeagueClan.objects(cwl_id=self.db_id).update_one(
                set__season=self.season.id,
                set__tag=self.tag,
                set__roster_open=self.roster_open,
                upsert=True
                )
            bot_client.coc_data_log.info(
                f"{str(BasicClan(self.tag))} closed roster for {self.season.description} CWL."
                )
        async with self._lock:
            self.roster_open = False
            await bot_client.run_in_thread(_save_to_db)
    
    async def reset_roster(self):
        def _query_from_db():
            query = db_WarLeaguePlayer.objects(
                (Q(season=self.season.id) & Q(registered=True) & Q(roster_clan=self.tag))
                ).only('tag')
            return [db_player.tag for db_player in query]
        self._participant_tags = await bot_client.run_in_thread(_query_from_db)

    async def finalize_roster(self):
        await self.close_roster()
        role = self.league_clan_role
        async for m in AsyncIter(role.members):
            await m.remove_roles(role,reason='CWL Roster Finalized')
        await asyncio.gather(*(m.finalize() for m in self.participants))
    
    ##################################################
    ### CREATE FROM API
    ##################################################    
    @classmethod
    async def from_api(cls,league_group:WarLeagueGroup,api_data:coc.ClanWarLeagueClan):
        def _save_to_db():
            db_WarLeagueClan.objects(cwl_id=cwl_id).update_one(
                set__season=league_group.season.id,
                set__tag=api_data.tag,
                set__name=api_data.name,
                set__league_group=league_group.id,
                set__master_roster=[m.tag for m in api_data.members],
                upsert=True
                )
            
        cwl_id = {
            'season':league_group.season.id,
            'tag':api_data.tag
            }
        await bot_client.run_in_thread(_save_to_db)

        await asyncio.gather(*[WarLeaguePlayer.from_api(league_group,api_data.tag,member) for member in api_data.members],return_exceptions=True)
        
        clan = cls(api_data.tag,league_group.season)
        clan.league_group_id = league_group.id
        clan._name = api_data.name
        clan.master_roster_tags = [m.tag for m in api_data.members] 
        return clan

    ##################################################
    ### CLASS QUERIES
    ##################################################
    @classmethod
    async def participating_by_season(cls,season:aClashSeason):
        def _db_query():
            query = db_WarLeagueClan.objects(
                season=season.id,
                is_participating=True
                ).only('tag')
            return [db_clan.tag for db_clan in query]
        
        clan_tags = await bot_client.run_in_thread(_db_query)
        ret_clans = [cls(t,season) for t in clan_tags]

        return sorted(list(set(ret_clans)),
            key=lambda x:(x.level,MultiplayerLeagues.get_index(x.war_league_name)),
            reverse=True)

##################################################
#####
##### WAR LEAGUE CLAN
#####
##################################################
class WarLeaguePlayer(BasicPlayer):
    _cache = {}

    def __new__(cls,player_tag:str,season:aClashSeason):
        if (player_tag,season.id) not in cls._cache:
            instance = super().__new__(cls)
            instance._is_new = True
            cls._cache[(player_tag,season.id)] = instance
        return cls._cache[(player_tag,season.id)]
    
    def __init__(self,player_tag:str,season:aClashSeason):
        if self._is_new:
            self.tag = player_tag
            self.season = season
            self._lock = asyncio.Lock()
            
            super().__init__(tag=self.tag)

        self._is_new = False
    
    def __str__(self):
        return f"CWL {self.season.id} {self.name} {self.tag}"
    
    ##################################################
    ### GLOBAL ATTRIBUTES
    ##################################################
    @property
    def player_str(self):
        return super().__str__()

    @property
    def db_id(self):
        return {
            'season':self.season.id,
            'tag':self.tag
            }
    
    @property
    def _database(self) -> Optional[db_WarLeaguePlayer]:
        try:
            return db_WarLeaguePlayer.objects.get(cwl_id=self.db_id)
        except DoesNotExist:
            return None
    
    @cached_property
    def _name(self) -> str:
        return getattr(self._database,'name',None)

    @property
    def name(self) -> str:
        if self._name:
            return self._name
        return BasicPlayer(self.tag).name
    
    @cached_property
    def _war_league_townhall(self) -> int:
        return getattr(self._database,'townhall',0)
    
    @property
    def town_hall(self) -> int:
        if self._war_league_townhall > 0:
            return self._war_league_townhall
        return BasicPlayer(self.tag).town_hall_level
    
    @property
    def town_hall_level(self) -> int:
        return self.town_hall
    
    @cached_property
    def _war_league_discord_user(self) -> int:
        return getattr(self._database,'discord_user',0)
    
    @property
    def discord_user(self) -> int:
        if self._war_league_discord_user > 0:
            return self._war_league_discord_user
        return BasicPlayer(self.tag).discord_user
    
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
    def league_clan_tag(self) -> Optional[str]:
        league_clan = getattr(self._database,'league_clan','')
        if len(league_clan) > 0:
            return league_clan
        return None
        
    @property
    def league_clan(self):
        return WarLeagueClan(self.league_clan_tag,self.season) if self.league_clan_tag else None
    
    @property
    def current_war(self):
        def pred_current_war(war):
            return war.state == 'inWar' and self.tag in [m.tag for m in war.members]
        active_war = [war for war in self.league_clan.league_wars if pred_current_war(war)]
        return active_war[0] if len(active_war) == 1 else None
    
    @property
    def war_log(self):
        def pred_clan_wars(war):
            return war.get_member(self.tag) and war.state in ['warEnded','inWar']
        if self.league_clan:
            clan_wars = [war for war in self.league_clan.league_wars if pred_clan_wars(war)]
            if len(clan_wars) > 0:
                return sorted(clan_wars,key=lambda war: war.end_time.int_timestamp,reverse=True)
        return None
    
    @property
    def war_stats(self):
        if hasattr(self, '_war_stats') and pendulum.now().int_timestamp - self._war_stats.timestamp.int_timestamp > 10800:
            del self._war_stats
        return self._war_stats
    
    @cached_property
    def _war_stats(self):
        return aClanWarSummary.for_player(
            player_tag=self.tag,
            war_log=self.war_log if self.war_log else []
            )
    
    ##################################################
    ### CWL SET UP ATTRIBUTES
    ### These are usable only during CWL registration
    ##################################################
    @cached_property
    def roster_clan_tag(self) -> Optional[str]:
        roster_clan = getattr(self._database,'roster_clan','')
        if len(roster_clan) > 0:
            return roster_clan
        return None
    
    @property
    def roster_clan(self):
        return WarLeagueClan(self.roster_clan_tag,self.season) if self.roster_clan_tag else None
    
    @cached_property
    def is_registered(self) -> bool:
        return getattr(self._database,'registered',False)
    
    #This is the league group that the player has registered to participate in.
    @cached_property
    def league_group(self) -> int:
        return getattr(self._database,'league_group',0)
    
    ##################################################
    ### PLAYER METHODS
    ##################################################
    async def register(self,discord_user:int,league_group:int):
        def _save_to_db():
            db_WarLeaguePlayer.objects(cwl_id=self.db_id).update_one(
                set__season=self.season.id,
                set__tag=self.tag,
                set__registered=self.is_registered,
                set__discord_user=self._war_league_discord_user,
                set__league_group=self.league_group,
                upsert=True
                )
            bot_client.coc_data_log.info(
                f"{str(BasicPlayer(self.tag))} {self.discord_user} registered for {self.season.description} CWL in {CWLLeagueGroups.get_description_no_emoji(league_group)} (Group {league_group})."
                )
        
        async with self._lock:
            self.is_registered = True
            self._war_league_discord_user = discord_user
            self.league_group = league_group
            await bot_client.run_in_thread(_save_to_db)
    
    async def unregister(self):
        def _save_to_db():
            db_WarLeaguePlayer.objects(cwl_id=self.db_id).update_one(
                set__season=self.season.id,
                set__tag=self.tag,
                set__registered=self.is_registered,
                set__league_group=self.league_group,
                set__roster_clan=self.roster_clan_tag,
                upsert=True
                )
            bot_client.coc_data_log.info(
                f"{str(BasicPlayer(self.tag))} unregistered from {self.season.description} CWL."
                )
        
        async with self._lock:
            if self.roster_clan:
                self.roster_clan._participant_tags.remove(self.tag)
            self.is_registered = False
            self.league_group = 0
            self.roster_clan_tag = None
            await bot_client.run_in_thread(_save_to_db)
    
    async def admin_add(self,league_clan:str):
        def _save_to_db():
            db_WarLeaguePlayer.objects(cwl_id=self.db_id).update_one(
                set__season=self.season.id,
                set__tag=self.tag,
                set__registered=self.is_registered,
                set__roster_clan=self.roster_clan_tag,
                upsert=True
                )
            bot_client.coc_data_log.info(
                f"{str(BasicPlayer(self.tag))} was added by an admin to {self.season.description} CWL with {self.roster_clan.name} ({self.roster_clan.tag})."
                )
            
        async with self._lock:
            self.is_registered = True
            if self.roster_clan:
                try:
                    self.roster_clan._participant_tags.remove(self.tag)
                except ValueError:
                    pass

            self.roster_clan_tag = league_clan
            self.roster_clan._participant_tags.append(self.tag)
            await bot_client.run_in_thread(_save_to_db)
    
    async def admin_remove(self):
        def _save_to_db():
            db_WarLeaguePlayer.objects(cwl_id=self.db_id).update_one(
                set__season=self.season.id,
                set__tag=self.tag,
                set__registered=self.is_registered,
                set__league_group=self.league_group,
                set__roster_clan=self.roster_clan_tag,
                upsert=True
                )
            bot_client.coc_data_log.info(
                f"{str(BasicPlayer(self.tag))} was removed by an admin from {self.season.description} CWL."
                )
            
        async with self._lock:
            if self.roster_clan:
                self.roster_clan._participant_tags.remove(self.tag)

            self.is_registered = False
            self.league_group = 0
            self.roster_clan_tag = None
            await bot_client.run_in_thread(_save_to_db)
    
    async def save_roster_clan(self):
        def _save_to_db():
            db_WarLeaguePlayer.objects(cwl_id=self.db_id).update_one(
                set__season=self.season.id,
                set__tag=self.tag,
                set__roster_clan=self.roster_clan_tag,
                upsert=True
                )
            bot_client.coc_data_log.info(
                f"{str(BasicPlayer(self.tag))} was rostered in {self.season.description} CWL: {self.roster_clan.name} ({self.roster_clan.tag})."
                )
        async with self._lock:
            await bot_client.run_in_thread(_save_to_db)
    
    async def reset_roster_clan(self):
        def _db_query():
            try:
                return db_WarLeaguePlayer.objects.get(cwl_id=self.db_id)
            except DoesNotExist:
                return None
            
        async with self._lock:
            del self.roster_clan_tag
            db = await bot_client.run_in_thread(_db_query)
            self.roster_clan_tag = getattr(db,'roster_clan',None)
    
    async def finalize(self):
        def _save_to_db():
            db_WarLeaguePlayer.objects(cwl_id=self.db_id).update_one(
                set__season=self.season.id,
                set__tag=self.tag,
                set__registered=self.is_registered,
                set__discord_user=self.discord_user,
                set__roster_clan=self.roster_clan_tag,
                set__league_group=self.league_group,
                upsert=True
                )
            bot_client.coc_data_log.info(
                f"{str(BasicPlayer(self.tag))}: {self.season.description} CWL roster has been finalized with {self.roster_clan.name} ({self.roster_clan.tag})."
                )
        
        async with self._lock:
            await bot_client.run_in_thread(_save_to_db)
            cwl_role = self.roster_clan.league_clan_role
            if cwl_role:
                try:
                    member = await bot_client.bot.get_or_fetch_member(cwl_role.guild,self.discord_user)
                except discord.NotFound:
                    pass
                else:
                    await member.add_roles(cwl_role,'CWL Roster Finalized')
    
    ##################################################
    ### CLASS / STATIC METHODS
    ##################################################
    @classmethod
    async def from_api(cls,league_group:WarLeagueGroup,clan_tag:str,api_data:coc.ClanWarLeagueClanMember):
        def _save_to_db():
            db_WarLeaguePlayer.objects(cwl_id=cwl_id).update_one(
                set__season=league_group.season.id,
                set__tag=api_data.tag,
                set__name=api_data.name,
                set__townhall=api_data.town_hall,
                set__league_clan=clan_tag,
                upsert=True
                )
            
        cwl_id = {
            'season':league_group.season.id,
            'tag':api_data.tag
            }
        await bot_client.run_in_thread(_save_to_db)

        player = cls(api_data.tag,league_group.season)
        player._name = api_data.name
        player.league_clan_tag = clan_tag
        player._war_league_townhall = api_data.town_hall        
        return player

    ##################################################
    ### CLASS QUERIES
    ##################################################
    @classmethod
    async def get_by_user(cls,season:aClashSeason,user_id:int,only_registered=False):
        def _db_query():
            if only_registered:
                query = db_WarLeaguePlayer.objects(
                    season=season.id,
                    discord_user=user_id,
                    registered=True
                    ).only('tag')
            else:
                query = db_WarLeaguePlayer.objects(
                    season=season.id,
                    discord_user=user_id
                    ).only('tag')
            return [db_player.tag for db_player in query]
        
        qq = await bot_client.run_in_thread(_db_query)
        ret_players = [cls(q,season) for q in qq]
        return sorted(ret_players, key=lambda x:(x.town_hall_level,x.exp_level),reverse=True)
    
    @classmethod
    async def signups_by_group(cls,season:aClashSeason,group:int):
        def _db_query():
            query = db_WarLeaguePlayer.objects(
                (Q(season=season.id) &Q(registered=True) & Q(league_group__gt=0)) & (Q(league_group__lte=group) | Q(league_group=99))
                ).only('tag')
            return [db_player.tag for db_player in query]
        
        qq = await bot_client.run_in_thread(_db_query)
        ret_players = [cls(q,season) for q in qq]
        return sorted(ret_players, key=lambda x:(x.town_hall_level,x.exp_level),reverse=True)

    @classmethod
    async def signups_by_season(cls,season:aClashSeason):
        def _db_query():
            query = db_WarLeaguePlayer.objects(
                season=season.id,
                registered=True
                ).only('tag')
            return [db_player.tag for db_player in query]
        
        qq = await bot_client.run_in_thread(_db_query)
        ret_players = [cls(q,season) for q in qq]
        return sorted(ret_players, key=lambda x:(x.town_hall_level,x.exp_level),reverse=True)