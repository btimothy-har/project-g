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
from .api_client import BotClashClient, aClashSeason

from .coc_objects.clans.clan import aClan, db_Clan, db_AllianceClan, db_WarLeagueClanSetup
from .coc_objects.players.player import BasicPlayer, aPlayer, db_Player, db_PlayerStats
from .coc_objects.events.clan_war import aClanWar
from .coc_objects.events.clan_war_leagues import WarLeagueGroup
from .coc_objects.events.raid_weekend import aRaidWeekend

from .exceptions import InvalidTag, ClashAPIError, InvalidAbbreviation

from .utils.constants.coc_constants import ClanRanks, MultiplayerLeagues
from .utils.components import clash_embed, DefaultView, DiscordButton, EmojisUI

bot_client = BotClashClient()

class RequestCounter():
    def __init__(self):
        self._archive_sent = deque(maxlen=60)
        self._archive_received = deque(maxlen=60)
        self._sent = 0
        self._received = 0
        self._timestamp = pendulum.now()
        self._lock = asyncio.Lock()

    @property
    def current_average(self) -> (float, float):
        diff = pendulum.now() - self._timestamp
        sent_avg = self._sent / diff.total_seconds() if self._sent > 0 else 0
        rcvd_avg = self._received / diff.total_seconds() if self._received > 0 else 0
        return sent_avg, rcvd_avg
    
    @property
    def rcvd_stats(self) -> (float, float, float):
        if len(self._archive_received) == 0:
            return 0,0,0
        avg = sum(self._archive_received)/len(self._archive_received)
        last = self._archive_received[-1]
        maxr = max(self._archive_received)
        return avg, last, maxr
    
    @property
    def sent_stats(self) -> (float, float, float):
        if len(self._archive_sent) == 0:
            return 0,0,0
        avg = sum(self._archive_sent)/len(self._archive_sent)
        last = self._archive_sent[-1]
        maxr = max(self._archive_sent)
        return avg, last, maxr
    
    async def increment_sent(self):
        async with self._lock:
            self._sent += 1

    async def increment_received(self):
        async with self._lock:
            self._received += 1
    
    async def reset(self):
        async with self._lock:
            diff = pendulum.now() - self._timestamp
            self._archive_received.append(self._received / diff.total_seconds())
            self._received = 0
            self._archive_sent.append(self._sent / diff.total_seconds())
            self._sent = 0
            self._timestamp = pendulum.now()

class ClientThrottler:
    def __init__(self,cog:BotClashClient,rate_limit:int,concurrent_requests:int=1):
        self.cog = cog

        self.base_sleep = 1 / rate_limit
        self.sleep_time = 0

        self._lock = asyncio.Lock()
        self._semaphore = asyncio.Semaphore(concurrent_requests)

    async def __aenter__(self):
        async with self._semaphore:
            if self.cog.last_api_time > 1.5:
                async with self._lock:
                    self.sleep_time += (self.base_sleep * 0.1)
                    await asyncio.sleep(self.sleep_time)

            else:
                self.sleep_time = 0

    async def __aexit__(self, exc_type, exc_value, traceback):
        pass

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

        self.counter = RequestCounter()

        self.semaphore_limit = int(bot_client.rate_limit)
        
        self.client_semaphore = asyncio.Semaphore(self.semaphore_limit)
        self.api_lock = ClientThrottler(self,bot_client.rate_limit,20)
        
        self.player_api = deque(maxlen=10000)
        self.player_throttle = deque(maxlen=100)

        self.clan_api = deque(maxlen=10000)
        self.clan_throttle = deque(maxlen=100)
        
        self.war_api = deque(maxlen=1000)
        self.raid_api = deque(maxlen=1000)

    def format_help_for_context(self, ctx: commands.Context) -> str:
        context = super().format_help_for_context(ctx)
        return f"{context}\n\nAuthor: {self.__author__}\nVersion: {self.__version__}"
    
    @property
    def client(self) -> BotClashClient:
        return bot_client
    
    @property
    def api_maintenance(self) -> bool:
        cog = self.bot.get_cog("ClashOfClansTasks")
        return cog.api_maintenance
    
    @property
    def client_semaphore_waiters(self) -> int:
        return len(self.client_semaphore._waiters) if self.client_semaphore._waiters else 0
    
    @property
    def last_api_time(self) -> float:
        all_times = []
        if len(self.player_api) > 0:
            all_times.extend(list(self.player_api)[-100:])
        if len(self.clan_api) > 0:
            all_times.extend(list(self.clan_api)[-100:])
        #return average
        return sum(all_times)/len(all_times) if len(all_times) > 0 else 0

    @property
    def player_api_avg(self) -> float:
        return sum(self.player_api)/len(self.player_api) if len(self.player_api) > 0 else 0

    @property
    def clan_api_avg(self) -> float:
        return sum(self.clan_api)/len(self.clan_api) if len(self.clan_api) > 0 else 0

    @property
    def war_api_avg(self) -> float:
        return sum(self.war_api)/len(self.war_api) if len(self.war_api) > 0 else 0
    
    @property
    def raid_api_avg(self) -> float:
        return sum(self.raid_api)/len(self.raid_api) if len(self.raid_api) > 0 else 0

    ##################################################
    ### COG LOAD
    ##################################################
    async def cog_load(self):
        self.bot_status_update_loop.start()
        self.reset_counter.start()
        asyncio.create_task(self.start_client_cog())
    
    async def start_client_cog(self):
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
        
    async def cog_unload(self):
        self.bot_status_update_loop.cancel()
        self.reset_counter.cancel()

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
    
    @tasks.loop(seconds=59)
    async def reset_counter(self):
        await self.counter.reset()
    
    ############################################################
    #####
    ##### COC: PLAYERS
    #####
    ############################################################
    async def fetch_player(self,tag:str,no_cache=False,enforce_lock=False) -> aPlayer:

        player = None
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
            async with self.client_semaphore:
                ot = pendulum.now()
                if enforce_lock:
                    async with self.api_lock:
                        await asyncio.sleep(0)

                st = pendulum.now()
                diff = st - ot
                self.player_throttle.append(diff.total_seconds())

                await self.counter.increment_sent()
                player = await self.client.coc.get_player(n_tag,cls=aPlayer)

                diff = pendulum.now() - st
                self.player_api.append(diff.total_seconds())

                return player

        except coc.NotFound as exc:
            raise InvalidTag(tag) from exc
        except (coc.InvalidArgument,coc.InvalidCredentials,coc.Maintenance,coc.Forbidden,coc.GatewayError) as exc:
            if cached:
                return cached
            else:
                raise ClashAPIError(exc) from exc
        finally:
            if player:
                await self.client.player_cache.set(player.tag,player)
                await self.counter.increment_received()
                
                if player.is_new:
                    player.first_seen = pendulum.now()        
                if player.cached_name != player.name:
                    player.cached_name = player.name        
                if player.cached_xp_level != player.exp_level:
                    player.cached_xp_level = player.exp_level        
                if player.cached_townhall != player.town_hall_level:
                    player.cached_townhall = player.town_hall_level

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
    async def fetch_clan(self,tag:str,no_cache:bool=False,enforce_lock=False) -> aClan:
        
        clan = None
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
            async with self.client_semaphore:
                ot = pendulum.now()            
                if enforce_lock:
                    async with self.api_lock:
                        await asyncio.sleep(0)

                st = pendulum.now()
                diff = st - ot
                self.clan_throttle.append(diff.total_seconds())

                await self.counter.increment_sent()
                clan = await self.client.coc.get_clan(n_tag,cls=aClan)

                diff = pendulum.now() - st
                self.clan_api.append(diff.total_seconds())

                return clan

        except coc.NotFound as exc:
            raise InvalidTag(tag) from exc
        except (coc.Maintenance,coc.GatewayError) as exc:
            if cached:
                return cached
            else:
                raise ClashAPIError(exc) from exc
        finally:
            if clan:
                await self.client.clan_cache.set(clan.tag,clan)
                await self.counter.increment_received()
        
                if clan.name != clan.cached_name:
                    clan.cached_name = clan.name
                if clan.badge != clan.cached_badge:
                    clan.cached_badge = clan.badge        
                if clan.level != clan.cached_level:
                    clan.cached_level = clan.level        
                if clan.capital_hall != clan.cached_capital_hall:
                    clan.cached_capital_hall = clan.capital_hall        
                if clan.war_league_name != clan.cached_war_league:
                    clan.cached_war_league = clan.war_league_name

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
            async with self.client_semaphore:
                st = pendulum.now()

                await self.counter.increment_sent()
                api_war = await self.client.coc.get_clan_war(clan.tag)

                diff = pendulum.now() - st
                self.war_api.append(diff.total_seconds())

            if not api_war or getattr(api_war,'state','notInWar') == 'notInWar':
                return None        
            
            clan_war = await aClanWar.create_from_api(api_war)
            return clan_war

        except coc.PrivateWarLog:
            return None
        except coc.NotFound as exc:
            raise InvalidTag(clan.tag) from exc
        except (coc.Maintenance,coc.GatewayError) as exc:
            raise ClashAPIError(exc) from exc
        finally:
            if api_war:
                await self.counter.increment_received()
        
    async def get_league_group(self,clan:aClan) -> WarLeagueGroup:
        api_group = None
        try:
            async with self.client_semaphore:          
                st = pendulum.now()

                await self.counter.increment_sent()
                api_group = await self.client.coc.get_league_group(clan.tag)

                diff = pendulum.now() - st
                self.war_api.append(diff.total_seconds())

            if api_group and api_group.state in ['preparation','inWar','ended','warEnded']:
                league_group = await WarLeagueGroup.from_api(clan,api_group)
                return league_group

        except coc.NotFound:
            pass
        except (coc.Maintenance,coc.GatewayError) as exc:
            raise ClashAPIError(exc)
        finally:
            if api_group:
                await self.counter.increment_received()
            
    ############################################################
    #####
    ##### COC: RAID WEEKEND
    #####
    ############################################################ 
    async def get_raid_weekend(self,clan:aClan) -> aRaidWeekend:
        api_raid = None
        try:
            async with self.client_semaphore:
                st = pendulum.now()

                await self.counter.increment_sent()
                raidloggen = await self.client.coc.get_raid_log(clan_tag=clan.tag,page=False,limit=1)
                    
                diff = pendulum.now() - st
                self.raid_api.append(diff.total_seconds())

                if len(raidloggen) == 0:
                    return None
                api_raid = raidloggen[0]
                if not api_raid:
                    return None        
                raid_weekend = await aRaidWeekend.create_from_api(clan,api_raid)
                return raid_weekend

        except coc.PrivateWarLog:
            return None
        except coc.NotFound as exc:
            raise InvalidTag(self.tag) from exc
        except (coc.Maintenance,coc.GatewayError) as exc:
            raise ClashAPIError(exc) from exc
        finally:
            if api_raid:
                await self.counter.increment_received()
    
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

        embed.add_field(
            name="**API Client**",
            value="```ini"
                + f"\n{'[Maintenance]':<15} {self.api_maintenance}"
                + f"\n{'[API Keys]':<15} " + f"{bot_client.num_keys:,}"
                + f"\n{'[API Requests]':<15} {self.semaphore_limit - self.client_semaphore._value:,} / {self.semaphore_limit:,}"
                + "```",
            inline=False
            )
        
        avg_throttle = sum(self.player_throttle)/len(self.player_throttle) if len(self.player_throttle) > 0 else 0
        max_throttle = max(self.player_throttle) if len(self.player_throttle) > 0 else 0
        embed.add_field(
            name="**Player API**",
            value="```ini"
                + f"\n{'[Last]':<10} {(self.player_api[-1] if len(self.player_api) > 0 else 0):.3f}s"
                + f"\n{'[Mean]':<10} {self.player_api_avg:.3f}s"
                + f"\n{'[Min/Max]':<10} {(min(self.player_api) if len(self.player_api) > 0 else 0):.3f}s ~ {(max(self.player_api) if len(self.player_api) > 0 else 0):.3f}s"
                + f"\n{'[Throttle]':<10} {avg_throttle:.2f}s (max: {max_throttle:.2f}s)"
                + "```",
            inline=False
            )
        avg_throttle = sum(self.clan_throttle)/len(self.clan_throttle) if len(self.clan_throttle) > 0 else 0
        max_throttle = max(self.clan_throttle) if len(self.clan_throttle) > 0 else 0
        embed.add_field(
            name="**Clan API**",
            value="```ini"
                + f"\n{'[Last]':<10} {(self.clan_api[-1] if len(self.clan_api) > 0 else 0):.3f}s"
                + f"\n{'[Mean]':<10} {self.clan_api_avg:.3f}s"
                + f"\n{'[Min/Max]':<10} {(min(self.clan_api) if len(self.clan_api) > 0 else 0):.3f}s ~ {(max(self.clan_api) if len(self.clan_api) > 0 else 0):.3f}s"
                + f"\n{'[Throttle]':<10} {avg_throttle:.2f}s (max: {max_throttle:.2f}s)"
                + "```",
            inline=False
            )
        embed.add_field(
            name="**Clan War API**",
            value="```ini"
                + f"\n{'[Last]':<6} {(self.war_api[-1] if len(self.war_api) > 0 else 0):.3f}s"
                + f"\n{'[Avg]':<6} {self.war_api_avg:.3f}s"
                + f"\n{'[Min]':<6} {(min(self.war_api) if len(self.war_api) > 0 else 0):.3f}s"
                + f"\n{'[Max]':<6} {(max(self.war_api) if len(self.war_api) > 0 else 0):.3f}s"
                + "```",
            inline=True
            )
        embed.add_field(
            name="**Capital Raids API**",
            value="```ini"
                + f"\n{'[Last]':<6} {(self.raid_api[-1] if len(self.raid_api) > 0 else 0):.3f}s"
                + f"\n{'[Avg]':<6} {self.raid_api_avg:.3f}s"
                + f"\n{'[Min]':<6} {(min(self.raid_api) if len(self.raid_api) > 0 else 0):.3f}s"
                + f"\n{'[Max]':<6} {(max(self.raid_api) if len(self.raid_api) > 0 else 0):.3f}s"
                + "```",
            inline=True
            )
        
        sent, rcvd = self.counter.current_average
        avg_rcvd, last_rcvd, max_rcvd = self.counter.rcvd_stats
        avg_sent, last_sent, max_sent = self.counter.sent_stats
        
        embed.add_field(
            name="**Request Throughput (sent / rcvd, per second)**",
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