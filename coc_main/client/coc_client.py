import coc
import logging
import asyncio
import pendulum

import motor.motor_asyncio

from typing import *
from time import process_time
from async_property import AwaitLoader
from coc.ext import discordlinks

from redbot.core.bot import Red

from ..coc_objects.season.season import aClashSeason
from ..coc_objects.players.player import aPlayer
from ..coc_objects.clans.clan import aClan
from ..coc_objects.events.clan_war_v2 import bClanWar, bWarLeagueGroup, bWarLeagueClan
from ..coc_objects.events.war_players import bWarLeaguePlayer
from ..utils.constants.coc_constants import ClanRanks, MultiplayerLeagues

from .throttler import CounterThrottler

LOG = logging.getLogger("coc.http")
LOOP_TRACKER = {
    'player':{},
    'clan':{}
    }
LOOPS_ACTIVE = {
    'player':False,
    'clan':False
    }
LAST_LOOP = {
    'player':None,
    'clan':None
    }
LOOP_RUNTIME = {
    'player':[],
    'clan':[]
    }

LINKS_APPROVED_IDS = [1031240380487831664]

class LinksNotLoggedIn(coc.ClashOfClansException):
    """
    Raised when the DiscordLinks client is not logged in.
    """

class LoginNotSet(coc.ClashOfClansException):
    """
    Raised when the Clash API credentials are not set.
    """

class CacheQueue(asyncio.Queue):
    def __init__(self):
        self.item_set = set()
        super().__init__()

    def __len__(self):
        return self.qsize()
    
    async def put(self,item):
        if item in self.item_set:
            return
        await super().put(item)        
    
    async def get(self):
        item = await super().get()
        self.item_set.discard(item)
        return item

class ClashClient(coc.EventsClient):
    _bot = None

    @classmethod
    async def start(cls,bot:Red,rate_limit:int=30,keys:Optional[List[str]]=None) -> 'ClashClient':
        cls._bot = bot
        if keys is not None and len(keys) >= 1:
            client = cls(
                load_game_data=coc.LoadGameData(always=True),
                throttler=CounterThrottler,
                throttle_limit=rate_limit
                )
            await client.login_with_tokens(*keys)
            LOG.info(f"Logged into Clash of Clans API with {len(keys)} keys.")
            return client
        
        else:
            clashapi_login = await bot.get_shared_api_tokens('clashapi')
            
            if clashapi_login.get("username") is None:
                raise LoginNotSet(f"Clash API Username is not set.")
            if clashapi_login.get("password") is None:
                raise LoginNotSet(f"Clash API Password is not set.")
            
            client = cls(
                key_count=int(clashapi_login.get("keys",1)),
                key_names='project-g',
                load_game_data=coc.LoadGameData(always=True),
                throttler=CounterThrottler,
                throttle_limit=rate_limit
                )            
            await client.login(
                clashapi_login.get("username"),
                clashapi_login.get("password")                
                )
            LOG.info(f"Logged into Clash of Clans API with username {clashapi_login.get('username')}.")
            return client
    
    async def close(self) -> None:
        try:
            await self.links_client.close()
            self._links_client = None
        except LinksNotLoggedIn:
            pass            
        await super().close()        
        LOG.info(f"Logged out of Clash of Clans API.")

    def __init__(self,**options):
        self.maintenance = False
        self._links_client = None

        self._use_discovery = False
        self._player_cache_queue = CacheQueue()
        self._clan_cache_queue = CacheQueue()
    
        super().__init__(**options)
    
    ############################################################
    #####
    ##### PROPERTY HELPERS
    #####
    ############################################################
    @property
    def bot(self) -> Red:
        return self._bot
    @property
    def http_throttler(self) -> CounterThrottler:
        return self.http._HTTPClient__throttle    
    @property
    def links_client(self) -> discordlinks.DiscordLinkClient:
        if not self._links_client:
            raise LinksNotLoggedIn()
        return self._links_client    
    @property
    def coc_db(self) -> motor.motor_asyncio.AsyncIOMotorDatabase:
        cog = self.bot.get_cog("ClashOfClansMain")
        return cog.db_client.database
    
    ############################################################
    #####
    ##### API PERFORMANCE
    #####
    ############################################################    
    @property
    def player_api(self) -> List[float]:
        try:
            a = self.http.stats['/players/{}']
        except KeyError:
            a = []
        return list(a)
    @property
    def player_api_avg(self) -> float:
        return sum(self.player_api) / len(self.player_api) if len(self.player_api) > 0 else 0
    
    @property
    def clan_api(self) -> List[float]:
        try:
            a = self.http.stats['/clans/{}']
        except KeyError:
            a = []
        return list(a)        
    @property
    def clan_api_avg(self) -> float:
        return sum(self.clan_api)/len(self.clan_api) if len(self.clan_api) > 0 else 0
    
    @property
    def api_current_throughput(self) -> Tuple[float, float]:
        nt = process_time()

        diff = nt - self.http_throttler.sent_time
        sent_avg = self.http_throttler.current_sent / diff if self.http_throttler.current_sent > 0 else 0
        
        diff = nt - self.http_throttler.rcvd_time
        rcvd_avg = self.http_throttler.current_rcvd / diff if self.http_throttler.current_rcvd > 0 else 0
        return sent_avg, rcvd_avg
    
    @property
    def rcvd_stats(self) -> Tuple[float, float, float]:
        if len(self.http_throttler.rcvd) == 0:
            return 0,0,0
        avg = sum(self.http_throttler.rcvd)/len(self.http_throttler.rcvd)
        last = list(self.http_throttler.rcvd)[-1]
        maxr = max(self.http_throttler.rcvd)
        return avg, last, maxr
    
    @property
    def sent_stats(self) -> Tuple[float, float, float]:
        if len(self.http_throttler.sent) == 0:
            return 0,0,0
        avg = sum(self.http_throttler.sent)/len(self.http_throttler.sent)
        last = list(self.http_throttler.sent)[-1]
        maxr = max(self.http_throttler.sent)
        return avg, last, maxr
    
    ############################################################
    #####
    ##### PLAYER API
    #####
    ############################################################
    def get_players(self,player_tags:Iterable[str],cls:Type[coc.Player]=None,load_game_data:bool=True,**kwargs) -> AsyncIterator[aPlayer]:
        if self.maintenance:
            raise coc.Maintenance()
        
        if not cls:
            cls = aPlayer
        return super().get_players(
            player_tags=player_tags,
            cls=cls,
            load_game_data=load_game_data,
            **kwargs)

    async def get_player(self,player_tag:str,cls:Type[coc.Player]=None,load_game_data:bool=True,**kwargs) -> aPlayer:
        if not cls:
            cls = aPlayer
        player = await super().get_player(
            player_tag=player_tag,
            cls=cls,
            load_game_data=load_game_data,
            **kwargs)
        
        if isinstance(player,AwaitLoader):
            await player.load()
        
        if self._use_discovery:
            await self._player_cache_queue.put(player.tag)
        return player

    async def get_members_by_season(self,clan:coc.Clan,season:Optional[aClashSeason]=None) -> List[coc.Player]:
        if not season or season.id not in [s.id for s in aClashSeason.tracked()]:
            season = aClashSeason.current()
        
        filter_criteria = {
            'season':season.id,
            'home_clan_tag':clan.tag,
            'is_member':True
            }
        query = self.coc_db.db_player_member_snapshot.find(filter_criteria,{'tag':1})
        tags = [p['tag'] async for p in query]
        ret_players = [p async for p in self.get_players(tags)]
        return sorted(
            ret_players,
            key=lambda x:(ClanRanks.get_number(x.alliance_rank),x.town_hall.level,x.exp_level),
            reverse=True
            )
    
    ############################################################
    #####
    ##### CLAN API
    #####
    ############################################################
    def get_clans(self,tags:Iterable[str],cls:Type[coc.Clan]=None,**kwargs) -> AsyncIterator[aClan]:
        if self.maintenance:
            raise coc.Maintenance()
        
        if not cls:
            cls = aClan
        return super().get_clans(tags=tags,cls=cls,**kwargs)
    
    async def get_clan(self,tag:str,cls:Type[coc.Clan]=None,**kwargs) -> aClan:
        if not cls:
            cls = aClan
        clan = await super().get_clan(tag=tag,cls=cls,**kwargs)
        
        if isinstance(clan,AwaitLoader):
            await clan.load()
        
        if self._use_discovery:
            await self._clan_cache_queue.put(clan.tag)
        return clan

    async def from_clan_abbreviation(self,abbreviation:str) -> aClan:
        if self.maintenance:
            raise coc.Maintenance()
        
        query = await self.coc_db.db__clan.find_one(
            {
                'abbreviation':abbreviation.upper()
                },
            {'_id':1}
            )
        if query:
            clan = await self.get_clan(query['_id'])
            return clan        
        clan = await self.get_clan(abbreviation)
        return clan
    
    async def get_registered_clans(self) -> List[aClan]:
        if self.maintenance:
            raise coc.Maintenance()
        
        filter = {
            "emoji": {
                "$exists": True,
                "$ne": ""
                }
            }
        query = self.coc_db.db__clan.find(filter,{'_id':1})            
        tags = [c['_id'] async for c in query]
        ret_clans = [c async for c in self.get_clans(tags)]
        return sorted(
            ret_clans,
            key=lambda x:(x.level,x.capital_hall),
            reverse=True
            )

    async def get_alliance_clans(self) -> List[aClan]:
        if self.maintenance:
            raise coc.Maintenance()
        
        query = self.coc_db.db__alliance_clan.find({},{'_id':1})
        tags = [c['_id'] async for c in query]
        ret_clans = [c async for c in self.get_clans(tags)]
        return sorted(
            ret_clans,
            key=lambda x:(x.level,x.max_recruitment_level,x.capital_hall),
            reverse=True
            )

    async def get_war_league_clans(self) -> List[aClan]:
        if self.maintenance:
            raise coc.Maintenance()
        
        filter = {
            'is_active':True
            }
        query = self.coc_db.db__war_league_clan_setup.find(filter,{'_id':1})            
        tags = [c['_id'] async for c in query]
        ret_clans = [c async for c in self.get_clans(tags)]
        return sorted(
            ret_clans,
            key=lambda x:(MultiplayerLeagues.get_index(x.war_league_name),x.level,x.capital_hall),
            reverse=True
            )
    
    ############################################################
    #####
    ##### CLAN WARS
    #####
    ############################################################
    async def get_clan_war(self,clan_tag:str,cls:Type[coc.ClanWar]=None,**kwargs) -> bClanWar:
        if not cls:
            cls = bClanWar
        war = await super().get_clan_war(clan_tag=clan_tag,cls=cls,**kwargs)
        if isinstance(war,AwaitLoader):
            await war.load()
        return war

    async def get_current_war(self,clan_tag:str,cwl_round:coc.WarRound=coc.WarRound.current_war,cls:Type[coc.ClanWar]=None,**kwargs) -> Optional[bClanWar]:
        if not cls:
            cls = bClanWar
        war = await super().get_current_war(clan_tag=clan_tag,cwl_round=cwl_round,cls=cls,**kwargs)
        if isinstance(war,AwaitLoader):
            await war.load()
        return war
    
    def get_clan_wars(self,clan_tags:Iterable[str], cls:Type[coc.ClanWar]=None,**kwargs) -> AsyncIterator[bClanWar]:
        if not cls:
            cls = bClanWar
        return super().get_clan_wars(clan_tags=clan_tags,cls=cls,**kwargs)

    def get_current_wars(self,clan_tags:Iterable[str],cls:Type[coc.ClanWar]=coc.ClanWar,**kwargs) -> AsyncIterator[bClanWar]:
        if not cls:
            cls = bClanWar
        return super().get_current_wars(clan_tags=clan_tags,cls=cls,**kwargs)

    async def get_clan_wars_for_player(self,player_tag:str,season:aClashSeason=None,**kwargs) -> List[bClanWar]:
        tag = coc.utils.correct_tag(player_tag)
        query = await bClanWar._search_for_player(player_tag=tag,season=season)
        wars = [bClanWar(data=w,client=self) for w in query]
        await asyncio.gather(*[w.load() for w in wars])
        return sorted(wars,key=lambda w:w.preparation_start_time,reverse=True)
    
    async def get_clan_wars_for_clan(self,clan_tag:str,season:aClashSeason=None,**kwargs) -> List[bClanWar]:
        tag = coc.utils.correct_tag(clan_tag)
        query = await bClanWar._search_for_clan(clan_tag=tag,season=season)
        wars = [bClanWar(data=w,client=self,clan_tag=tag) for w in query]
        await asyncio.gather(*[w.load() for w in wars])
        return sorted(wars,key=lambda w:w.preparation_start_time,reverse=True)
    
    ############################################################
    #####
    ##### CLAN WAR LEAGUES
    #####
    ############################################################
    async def get_league_player(self,player_tag:str,season:aClashSeason,**kwargs) -> Optional[bWarLeaguePlayer]:
        query = await bWarLeaguePlayer.search_by_attributes(season=season,tag=player_tag)
        data = query[0] if query else None
        if data:
            player = await bWarLeaguePlayer(data=data,season=season,client=self,from_api=False)
            return player
        
        if pendulum.now().int_timestamp < season.cwl_end.int_timestamp:
            player = await self.get_player(player_tag)
            data = {
                'tag':player.tag,
                'name':player.name,
                'townHallLevel':player.town_hall.level,
                'season':pendulum.from_format(season.id,'M-YYYY').format('YYYY-MM')
                }
            player = await bWarLeaguePlayer(data=data,season=season,client=self)
            return player
        return None
    
    async def get_league_players(self,season:aClashSeason,**kwargs) -> List[bWarLeaguePlayer]:
        query = await bWarLeaguePlayer.search_by_attributes(season=season,**kwargs)
        return [bWarLeaguePlayer(data=p,season=season,client=self,from_api=False) for p in query]

    async def get_league_clan(self,clan_tag:str,season:aClashSeason,**kwargs) -> Optional[bWarLeagueClan]:
        query = await bWarLeagueClan.search_by_attributes(season=season,tag=clan_tag)
        data = query[0] if query else None
        if data:
            clan = await bWarLeagueClan(data=data,season=season,client=self,from_api=False)
            return clan
        
        if pendulum.now().int_timestamp < season.cwl_end.int_timestamp:
            clan = await self.get_clan(clan_tag)
            data = {
                'tag':clan.tag,
                'name':clan.name,
                'season':pendulum.from_format(season.id,'M-YYYY').format('YYYY-MM'),
                'league':clan.war_league_name,
                'clanLevel':clan.level,
                'badgeUrls':{
                    'small':clan.badge,
                    'medium':clan.badge,
                    'large':clan.badge
                    },
                'members':[]
                }
            clan = await bWarLeagueClan(data=data,season=season,client=self)        
            return clan
        return None
    
    async def get_league_clans(self,season:aClashSeason,**kwargs) -> List[bWarLeagueClan]:
        query = await bWarLeagueClan.search_by_attributes(season=season,**kwargs)
        return [await bWarLeagueClan(data=c,season=season,client=self,from_api=False) for c in query]

    async def get_league_group(self,clan_tag:str,cls:Type[coc.ClanWarLeagueGroup]=None,season:aClashSeason=None,**kwargs) -> bWarLeagueGroup:
        if not season:
            season = aClashSeason.current()
        if not cls:
            cls = bWarLeagueGroup
        
        if season.is_current:
            group = await super().get_league_group(clan_tag=clan_tag,cls=cls,season=season,**kwargs)
            if isinstance(group,AwaitLoader):
                await group.load()
            return group

        else:
            query = await bWarLeagueGroup.get_for_clan_by_season(clan_tag=clan_tag,season=season)
            if query:
                group = cls(data=query,client=self)
                if isinstance(group,AwaitLoader):
                    await group.load()
                return group
            return None
    
    async def get_league_group_from_league_war(self,war_tag:str,cls:Type[coc.ClanWarLeagueGroup]=None,**kwargs) -> Optional[bWarLeagueGroup]:
        if not cls:
            cls = bWarLeagueGroup
        
        query = await bWarLeagueGroup.get_by_war_tag(war_tag=war_tag)
        if query:
            group = cls(data=query,client=self,**kwargs)
            if isinstance(group,AwaitLoader):
                await group.load()
            return group
        return None
    
    async def get_league_war(self,war_tag:str,cls:Type[coc.ClanWar]=None,**kwargs) -> bClanWar:
        if not cls:
            cls = bClanWar
        war = await super().get_league_war(war_tag=war_tag,cls=cls,**kwargs)
        if war.state == 'notInWar':
            query = await bClanWar._search_by_tag(war_tag)
            if query:
                war = cls(data=query,client=self,**kwargs)

        if isinstance(war,AwaitLoader):
            await war.load()
        return war
    
    def get_league_wars(self,war_tags: Iterable[str],clan_tag: str = None,cls:Type[coc.ClanWar]=None,**kwargs) -> AsyncIterator[bClanWar]:
        if not cls:
            cls = bClanWar
        return super().get_league_wars(war_tags=war_tags,clan_tag=clan_tag,cls=cls,**kwargs)
    
    ############################################################
    #####
    ##### DISCORDLINKS
    #####
    ############################################################
    async def discordlinks_login(self):
        if self.bot.user.id not in LINKS_APPROVED_IDS:
            LOG.warning(f"Bot {self.bot.user} is not approved for Clash DiscordLinks. Skipping login.")
            return
        
        discordlinks_login = await self.bot.get_shared_api_tokens("clashlinks")

        if discordlinks_login.get("username") is None:
            LOG.error(f"Clash DiscordLinks Username is not set. Skipping login.")
        if discordlinks_login.get("password") is None:
            LOG.error(f"Clash DiscordLinks Password is not set. Skipping login.")
        try:
            self._links_client = await discordlinks.login(
                discordlinks_login.get("username"),
                discordlinks_login.get("password"))
        except Exception:
            LOG.exception(f"Error logging into Clash DiscordLinks. Skipping login.")
        else:
            LOG.info(f"Logged into Clash DiscordLinks.")

    async def get_linked_players(self,user:int) -> List[str]:
        try:
            get_linked_players = await self.links_client.get_linked_players(user)
        except LinksNotLoggedIn:
            return []
        except:
            LOG.exception(f"Error while retrieving accounts for {user}.")
            raise
        return get_linked_players