import hashlib

import asyncio
import coc
import discord
import pendulum

from typing import *
from functools import cached_property
from mongoengine import *

from coc_client.api_client import BotClashClient

from redbot.core.utils import AsyncIter

from ..season.season import aClashSeason
from .clan_war_summary import aSummaryWarStats

from ...utilities.utils import *

from ...constants.coc_constants import *
from ...constants.coc_emojis import *
from ...constants.ui_emojis import *
from ...exceptions import *

##################################################
#####
##### DATABASE
#####
##################################################
class db_WarLeagueGroup(Document):
    group_id = StringField(primary_key=True,required=True)
    season = StringField(default="")
    state = StringField(default="")
    league = StringField(default="")
    number_of_rounds = IntField(default=0)
    rounds = ListField(ListField(StringField()),default=[])
    clans = ListField(StringField(),default=[])

class db_WarLeagueClan(Document):
    #ID using format {'season':'1-2023','tag':'#12345678'}
    cwl_id = DictField(primary_key=True,required=True)
    season = StringField(default="")
    tag = StringField(default="")
    name = StringField(default="")
    is_participating = BooleanField(default=False)
    roster_open = BooleanField(default=True)    
    league_group = StringField(default="") #hash
    master_roster = ListField(StringField(),default=[])
    
    #signup_open = BooleanField(default=False)

class db_WarLeaguePlayer(Document):
    #ID using format {'season':'1-2023','tag':'#12345678'}
    cwl_id = DictField(primary_key=True,required=True)
    season = StringField(default="")
    tag = StringField(default="")
    name = StringField(default="")
    registered = BooleanField(default=False)
    discord_user = IntField(default=0)
    roster_clan = StringField(default="")    
    league_clan = StringField(default="")
    league_group = IntField(default=0)
    townhall = IntField(default=0)

##################################################
#####
##### WAR LEAGUE GROUP
#####
##################################################
class WarLeagueGroup():
    _cache = {}

    @classmethod
    def by_season(cls,season:aClashSeason):
        query = db_WarLeagueGroup.objects(season=season.id).only('group_id')
        return [cls(db_group.group_id,season) for db_group in query]

    def __new__(cls,group_id:str):
        if group_id not in cls._cache:
            instance = super().__new__(cls)
            instance._is_new = True
            cls._cache[group_id] = instance
        return cls._cache[group_id]
    
    def __init__(self,group_id:str):
        if self._is_new:
            self.id = group_id
            self.load()

        self._is_new = False
    
    def load(self):
        self.season = None
        self.state = ""
        self.league = ""
        self.number_of_rounds = 0
        self.rounds = []
        self._clans = []
        try:
            wl_group = db_WarLeagueGroup.objects.get(group_id=self.id).to_mongo().to_dict()
        except DoesNotExist:
            raise
        else:
            self.season = aClashSeason(wl_group.get('season'))
            self.state = wl_group.get('state')
            self.league = wl_group.get('league')
            self.number_of_rounds = wl_group.get('number_of_rounds')
            self.rounds = wl_group.get('rounds')
            self._clans = wl_group.get('clans')
    
    ##################################################
    ### CLASS / STATIC METHODS
    ##################################################
    @classmethod
    async def from_api(cls,api_data:coc.ClanWarLeagueGroup):
        client = BotClashClient()

        combined = f"{pendulum.from_format(api_data.season, 'YYYY-MM').format('M-YYYY')}-{''.join(sorted([clan.tag for clan in api_data.clans]))}"
        group_id = hashlib.sha256(combined.encode()).hexdigest()

        _new_group = False

        try:
            wl_group = db_WarLeagueGroup.objects.get(group_id=group_id)
        except DoesNotExist:
            _new_group = True
            wl_group = db_WarLeagueGroup(group_id=group_id)
        finally:
            if _new_group:
                clan_1 = await client.cog.fetch_clan(api_data.clans[0].tag)
                wl_group.league = clan_1.war_league.name
                wl_group.season = pendulum.from_format(api_data.season, 'YYYY-MM').format('M-YYYY')
                wl_group.number_of_rounds = api_data.number_of_rounds
                wl_group.clans = [clan.tag for clan in api_data.clans]
            
            wl_group.state = api_data.state

            war_tasks = [cls.fetch_wars_in_round(group_id,round) for round in api_data.rounds]
            league_wars_in_round = await asyncio.gather(*war_tasks)
            war_round_ids = []
            for round in league_wars_in_round:
                war_round_ids.append([getattr(war,'war_id','') for war in round if war is not None])                
            wl_group.rounds = war_round_ids            
            wl_group.save()
        
        group = cls(group_id)
        group.load()

        clan_tasks = [WarLeagueClan.from_api(group,league_clan) for league_clan in api_data.clans]
        await asyncio.gather(*clan_tasks)

        if _new_group:
            client.cog.coc_data_log.debug(f"New CWL Group found: {group_id}"
                + f"\nLeague: {group.league}"
                + f"\nClans: {'; '.join([f'{clan.name} {clan.tag}' for clan in group.clans])}"
                )    
        return group

    @staticmethod
    async def fetch_wars_in_round(group_id:str,war_tags:list[str]):
        client = BotClashClient()
        return await asyncio.gather(*(client.cog.get_league_war(group_id,tag) for tag in war_tags))
    
    ##################################################
    ### DATA FORMATTERS
    ##################################################
    def __str__(self) -> str:
        return self.season.description + ': ' + ', '.join([f"{clan.name} {clan.tag}" for clan in self.clans])

    def __hash__(self) -> int:
        return self.id
    
    @property
    def clans(self):
        return sorted([WarLeagueClan(c,self.season) for c in self._clans],key=lambda x: x.clan.level,reverse=True)
    
    @property
    def wars(self):
        client = BotClashClient()
        return [client.cog.get_clan_war_from_id(war_id) for round in self.rounds for war_id in round]
    
    @property
    def current_round(self) -> int:
        client = BotClashClient()
        for i, round in enumerate(reversed(self.rounds)):
            if any([client.cog.get_clan_war_from_id(war_id).state == self.state for war_id in round]):
                return len(self.rounds) - i
  
    def get_clan(self,tag:str):
        if tag in self._clans:
            return WarLeagueClan(tag,self.season)
        return None    
    
    def get_round_from_war(self,war):
        return next((i for i,round in enumerate(self.rounds,start=1) if war.war_id in round),None)
    
    def get_round(self,round:int):
        client = BotClashClient()
        return [client.cog.get_clan_war_from_id(war_id) for war_id in self.rounds[round-1]]
    
    
##################################################
#####
##### WAR LEAGUE CLAN
#####
##################################################
class WarLeagueClan():
    _cache = {}

    @classmethod
    def participating_by_season(cls,season:aClashSeason):
        query = db_WarLeagueClan.objects(season=season.id,is_participating=True).only('tag')
        ret_clans = [cls(db_clan.tag,season) for db_clan in query]
        return sorted(list(set(ret_clans)),
            key=lambda x:(x.clan.level,multiplayer_leagues.index(x.clan.war_league.name)),
            reverse=True)

    def __new__(cls,clan_tag:str,season:aClashSeason):
        if (clan_tag,season.id) not in cls._cache:
            instance = super().__new__(cls)
            instance._is_new = True
            cls._cache[(clan_tag,season.id)] = instance
        return cls._cache[(clan_tag,season.id)]
    
    def __init__(self,clan_tag:str,season:aClashSeason):
        self.client = BotClashClient()
        if self._is_new:
            self.tag = clan_tag
            self.season = season
            self.load()
        
        self.client.cog.clan_cache.add_to_queue(self.tag)
        self._is_new = False
    
    def load(self):
        self._is_participating = False
        self._name = None
        self._roster_open = True
        self._participants = []

        self._league_group = None
        self._master_roster = []
        
        if self.tag == None:
            return
        try:
            db_clan = db_WarLeagueClan.objects.get(cwl_id=self.db_id).to_mongo().to_dict()
        except DoesNotExist:
            pass
        else:
            self._name = db_clan.get('name',None)
            self._is_participating = db_clan.get('is_participating',False)
            self._roster_open = db_clan.get('roster_open',True)
            self._league_group = db_clan.get('league_group',None)
            self._master_roster = db_clan.get('master_roster',[])
    
    async def finalize_roster(self):
        self.roster_open = False
        role = self.clan.cwl_config.role
        async for m in AsyncIter(role.members):
            await m.remove_roles(role,reason='CWL Roster Finalized')
        tasks = [player.finalize() for player in self.participants]
        await asyncio.gather(*tasks,return_exceptions=True)
    
    ##################################################
    ### CLASS / STATIC METHODS
    ##################################################    
    @classmethod
    async def from_api(cls,league_group:WarLeagueGroup,api_data:coc.ClanWarLeagueClan):
        
        client = BotClashClient()
        cwl_id = {'season':league_group.season.id,'tag':api_data.tag}

        await client.cog.fetch_clan(api_data.tag)
    
        try:
            db_clan = db_WarLeagueClan.objects.get(cwl_id=cwl_id)
        except DoesNotExist:
            db_clan = db_WarLeagueClan(cwl_id=cwl_id)
        finally:
            if not db_clan.season:
                db_clan.season = league_group.season.id
            if not db_clan.tag:
                db_clan.tag = api_data.tag
            db_clan.name = api_data.name
            db_clan.league_group = league_group.id
            db_clan.master_roster = [m.tag for m in api_data.members]
            db_clan.save()        
        
        await asyncio.gather(*[WarLeaguePlayer.from_api(league_group,api_data.tag,member) for member in api_data.members],return_exceptions=True)
        
        instance = cls(api_data.tag,league_group.season)
        instance.load()
        return instance

    ##################################################
    ### DATA FORMATTERS
    ##################################################
    @property
    def db_id(self) -> dict:
        return {'season':self.season.id,'tag':self.tag}
    
    @property
    def name(self) -> str:
        name = self._name if self._name else self.clan.name
        if check_rtl(name):
            return '\u200F' + name + '\u200E'
        return name

    ##################################################
    ### OBJECT REFERENCES
    ##################################################
    @property
    def clan(self):        
        return self.client.cog.get_clan(self.tag)
    
    @property
    def league_group(self) -> Optional[WarLeagueGroup]:
        return WarLeagueGroup(self._league_group) if self._league_group else None
    
    @property
    def league(self):
        return self.league_group.league if self.league_group else self.clan.war_league.name
      
    @property
    def participants(self):
        query = db_WarLeaguePlayer.objects(
            (Q(season=self.season.id) & Q(registered=True) & Q(roster_clan=self.tag))
            ).only('tag')
        
        ret_players = [WarLeaguePlayer(db_player.tag,self.season) for db_player in query]       
        
        in_memory = [p for p in WarLeaguePlayer._cache.values() if p.season == self.season and getattr(p.roster_clan,'tag',None) == self.tag]
        ret_players.extend(in_memory)

        return sorted(list(set(ret_players)), key=lambda x:(x.player.town_hall.level,x.player.hero_strength),reverse=True)
    
    @property
    def master_roster(self):
        return sorted([WarLeaguePlayer(tag,self.season) for tag in self._master_roster],key=lambda m: m.town_hall,reverse=True)
    
    @property
    def all_wars(self):
        def pred_clan_wars(war):
            return war.clan_1.tag == self.tag or war.clan_2.tag == self.tag
        if self.league_group:
            clan_wars = [war for war in self.league_group.wars if pred_clan_wars(war)]
            if len(clan_wars) > 0:
                return clan_wars
        return None
    
    @property
    def current_war(self):
        if self.all_wars:
            active_war = [war for war in self.all_wars if war.state == 'inWar']
            if active_war:
                return max(active_war, key=lambda war: war.end_time)
            prep_war = [war for war in self.all_wars if war.state == 'preparation']
            if prep_war:
                return max(prep_war, key=lambda war: war.end_time)
            return max(self.all_wars, key=lambda war: war.end_time)
        return None
    
    @property
    def current_round(self):
        if self.current_war:
            for i,round in enumerate(self.league_group.rounds):
                if self.current_war.war_id in round:
                    return i+1        
        return None
    @property
    def total_score(self):
        if self.league_group:
            return sum(war.get_clan(self.tag).stars + (10 if war.get_clan(self.tag).result in ['won'] else 0) for war in self.all_wars)
        return 0
    @property
    def total_destruction(self):
        if self.league_group:
            return round(sum(getattr(member.best_opponent_attack,'destruction',0) for war in self.all_wars for member in war.get_opponent(self.tag).members))
        return 0        
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
    def war_stats(self):
        if hasattr(self,'_war_stats') and pendulum.now().int_timestamp - self._war_stats.timestamp.int_timestamp > 10800:
            del self._war_stats
        return self._war_stats
    @cached_property
    def _war_stats(self):
        return aSummaryWarStats(
            war_log=self.all_wars if self.all_wars else [],
            clan=self.tag)
    
    ##################################################
    ### ATTRIBUTES
    ##################################################    
    @property
    def is_participating(self) -> bool:
        return self._is_participating
    @is_participating.setter
    def is_participating(self,is_participating:bool):
        self._is_participating = is_participating
        try:
            db_clan = db_WarLeagueClan.objects.get(cwl_id=self.db_id)
        except DoesNotExist:
            db_clan = db_WarLeagueClan(cwl_id=self.db_id)
        db_clan.season = self.season.id
        db_clan.tag = self.tag
        db_clan.is_participating = self._is_participating
        db_clan.save()

    @property
    def roster_open(self) -> bool:
        return self._roster_open
    @roster_open.setter
    def roster_open(self,roster_open:bool):
        self._roster_open = roster_open
        try:
            db_clan = db_WarLeagueClan.objects.get(cwl_id=self.db_id)
        except DoesNotExist:
            db_clan = db_WarLeagueClan(cwl_id=self.db_id)
        db_clan.roster_open = self._roster_open
        db_clan.save()    

##################################################
#####
##### WAR LEAGUE CLAN
#####
##################################################
class WarLeaguePlayer():
    _cache = {}

    @classmethod
    def get_by_user(cls,season:aClashSeason,user_id:int,only_registered=False):
        if only_registered:
            query = db_WarLeaguePlayer.objects(season=season.id,discord_user=user_id,registered=True).only('tag')
        else:
            query = db_WarLeaguePlayer.objects(season=season.id,discord_user=user_id).only('tag')

        ret_players = [cls(db_player.tag,season) for db_player in query]
        return sorted(ret_players, key=lambda x:(x.player.town_hall.level,x.player.exp_level),reverse=True)
    
    @classmethod
    def signups_by_group(cls,season:aClashSeason,group:int):
        query = db_WarLeaguePlayer.objects(
            (Q(season=season.id) &Q(registered=True) & Q(league_group__gt=0)) & (Q(league_group__lte=group) | Q(league_group=99))
            ).only('tag')
        
        ret_players = [cls(db_player.tag,season) for db_player in query]
        return sorted(ret_players, key=lambda x:(x.player.town_hall.level,x.player.exp_level),reverse=True)

    @classmethod
    def signups_by_season(cls,season:aClashSeason):
        query = db_WarLeaguePlayer.objects(season=season.id,registered=True).only('tag')        
        ret_players = [cls(db_player.tag,season) for db_player in query]
        return sorted(ret_players, key=lambda x:(x.player.town_hall.level,x.player.exp_level),reverse=True)

    def __new__(cls,player_tag:str,season:aClashSeason):
        if (player_tag,season.id) not in cls._cache:
            instance = super().__new__(cls)
            instance._is_new = True
            cls._cache[(player_tag,season.id)] = instance
        return cls._cache[(player_tag,season.id)]
    
    def __init__(self,player_tag:str,season:aClashSeason):
        self.client = BotClashClient()
        if self._is_new:
            self.tag = player_tag
            self.season = season            
            self.load()
        
        self.client.cog.player_cache.add_to_queue(self.tag)
        self._is_new = False
    
    def load(self):
        self._is_registered = False
        self._discord_user = 0
        self._league_group = 0
        self._roster_clan = None
        self._name = None
        self._townhall = 0
        self._league_clan = None
        try:
            cwl_player = db_WarLeaguePlayer.objects.get(cwl_id=self.db_id).to_mongo().to_dict()
        except DoesNotExist:
            pass
        else:
            self._is_registered = cwl_player.get('registered',False)
            self._discord_user = cwl_player.get('discord_user',0)
            self._league_group = cwl_player.get('league_group',0)
            self._roster_clan = cwl_player.get('roster_clan',None)
            self._name = cwl_player.get('name',None)
            self._townhall = cwl_player.get('townhall',0)
            self._league_clan = cwl_player.get('league_clan',None)
            if cwl_player.get('season','') != self.season.id or cwl_player.get('tag','') != self.tag:
                self.save()
    
    def save(self):
        try:
            cwl_player = db_WarLeaguePlayer.objects.get(cwl_id=self.db_id)
        except DoesNotExist:
            cwl_player = db_WarLeaguePlayer(cwl_id=self.db_id)
        cwl_player.season = self.season.id
        cwl_player.tag = self.tag
        cwl_player.name = self._name
        cwl_player.registered = self._is_registered
        cwl_player.discord_user = self._discord_user
        cwl_player.league_group = self._league_group
        cwl_player.roster_clan = self._roster_clan
        cwl_player.save()
        self.client.cog.coc_data_log.info(f'Player {self}: attributes saved to database.'
            + f"\nRegistered: {self._is_registered}"
            + f"\nDiscord User: {self._discord_user}"
            + f"\nLeague Group: {self._league_group}"
            + f"\nRoster Clan: {self._roster_clan}"
            )
    
    def signup(self,discord_user:int,league_group:int):
        self._is_registered = True
        self._discord_user = discord_user
        self._league_group = league_group
    
    def unregister(self):
        self._is_registered = False
        self._league_group = 0
        self._roster_clan = None
    
    def admin_add(self,league_clan:str):
        if not self.is_registered:
            self.is_registered = True
            self.discord_user = self.player.discord_user
        self._roster_clan = league_clan
        self.save()
    
    def admin_remove(self):
        self._is_registered = False
        self._league_group = 0
        self._roster_clan = None
        self.save()    
    
    async def finalize(self):
        self.save()
        cwl_role = self.roster_clan.clan.cwl_config.role
        if cwl_role:
            try:
                member = await self.bot.get_or_fetch_member(cwl_role.guild,self.discord_user)
            except discord.NotFound:
                pass
            else:
                await member.add_roles(cwl_role,'CWL Roster Finalized')
    
    ##################################################
    ### CLASS / STATIC METHODS
    ##################################################    
    @classmethod
    async def from_api(cls,league_group:WarLeagueGroup,clan_tag:str,api_data:coc.ClanWarLeagueClanMember):

        client = BotClashClient()
        cwl_id = {'season':league_group.season.id,'tag':api_data.tag}

        player = await client.cog.fetch_player(api_data.tag)
        try:
            cwl_player = db_WarLeaguePlayer.objects.get(cwl_id=cwl_id)
        except DoesNotExist:
            cwl_player = db_WarLeaguePlayer(cwl_id=cwl_id)
        finally:
            cwl_player.name = api_data.name
            if league_group.season.is_current:
                cwl_player.townhall = player.town_hall.level
            else:
                cwl_player.townhall = api_data.town_hall
            cwl_player.league_clan = clan_tag
            cwl_player.save()

        instance = cls(api_data.tag,league_group.season)
        instance.load()
        return instance
    
    ##################################################
    ### DATA FORMATTERS
    ##################################################
    def __str__(self):
        return f"CWL {self.season.id} {self.name} {self.name}"

    @property
    def db_id(self):
        return {'season':self.season.id,'tag':self.tag}

    @property
    def name(self):
        n = self._name if self._name else self.player.name
        if check_rtl(n):
            return '\u200F' + n + '\u200E'
        return n

    ##################################################
    ### OBJECT REFERENCES
    ##################################################
    @property
    def player(self):
        return self.client.cog.get_player(self.tag)
    
    @property
    def town_hall(self):
        if self._townhall > 0:
            return self._townhall 
        else:
            try:
                return self.player.town_hall.level
            except CacheNotReady:
                return 1
            
    @property
    def league(self):
        if self.league_clan:
            return self.league_clan.league
        elif self.roster_clan:
            return self.roster_clan.league
        else:
            return None
        
    @property
    def league_or_roster_clan(self):
        if self.league_clan:
            return self.league_clan
        elif self.roster_clan:
            return self.roster_clan
        else:
            return None
    
    @property
    def league_clan(self):
        return WarLeagueClan(self._league_clan,self.season) if self._league_clan else None
    
    @property
    def current_war(self):
        def pred_current_war(war):
            return war.state == 'inWar' and self.tag in [m.tag for m in war.members]
        active_war = [war for war in self.league_clan.all_wars if pred_current_war(war)]
        return active_war[0] if len(active_war) == 1 else None
    
    @property
    def war_log(self):
        def pred_clan_wars(war):
            return war.get_member(self.tag) and war.state in ['warEnded','inWar']
        if self.league_clan:
            clan_wars = [war for war in self.league_clan.all_wars if pred_clan_wars(war)]
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
        return aSummaryWarStats(war_log=self.war_log,player=self.tag)
    
    ##################################################
    ### ATTRIBUTES
    ##################################################        
    @property
    def is_registered(self):
        return self._is_registered
    @is_registered.setter
    def is_registered(self,value:bool):
        self._is_registered = value

    @property
    def discord_user(self):
        return self._discord_user
    @discord_user.setter
    def discord_user(self,value:int):
        self._discord_user = value
    
    @property
    def league_group(self):
        return self._league_group
    @league_group.setter
    def league_group(self,value:int):
        self._league_group = value

    @property
    def roster_clan(self):
        return WarLeagueClan(self._roster_clan,self.season) if self._roster_clan else None
    @roster_clan.setter
    def roster_clan(self,league_clan=None):
        if not self.roster_clan or getattr(self.roster_clan,'roster_open',True):
            if league_clan:
                self._roster_clan = league_clan.tag
            else:
                self._roster_clan = None