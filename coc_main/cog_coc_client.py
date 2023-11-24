import asyncio
import coc
import discord
import pendulum

from typing import *
from mongoengine import *

from collections import deque
from discord.ext import tasks
from redbot.core import commands
from redbot.core.bot import Red
from redbot.core.utils import AsyncIter
from .api_client import BotClashClient, aClashSeason

from .coc_objects.clans.clan import BasicClan, aClan, db_Clan, db_AllianceClan, db_WarLeagueClanSetup
from .coc_objects.players.player import BasicPlayer, aPlayer, db_Player, db_PlayerStats
from .coc_objects.events.clan_war import aClanWar
from .coc_objects.events.clan_war_leagues import WarLeagueGroup
from .coc_objects.events.raid_weekend import aRaidWeekend

from .exceptions import InvalidTag, ClashAPIError, InvalidAbbreviation

from .utils.constants.coc_constants import ClanRanks, MultiplayerLeagues
from .utils.components import clash_embed, DefaultView, DiscordButton, EmojisUI, s_convert_seconds_to_str

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
    API Client Manager for Clash of Clans.

    This cog provides a wrapper for key COC API calls, facilitates the cache/API interaction, and tracks API response time(s).
    """

    __author__ = bot_client.author
    __version__ = bot_client.version

    def __init__(self,bot:Red):
        self.bot = bot
        self.start_task = None

    def format_help_for_context(self, ctx: commands.Context) -> str:
        context = super().format_help_for_context(ctx)
        return f"{context}\n\nAuthor: {self.__author__}\nVersion: {self.__version__}"
    
    @property
    def client(self) -> BotClashClient:
        return bot_client
    
    @property
    def api_maintenance(self) -> bool:
        return bot_client.api_maintenance
    
    @property
    def player_api(self) -> deque:
        return bot_client.player_api
    @property
    def player_api_avg(self) -> float:
        return bot_client.player_api_avg
    
    @property
    def clan_api(self) -> deque:
        return bot_client.clan_api
    @property
    def clan_api_avg(self) -> float:
        return bot_client.clan_api_avg
    
    async def get_player_from_loop(self,tag:str) -> Optional[aPlayer]:
        n_tag = coc.utils.correct_tag(tag)
        task_cog = self.bot.get_cog("ClashOfClansTasks")
        return task_cog.player_loop._cached.get(n_tag,None)
    
    async def get_clan_from_loop(self,tag:str) -> Optional[aClan]:
        n_tag = coc.utils.correct_tag(tag)
        task_cog = self.bot.get_cog("ClashOfClansTasks")
        return task_cog.clan_loop._cached.get(n_tag,None)

    ##################################################
    ### COG LOAD
    ##################################################
    async def cog_load(self):
        async def start_client_cog():
            try:
                while True:
                    if getattr(bot_client,'_api_logged_in',False):
                        break
                    await asyncio.sleep(1)

                war_tasks = asyncio.create_task(aClanWar.load_all())
                raid_tasks = asyncio.create_task(aRaidWeekend.load_all())
                player_tasks = asyncio.create_task(BasicPlayer.load_all())
                clan_tasks = asyncio.create_task(BasicClan.load_all())

                wars = await war_tasks
                self.client.coc_main_log.info(
                    f"Loaded {len(wars):,} Clan Wars from database."
                    )
                raids = await raid_tasks
                self.client.coc_main_log.info(
                    f"Loaded {len(raids):,} Capital Raids from database."
                    )
                
                players = await player_tasks
                self.client.coc_main_log.info(
                    f"Found {len(players):,} Players in database."
                    )
                
                clans = await clan_tasks
                self.client.coc_main_log.info(
                    f"Found {len(clans):,} Clans in database."
                    )
                
                # c_queue_task = asyncio.create_task(bot_client.clan_queue.add_many([c.tag for c in clans]))
                # p_queue_task = asyncio.create_task(bot_client.player_queue.add_many([p.tag for p in players]))
                #await asyncio.gather(c_queue_task,p_queue_task)
            except asyncio.CancelledError:
                return

        self.bot_status_update_loop.start()
        self.start_task = asyncio.create_task(start_client_cog())    
        
    async def cog_unload(self):
        self.bot_status_update_loop.cancel()

        self.start_task.cancel()
        await self.start_task
        
        BasicPlayer.clear_cache()
        BasicClan.clear_cache()
        
        aClanWar._cache = {}
        aRaidWeekend._cache = {}        
        aClashSeason._cache = {}
        
    ############################################################
    #####
    ##### LISTENERS
    #####
    ############################################################    
    @commands.Cog.listener("on_shard_connect")
    async def status_on_connect(self,shard_id):
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
    async def fetch_player(self,tag:str) -> aPlayer:
        player = None
        count_try = 0
        while True:
            try:
                count_try += 1
                player = await self.client.coc.get_player(tag,cls=aPlayer)
                break

            except coc.NotFound as exc:
                raise InvalidTag(tag) from exc
            
            except coc.ClashOfClansException as exc:
                cached = await self.get_player_from_loop(tag)
                if cached:
                    player = cached
                else:
                    raise ClashAPIError(exc) from exc
            
            except:
                if count_try > 5:
                    raise ClashAPIError()
                await asyncio.sleep(0.5)
                continue
        return player
    
    async def fetch_many_players(self,*tags) -> List[aPlayer]:
        tasks = []

        a_iter = AsyncIter(tags)
        async for tag in a_iter:
            task = asyncio.create_task(self.fetch_player(tag))
            tasks.append(task)

        ret = await asyncio.gather(*tasks,return_exceptions=True)
        if len([e for e in ret if isinstance(e,ClashAPIError)]) > 0:
            raise ClashAPIError([e for e in ret if isinstance(e,ClashAPIError)][0])
        
        ret_players = [p for p in ret if isinstance(p,aPlayer)]
        return ret_players

    async def fetch_members_by_season(self,clan:aClan,season:Optional[aClashSeason]=None) -> List[aPlayer]:
        def _db_query(q_clan,q_season):
            if q_season.is_current:
                query = db_Player.objects(
                    home_clan=q_clan.tag,
                    is_member=True
                    ).only('tag')
            else:
                query = db_PlayerStats.objects(
                    home_clan=q_clan.tag,
                    is_member=True,
                    season=q_season.id
                    ).only('tag') 
            return [p.tag for p in query]

        if not season or season.id not in [s.id for s in bot_client.tracked_seasons]:
            season = bot_client.current_season
        
        query = await bot_client.run_in_thread(_db_query,clan,season)     
        
        ret_players = await self.fetch_many_players(*query)
        return sorted(ret_players, key=lambda x:(ClanRanks.get_number(x.alliance_rank),x.town_hall_level,x.exp_level),reverse=True)     
    
    ############################################################
    #####
    ##### COC: CLANS
    #####
    ############################################################
    async def fetch_clan(self,tag:str) -> aClan:
        clan = None       
        count_try = 0
        while True:
            await asyncio.sleep(0)
            try:
                count_try += 1
                clan = await self.client.coc.get_clan(tag,cls=aClan)
                break

            except coc.NotFound as exc:
                raise InvalidTag(tag) from exc
            
            except coc.ClashOfClansException as exc:
                cached = await self.get_clan_from_loop(tag)
                if cached:
                    clan = cached
                else:
                    raise ClashAPIError(exc) from exc
            
            except:
                if count_try > 5:
                    raise ClashAPIError()
                await asyncio.sleep(0.5)
                continue
        
        return clan

    async def from_clan_abbreviation(self,abbreviation:str) -> aClan:
        def _db_query():
            try:
                get_clan = db_Clan.objects.get(abbreviation=abbreviation.upper())
            except:
                return None
            return get_clan.tag
        
        search = await bot_client.run_in_thread(_db_query)
        if not search:
            raise InvalidAbbreviation(abbreviation)
        
        clan = await self.fetch_clan(search)
        return clan
    
    async def get_registered_clans(self) -> List[aClan]:
        def _db_query():
            query = db_Clan.objects(
                Q(emoji__ne=None) & 
                Q(emoji__ne='')).only('tag')
            return [c.tag for c in query]
        
        c_tags = await bot_client.run_in_thread(_db_query)
        ret_clans = await asyncio.gather(*(self.fetch_clan(tag) for tag in c_tags))
        return sorted(ret_clans, key=lambda x:(x.level,x.capital_hall),reverse=True)

    async def get_alliance_clans(self) -> List[aClan]:
        def _db_query():
            query = db_AllianceClan.objects()
            return [c.tag for c in query]
        
        c_tags = await bot_client.run_in_thread(_db_query)
        ret_clans = await asyncio.gather(*(self.fetch_clan(tag) for tag in c_tags))
        return sorted(ret_clans, key=lambda x:(x.level,x.max_recruitment_level,x.capital_hall),reverse=True)

    async def get_war_league_clans(self) -> List[aClan]:
        def _db_query():
            query = db_WarLeagueClanSetup.objects(is_active=True).only('tag')
            return [c.tag for c in query]
        
        c_tags = await bot_client.run_in_thread(_db_query)
        ret_clans = await asyncio.gather(*(self.fetch_clan(tag) for tag in c_tags))
        return sorted(ret_clans, key=lambda x:(MultiplayerLeagues.get_index(x.war_league_name),x.level,x.capital_hall),reverse=True)

    ############################################################
    #####
    ##### COC: CLAN WARS
    #####
    ############################################################    
    async def get_clan_war(self,clan:aClan) -> aClanWar:
        api_war = None
        
        count_try = 0
        while True:
            await asyncio.sleep(0)
            try:
                count_try += 1
                api_war = await self.client.coc.get_clan_war(clan.tag)
                break
            except coc.PrivateWarLog:
                break
            except coc.NotFound as exc:
                raise InvalidTag(clan.tag) from exc
            except coc.ClashOfClansException as exc:
                raise ClashAPIError(exc) from exc
            except:
                if count_try > 5:
                    raise ClashAPIError()
                await asyncio.sleep(0.5)
                continue
        
        if api_war:                
            if getattr(api_war,'state','notInWar') != 'notInWar':
                clan_war = await aClanWar.create_from_api(api_war)
                return clan_war
        return None
            
    async def get_league_group(self,clan:aClan) -> WarLeagueGroup:
        api_group = None
        
        count_try = 0
        while True:
            await asyncio.sleep(0)
            try:
                count_try += 1
                api_group = await self.client.coc.get_league_group(clan.tag)
                break
            except coc.NotFound:
                break
            except coc.ClashOfClansException as exc:
                raise ClashAPIError(exc)
            except:
                if count_try > 5:
                    raise ClashAPIError()
                await asyncio.sleep(0.5)
                continue
                
        if api_group:
            if api_group.state in ['preparation','inWar','ended','warEnded']:
                league_group = await WarLeagueGroup.from_api(clan,api_group)
                return league_group
        return None
                
    ############################################################
    #####
    ##### COC: RAID WEEKEND
    #####
    ############################################################ 
    async def get_raid_weekend(self,clan:aClan) -> aRaidWeekend:
        raidloggen = None
        api_raid = None
        
        count_try = 0
        while True:
            await asyncio.sleep(0)
            try:
                count_try += 1
                raidloggen = await self.client.coc.get_raid_log(clan_tag=clan.tag,page=False,limit=1)
                break

            except coc.PrivateWarLog:
                break
            except coc.NotFound as exc:
                raise InvalidTag(self.tag) from exc
            except coc.ClashOfClansException as exc:
                raise ClashAPIError(exc) from exc
            except:
                if count_try > 5:
                    raise ClashAPIError()
                await asyncio.sleep(0.5)
                continue
                
        if raidloggen:
            if len(raidloggen) > 0:
                api_raid = raidloggen[0]
                if api_raid:
                    raid_weekend = await aRaidWeekend.create_from_api(clan,api_raid)
                    return raid_weekend
        return None
            
    ############################################################
    #####
    ##### STATUS REPORT
    #####
    ############################################################ 
    async def status_embed(self):
        embed = await clash_embed(self.bot,
            title="**Clash of Clans API**",
            message=f"### {pendulum.now().format('dddd, DD MMM YYYY HH:mm:ssZZ')}",
            timestamp=pendulum.now()
            )
        
        waiters = len(bot_client.coc.http._HTTPClient__lock._waiters) if bot_client.coc.http._HTTPClient__lock._waiters else 0
        api_connect_time = pendulum.now() - bot_client._last_login

        dd, hh, mm, ss = s_convert_seconds_to_str(api_connect_time.total_seconds())

        embed.add_field(
            name="**API Client**",
            value="```ini"
                + f"\n{'[Connect Time]':<15} {int(mm)}M {int(ss)}S"
                + f"\n{'[Maintenance]':<15} {self.api_maintenance}"
                + f"\n{'[API Keys]':<15} " + f"{bot_client.num_keys:,}"
                + f"\n{'[API Requests]':<15} " + f"{(bot_client.coc.http.key_count * bot_client.coc.http.throttle_limit) - bot_client.coc.http._HTTPClient__lock._value:,} / {int(bot_client.coc.http._HTTPClient__throttle.rate_limit):,}" + f" (Waiting: {waiters:,})"
                + "```",
            inline=False
            )
        embed.add_field(
            name="**Player API**",
            value="```ini"
                + f"\n{'[Last]':<10} {(self.player_api[-1] if len(self.player_api) > 0 else 0)/1000:.3f}s"
                + f"\n{'[Mean]':<10} {self.player_api_avg/1000:.3f}s"
                + f"\n{'[Min/Max]':<10} {(min(self.player_api) if len(self.player_api) > 0 else 0)/1000:.3f}s ~ {(max(self.player_api) if len(self.player_api) > 0 else 0)/1000:.3f}s"
                + "```",
            inline=False
            )
        embed.add_field(
            name="**Clan API**",
            value="```ini"
                + f"\n{'[Last]':<10} {(self.clan_api[-1] if len(self.clan_api) > 0 else 0)/1000:.3f}s"
                + f"\n{'[Mean]':<10} {self.clan_api_avg/1000:.3f}s"
                + f"\n{'[Min/Max]':<10} {(min(self.clan_api) if len(self.clan_api) > 0 else 0)/1000:.3f}s ~ {(max(self.clan_api) if len(self.clan_api) > 0 else 0)/1000:.3f}s"
                + "```",
            inline=False
            )
        
        sent, rcvd = bot_client.api_current_throughput
        avg_rcvd, last_rcvd, max_rcvd = bot_client.rcvd_stats
        avg_sent, last_sent, max_sent = bot_client.sent_stats
        
        embed.add_field(
            name="**Throughput (sent / rcvd, per second)**",
            value="```ini"
                + f"\n{'[Now]':<6} {sent:.2f} / {rcvd:.2f}"
                + f"\n{'[Last]':<6} {last_sent:.2f} / {last_rcvd:.2f}"
                + f"\n{'[Avg]':<6} {avg_sent:.2f} / {avg_rcvd:.2f}"
                + f"\n{'[Max]':<6} {max_sent:.2f} / {max_rcvd:.2f}"
                + "```",
            inline=False
            )
        return embed
    
    @commands.group(name="cocapi")
    @commands.is_owner()
    async def command_group_coc_api_client(self,ctx):
        """Manage the Clash of Clans API Client."""
        if not ctx.invoked_subcommand:
            pass
    
    @command_group_coc_api_client.command(name="status")
    @commands.is_owner()
    async def _status_report(self,ctx:commands.Context):
        """Status of the Clash of Clans API Client."""
        embed = await self.status_embed()
        view = RefreshStatus(ctx)
        await ctx.reply(embed=embed,view=view)

class RefreshStatus(DefaultView):
    def __init__(self,context:Union[discord.Interaction,commands.Context]):

        button = DiscordButton(
            function=self._refresh_embed,
            emoji=EmojisUI.REFRESH,
            label="Refresh",
            )

        super().__init__(context,timeout=9999999)
        self.is_active = True

        self.add_item(button)
    
    @property
    def client_cog(self) -> ClashOfClansClient:
        return bot_client.bot.get_cog("ClashOfClansClient")
    
    async def _refresh_embed(self,interaction:discord.Interaction,button:DiscordButton):
        await interaction.response.defer()
        embed = await self.client_cog.status_embed()
        await interaction.followup.edit_message(interaction.message.id,embed=embed)