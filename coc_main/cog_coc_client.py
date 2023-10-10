import asyncio
import coc
import discord
import pendulum

from typing import *
from mongoengine import *

from discord.ext import tasks
from redbot.core import commands
from .api_client import BotClashClient, aClashSeason

from .coc_objects.clans.clan import aClan, db_Clan, db_AllianceClan, db_WarLeagueClanSetup
from .coc_objects.players.player import BasicPlayer, aPlayer, db_Player, db_PlayerStats
from .coc_objects.events.clan_war import aClanWar
from .coc_objects.events.clan_war_leagues import WarLeagueGroup
from .coc_objects.events.raid_weekend import aRaidWeekend

from .exceptions import InvalidTag, ClashAPIError, InvalidAbbreviation

from .utils.constants.coc_constants import ClanRanks, MultiplayerLeagues

bot_client = BotClashClient()

############################################################
############################################################
#####
##### CLIENT COG
#####
############################################################
############################################################
class ClashOfClansClient(commands.Cog):
    """
    API Client connector for Clash of Clans

    This cog uses the [coc.py Clash of Clans API wrapper](https://cocpy.readthedocs.io/en/latest/).

    Client parameters are stored RedBot's API framework, using the `[p]set api clashapi` command. The accepted parameters are as follows:
    - `username` : API Username
    - `password` : API Password
    - `keys` : Number of keys to use. Defaults to 1.

    You can register for a Username and Password at https://developer.clashofclans.com.

    This cog also includes support for the Clash DiscordLinks service. If you have a username and password, set them with `[p]set api clashlinks` (parameters: `username` and `password`).

    The use of Clash DiscordLinks is optional.
    """

    __author__ = "bakkutteh"
    __version__ = "2023.10.2"

    def __init__(self,bot):
        self.bot = bot

    def format_help_for_context(self, ctx: commands.Context) -> str:
        context = super().format_help_for_context(ctx)
        return f"{context}\n\nAuthor: {self.__author__}\nVersion: {self.__version__}"
    
    @property
    def client(self) -> BotClashClient:
        return bot_client

    ##################################################
    ### COG LOAD
    ##################################################
    async def cog_load(self):
        war_tasks = asyncio.create_task(aClanWar.load_all())
        raid_tasks = asyncio.create_task(aRaidWeekend.load_all())

        wars = await war_tasks        
        self.client.coc_main_log.info(
            f"Loaded {len(wars):,} Clan Wars from database."
            )
        raids = await raid_tasks
        self.client.coc_main_log.info(
            f"Loaded {len(raids):,} Capital Raids from database."
            )
        
        player_tags = [db.tag for db in db_Player.objects.only('tag')]
        self.client.coc_main_log.info(
            f"Found {len(player_tags):,} Players in database."
            )
        
        clan_tags = [db.tag for db in db_Clan.objects.only('tag')]
        self.client.coc_main_log.info(
            f"Found {len(clan_tags):,} Clans in database."
            )
        
        await asyncio.gather(
            bot_client.player_cache.add_many_to_queue(player_tags),
            bot_client.clan_cache.add_many_to_queue(clan_tags)
            )

    ############################################################
    #####
    ##### LISTENERS
    #####
    ############################################################    
    @commands.Cog.listener("on_shard_connect")
    async def status_on_connect(self, shard_id):
        await self.bot.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.listening,
                name=f"$help!")
                )
    
    @tasks.loop(minutes=10.0)
    async def bot_status_update_loop(self):
        try:
            if self.client.last_status_update != None and (pendulum.now().int_timestamp - self.client.last_status_update.int_timestamp) < 14400:
                return            
            await self.bot.change_presence(
                activity=discord.Activity(
                    type=discord.ActivityType.listening,
                    name=f"$help!")
                    )              
        except Exception:
            #await self.bot.send_to_owners(f"An error occured during the Bot Status Update Loop. Check logs for details.")
            self.client.coc_main_log.exception(
                f"Error in Bot Status Loop"
                )
    
    ############################################################
    #####
    ##### COC: PLAYERS
    #####
    ############################################################
    async def fetch_player(self,tag:str,no_cache=False) -> aPlayer:
        n_tag = coc.utils.correct_tag(tag)
        if not coc.utils.is_valid_tag(tag):
            raise InvalidTag(tag)        
        
        try:
            cached = self.client.player_cache.get(n_tag)
        except:
            cached = None

        if not no_cache and isinstance(cached,aPlayer):
            if pendulum.now().int_timestamp - cached.timestamp.int_timestamp < 3600:
                return cached
        try:
            player = await self.client.coc.get_player(n_tag,cls=aPlayer)
        except coc.NotFound as exc:
            raise InvalidTag(tag) from exc
        except (coc.InvalidArgument,coc.InvalidCredentials,coc.Maintenance,coc.Forbidden,coc.GatewayError) as exc:
            if cached:
                return cached
            else:
                raise ClashAPIError(exc) from exc
        
        await self.client.player_cache.set(player.tag,player)        
        return player

    async def fetch_members_by_season(self,clan:aClan,season:Optional[aClashSeason]=None) -> List[aPlayer]:
        if not season or season.id not in [s.id for s in bot_client.tracked_seasons]:
            season = bot_client.current_season
        
        if season.is_current:
            query = db_Player.objects(
                home_clan=clan.tag,
                is_member=True
                ).only('tag')
        else:
            query = db_PlayerStats.objects(
                home_clan=clan.tag,
                is_member=True,
                season=season.id
                ).only('tag')        
        
        ret_players = await asyncio.gather(*(self.fetch_player(p.tag) for p in query))
        return sorted(ret_players, key=lambda x:(ClanRanks.get_number(x.alliance_rank),x.town_hall_level,x.exp_level),reverse=True)     
    
    ############################################################
    #####
    ##### COC: CLANS
    #####
    ############################################################
    async def fetch_clan(self,tag:str,no_cache:bool=False) -> aClan:
        n_tag = coc.utils.correct_tag(tag)
        if not coc.utils.is_valid_tag(tag):
            raise InvalidTag(tag)

        try:
            cached = self.client.clan_cache.get(n_tag)
        except:
            cached = None
        if no_cache:
            pass        
        elif isinstance(cached,aClan):
            if pendulum.now().int_timestamp - cached.timestamp.int_timestamp < 3600:
                return cached

        try:
            clan = await self.client.coc.get_clan(n_tag,cls=aClan)
        except coc.NotFound as exc:
            raise InvalidTag(tag) from exc
        except (coc.Maintenance,coc.GatewayError) as exc:
            if cached:
                return cached
            else:
                raise ClashAPIError(exc) from exc
            
        await self.client.clan_cache.set(clan.tag,clan)
        return clan

    async def from_clan_abbreviation(self,abbreviation:str) -> aClan:
        try:
            get_clan = db_Clan.objects.get(
                abbreviation=abbreviation.upper()
                )
        except (DoesNotExist,MultipleObjectsReturned):
            raise InvalidAbbreviation(abbreviation.upper())        
        clan = await self.fetch_clan(get_clan.tag)
        return clan
    
    async def get_registered_clans(self) -> List[aClan]:
        c_tags = [c.tag for c in db_Clan.objects(emoji__ne="").only('tag')]
        ret_clans = await asyncio.gather(*(self.fetch_clan(tag) for tag in c_tags))
        return sorted(ret_clans, key=lambda x:(x.level,x.capital_hall),reverse=True)

    async def get_alliance_clans(self) -> List[aClan]:
        c_tags = [c.tag for c in db_AllianceClan.objects()]
        ret_clans = await asyncio.gather(*(self.fetch_clan(tag) for tag in c_tags))
        return sorted(ret_clans, key=lambda x:(x.level,x.max_recruitment_level,x.capital_hall),reverse=True)

    async def get_war_league_clans(self) -> List[aClan]:
        c_tags = [c.tag for c in db_WarLeagueClanSetup.objects(is_active=True).only('tag')]
        ret_clans = await asyncio.gather(*(self.fetch_clan(tag) for tag in c_tags))
        return sorted(ret_clans, key=lambda x:(MultiplayerLeagues.get_index(x.war_league_name),x.level,x.capital_hall),reverse=True)

    ############################################################
    #####
    ##### COC: CLAN WARS
    #####
    ############################################################    
    async def get_clan_war(self,clan:aClan) -> aClanWar:
        api_war = None
        try:
            api_war = await self.client.coc.get_clan_war(clan.tag)
        except coc.PrivateWarLog:
            return None
        except coc.NotFound as exc:
            raise InvalidTag(clan.tag) from exc
        except (coc.Maintenance,coc.GatewayError) as exc:
            raise ClashAPIError(exc) from exc
        
        if not api_war or getattr(api_war,'state','notInWar') == 'notInWar':
            return None        
        clan_war = await aClanWar.create_from_api(api_war)
        return clan_war

    async def get_league_group(self,clan:aClan) -> WarLeagueGroup:
        try:
            api_group = await self.client.coc.get_league_group(clan.tag)
        except coc.NotFound:
            pass
        except (coc.Maintenance,coc.GatewayError) as exc:
            raise ClashAPIError(exc)
        else:
            if api_group and api_group.state in ['preparation','inWar','warEnded'] and pendulum.from_format(api_group.season, 'YYYY-MM').format('M-YYYY') == self.client.current_season.id:
                league_group = await WarLeagueGroup.from_api(clan,api_group)
                return league_group
        return None
    
    ############################################################
    #####
    ##### COC: RAID WEEKEND
    #####
    ############################################################ 
    async def get_raid_weekend(self,clan:aClan) -> aRaidWeekend:
        api_raid = None
        try:
            raidloggen = await self.client.coc.get_raid_log(clan_tag=clan.tag,page=False,limit=1)
        except coc.PrivateWarLog:
            return None
        except coc.NotFound as exc:
            raise InvalidTag(self.tag) from exc
        except (coc.Maintenance,coc.GatewayError) as exc:
            raise ClashAPIError(exc) from exc
        
        if len(raidloggen) == 0:
            return None
        api_raid = raidloggen[0]
        if not api_raid:
            return None        
        raid_weekend = await aRaidWeekend.create_from_api(clan,api_raid)
        return raid_weekend