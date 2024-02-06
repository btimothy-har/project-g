import asyncio
import coc
import discord
import pendulum

from typing import *

from art import text2art
from collections import deque
from discord.ext import tasks

from redbot.core import commands
from redbot.core.bot import Red
from redbot.core.utils import AsyncIter,bounded_gather

from .api_client import BotClashClient, aClashSeason

from .coc_objects.players.player import BasicPlayer, aPlayer
from .coc_objects.players.townhall import aTownHall
from .coc_objects.clans.clan import BasicClan, aClan
from .coc_objects.events.clan_war import aClanWar
from .coc_objects.events.clan_war_leagues import WarLeagueGroup
from .coc_objects.events.raid_weekend import aRaidWeekend

from .exceptions import InvalidTag, ClashAPIError, InvalidAbbreviation

from .utils.constants.coc_constants import ClanRanks, MultiplayerLeagues
from .utils.components import clash_embed, DefaultView, DiscordButton, EmojisUI

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
        self.season_lock = asyncio.Lock()

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
    
    @commands.command(name="convertstat")
    @commands.is_owner()
    async def command_convert_stat(self,ctx:commands.Context):
        
        await self.client.coc_db.db__player_activity.delete_many({'legacy_conversion':True})        
        query = self.client.coc_db.db__player_stats.find({})

        now = pendulum.now()

        await ctx.tick()
        async for entry in query:
            season = await aClashSeason(entry['season'])
            timestamp = now if season.is_current else season.season_end
            tag = entry['tag']
            name = entry['name']
            is_member = entry['is_member']
            home_clan = entry['home_clan']
            townhall = aTownHall(
                level=entry['town_hall'],
                weapon=0 if entry['town_hall'] < 12 else 1
                )

            try:
                player = await self.client.coc.get_player(tag,cls=aPlayer)
            except:
                continue

            if len(name) <= 0:
                name = player.name
            
            if entry['time_in_home_clan'] > 0:
                await self.client.coc_db.db__player_activity.insert_one(
                    {
                        'tag':tag,
                        'name':name,
                        'is_member':is_member,
                        'discord_user':player.discord_user,
                        'townhall':townhall.json(),
                        'home_clan':home_clan,
                        'clan':'',
                        'activity':'time_in_home_clan',
                        'stat':'',
                        'change':0,
                        'new_value':entry['time_in_home_clan'],
                        'timestamp':timestamp.int_timestamp,
                        'read_by_bank':True,
                        'legacy_conversion':True
                    }
                )

            attack_wins = entry.get('attacks',{})
            if attack_wins.get('season_total',0) > 0:
                await self.client.coc_db.db__player_activity.insert_one(
                    {
                        'tag':tag,
                        'name':name,
                        'is_member':is_member,
                        'discord_user':player.discord_user,
                        'townhall':townhall.json(),
                        'home_clan':home_clan,
                        'clan':'',
                        'activity':'attack_wins',
                        'stat':'',
                        'change':attack_wins.get('season_total',0),
                        'new_value':attack_wins.get('lastUpdate',0),
                        'timestamp':timestamp.int_timestamp,
                        'read_by_bank':True,
                        'legacy_conversion':True
                    }
                )

            defense_wins = entry.get('defenses',{})
            if defense_wins.get('season_total',0) > 0:
                await self.client.coc_db.db__player_activity.insert_one(
                    {
                        'tag':tag,
                        'name':name,
                        'is_member':is_member,
                        'discord_user':player.discord_user,
                        'townhall':townhall.json(),
                        'home_clan':home_clan,
                        'clan':'',
                        'activity':'defense_wins',
                        'stat':'',
                        'change':defense_wins.get('season_total',0),
                        'new_value':defense_wins.get('lastUpdate',0),
                        'timestamp':timestamp.int_timestamp,
                        'read_by_bank':True,
                        'legacy_conversion':True
                    }
                )

            donations_sent = entry.get('donations_sent',{})
            if donations_sent.get('season_total',0) > 0:
                await self.client.coc_db.db__player_activity.insert_one(
                    {
                        'tag':tag,
                        'name':name,
                        'is_member':is_member,
                        'discord_user':player.discord_user,
                        'townhall':townhall.json(),
                        'home_clan':home_clan,
                        'clan':'',
                        'activity':'donations_sent',
                        'stat':'',
                        'change':donations_sent.get('season_total',0),
                        'new_value':donations_sent.get('lastUpdate',0),
                        'timestamp':timestamp.int_timestamp,
                        'read_by_bank':True,
                        'legacy_conversion':True
                    }
                )

            donations_rcvd = entry.get('donations_rcvd',{})
            if donations_rcvd.get('season_total',0) > 0:
                await self.client.coc_db.db__player_activity.insert_one(
                    {
                        'tag':tag,
                        'name':name,
                        'is_member':is_member,
                        'discord_user':player.discord_user,
                        'townhall':townhall.json(),
                        'home_clan':home_clan,
                        'clan':'',
                        'activity':'donations_received',
                        'stat':'',
                        'change':donations_rcvd.get('season_total',0),
                        'new_value':donations_rcvd.get('lastUpdate',0),
                        'timestamp':timestamp.int_timestamp,
                        'read_by_bank':True,
                        'legacy_conversion':True
                    }
                )
            
            loot_gold = entry.get('loot_gold',{})
            if loot_gold.get('season_total',0) > 0:
                await self.client.coc_db.db__player_activity.insert_one(
                    {
                        'tag':tag,
                        'name':name,
                        'is_member':is_member,
                        'discord_user':player.discord_user,
                        'townhall':townhall.json(),
                        'home_clan':home_clan,
                        'clan':'',
                        'activity':'loot_gold',
                        'stat':'',
                        'change':loot_gold.get('season_total',0),
                        'new_value':loot_gold.get('lastUpdate',0),
                        'timestamp':timestamp.int_timestamp,
                        'read_by_bank':True,
                        'legacy_conversion':True
                    }
                )
            
            loot_elixir = entry.get('loot_elixir',{})
            if loot_elixir.get('season_total',0) > 0:
                await self.client.coc_db.db__player_activity.insert_one(
                    {
                        'tag':tag,
                        'name':name,
                        'is_member':is_member,
                        'discord_user':player.discord_user,
                        'townhall':townhall.json(),
                        'home_clan':home_clan,
                        'clan':'',
                        'activity':'loot_elixir',
                        'stat':'',
                        'change':loot_elixir.get('season_total',0),
                        'new_value':loot_elixir.get('lastUpdate',0),
                        'timestamp':timestamp.int_timestamp,
                        'read_by_bank':True,
                        'legacy_conversion':True
                    }
                )
            
            loot_darkelixir = entry.get('loot_darkelixir',{})
            if loot_darkelixir.get('season_total',0) > 0:
                await self.client.coc_db.db__player_activity.insert_one(
                    {
                        'tag':tag,
                        'name':name,
                        'is_member':is_member,
                        'discord_user':player.discord_user,
                        'townhall':townhall.json(),
                        'home_clan':home_clan,
                        'clan':'',
                        'activity':'loot_darkelixir',
                        'stat':'',
                        'change':loot_darkelixir.get('season_total',0),
                        'new_value':loot_darkelixir.get('lastUpdate',0),
                        'timestamp':timestamp.int_timestamp,
                        'read_by_bank':True,
                        'legacy_conversion':True
                    }
                )
            
            capitalcontribution = entry.get('capitalcontribution',{})
            if capitalcontribution.get('season_total',0) > 0:
                await self.client.coc_db.db__player_activity.insert_one(
                    {
                        'tag':tag,
                        'name':name,
                        'is_member':is_member,
                        'discord_user':player.discord_user,
                        'townhall':townhall.json(),
                        'home_clan':home_clan,
                        'clan':'',
                        'activity':'capital_contribution',
                        'stat':'',
                        'change':capitalcontribution.get('season_total',0),
                        'new_value':capitalcontribution.get('lastUpdate',0),
                        'timestamp':timestamp.int_timestamp,
                        'read_by_bank':True,
                        'legacy_conversion':True
                    }
                )

            clangames = entry.get('clangames',{})
            if clangames.get('score',0) > 0:
                await self.client.coc_db.db__player_activity.insert_one(
                    {
                        'tag':tag,
                        'name':name,
                        'is_member':is_member,
                        'discord_user':player.discord_user,
                        'townhall':townhall.json(),
                        'home_clan':home_clan,
                        'clan':clangames.get('clan',''),
                        'activity':'clan_games',
                        'stat':'',
                        'change':0,
                        'new_value':clangames.get('last_updated',0) - clangames.get('score',0),
                        'timestamp':clangames.get('starting_time',0) if clangames.get('starting_time',None) else 0,
                        'read_by_bank':True,
                        'legacy_conversion':True
                    }
                )
                await self.client.coc_db.db__player_activity.insert_one(
                    {
                        'tag':tag,
                        'name':name,
                        'is_member':is_member,
                        'discord_user':player.discord_user,
                        'townhall':townhall.json(),
                        'home_clan':home_clan,
                        'clan':clangames.get('clan',''),
                        'activity':'clan_games',
                        'stat':'',
                        'change':clangames.get('score',0),
                        'new_value':clangames.get('last_updated',0),
                        'timestamp':clangames.get('ending_time',0) if clangames.get('ending_time',None) else season.clangames_end.int_timestamp,
                        'read_by_bank':True,
                        'legacy_conversion':True
                    }
                )            
            bot_client.coc_data_log.debug(f"Converted Stats for {tag} {name} {season.id}")
        await self.bot.send_to_owners("Stats Conversion Complete")

    ##################################################
    ### COG LOAD
    ##################################################
    async def cog_load(self):
        self.bot_status_update_loop.start() 
        self.clash_season_check.start()
        
    async def cog_unload(self):
        self.bot_status_update_loop.cancel()
        self.clash_season_check.cancel()

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
            if self.client.last_status_update != None and (pendulum.now().int_timestamp - self.client.last_status_update.int_timestamp) < (6* 3600):
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
    
    @tasks.loop(seconds=10.0)
    async def clash_season_check(self):
        if self.season_lock.locked():
            return
        
        try:
            async with self.season_lock:
                season = await aClashSeason.get_current_season()

                if season.id == bot_client.current_season.id:
                    return None
                
                await season.set_as_current()
                await bot_client.load_seasons()
                
                bot_client.coc_main_log.info(f"New Season Started: {season.id} {season.description}\n"
                    + text2art(f"{season.id}",font="small")
                    )
                bot_client.coc_data_log.info(f"New Season Started: {season.id} {season.description}\n"
                    + text2art(f"{season.id}",font="small")
                    )
                
                await bot_client.bot.change_presence(
                    activity=discord.Activity(
                        type=discord.ActivityType.playing,
                        name=f"start of the {bot_client.current_season.short_description} Season! Clash on!")
                        )

                bank_cog = bot_client.bot.get_cog('Bank')
                if bank_cog:
                    await bank_cog.apply_bank_taxes()
                    await bank_cog.month_end_sweep()
        
        except Exception as exc:
            await self.bot.send_to_owners(f"An error occured during Season Refresh. Check logs for details."
                + f"```{exc}```")
            bot_client.coc_main_log.exception(
                f"Error in Season Refresh"
                )        
        finally:
            bot_client.last_season_check = pendulum.now()

    ############################################################
    #####
    ##### COC: PLAYERS
    #####
    ############################################################
    async def fetch_player(self,tag:str) -> aPlayer:
        n_tag = coc.utils.correct_tag(tag)
        if not coc.utils.is_valid_tag(n_tag):
            raise InvalidTag(n_tag)
        
        count = 0
        player = None        
        while True:
            try:
                count += 1
                player = await self.client.coc.get_player(n_tag,cls=aPlayer)
                break
            except coc.NotFound as exc:
                raise InvalidTag(n_tag) from exc
            except (coc.Maintenance,coc.GatewayError) as exc:
                cached = await self.get_player_from_loop(n_tag)
                if cached:
                    player = cached
                else:
                    raise ClashAPIError(exc)
                break
            except:
                if count > 3:
                    raise ClashAPIError()
                await asyncio.sleep(1)
                    
        return player
    
    async def fetch_many_players(self,*tags) -> List[aPlayer]:
        tasks = []

        a_iter = AsyncIter(tags)
        tasks = [self.fetch_player(tag) async for tag in a_iter]
        ret = await bounded_gather(*tasks,limit=1,return_exceptions=True)

        if len([e for e in ret if isinstance(e,ClashAPIError)]) > 0:
            raise ClashAPIError([e for e in ret if isinstance(e,ClashAPIError)][0])
        
        ret_players = [p for p in ret if isinstance(p,aPlayer)]
        return ret_players

    async def fetch_members_by_season(self,clan:aClan,season:Optional[aClashSeason]=None) -> List[aPlayer]:
        if not season or season.id not in [s.id for s in bot_client.tracked_seasons]:
            season = bot_client.current_season
        
        if season.is_current:
            query = bot_client.coc_db.db__player.find(
                {
                    'home_clan':clan.tag,
                    'is_member':True
                    },
                {'_id':1}
                )
            tags = [p['_id'] async for p in query]
        else:
            query = bot_client.coc_db.db__player_stats.find(
                {
                    '_id.season':season.id,
                    'home_clan':clan.tag,
                    'is_member':True,
                    },
                {'_id':1,'tag':1}
                )
            tags = [p['tag'] async for p in query]
                    
        ret_players = await self.fetch_many_players(*tags)
        return sorted(
            ret_players,
            key=lambda x:(ClanRanks.get_number(x.alliance_rank),x.town_hall.level,x.exp_level),
            reverse=True
            )
    
    ############################################################
    #####
    ##### COC: CLANS
    #####
    ############################################################
    async def fetch_clan(self,tag:str) -> aClan:
        n_tag = coc.utils.correct_tag(tag)
        if not coc.utils.is_valid_tag(n_tag):
            raise InvalidTag(n_tag)
        
        count = 0
        clan = None       
        while True:
            try:
                count += 1
                clan = await self.client.coc.get_clan(n_tag,cls=aClan)
                break
            except coc.NotFound as exc:
                raise InvalidTag(n_tag) from exc
            except (coc.GatewayError,coc.Maintenance) as exc:
                cached = await self.get_clan_from_loop(n_tag)
                if cached:
                    clan = cached
                else:
                    raise ClashAPIError(exc) from exc
                break
            except:
                if count > 3:
                    raise ClashAPIError()
                await asyncio.sleep(1)
            
        return clan

    async def fetch_many_clans(self,*tags) -> List[aClan]:
        tasks = []

        a_iter = AsyncIter(tags)
        tasks = [self.fetch_clan(tag) async for tag in a_iter]
        ret = await bounded_gather(*tasks,limit=1,return_exceptions=True)

        if len([e for e in ret if isinstance(e,ClashAPIError)]) > 0:
            raise ClashAPIError([e for e in ret if isinstance(e,ClashAPIError)][0])
        
        ret_clans = [p for p in ret if isinstance(p,aClan)]
        return ret_clans

    async def from_clan_abbreviation(self,abbreviation:str) -> aClan:
        query = await bot_client.coc_db.db__clan.find_one(
            {
                'abbreviation':abbreviation.upper()
                },
            {'_id':1}
            )
        if not query:
            raise InvalidAbbreviation(abbreviation)
        
        clan = await self.fetch_clan(query['_id'])
        return clan
    
    async def get_registered_clans(self) -> List[aClan]:
        query = bot_client.coc_db.db__clan.find(
            {
                "emoji": {
                    "$exists": True,
                    "$ne": ""
                    }
                },
                {'_id':1}
                )
        tags = [c['_id'] async for c in query]
        ret_clans = await self.fetch_many_clans(*tags)
        return sorted(
            ret_clans,
            key=lambda x:(x.level,x.capital_hall),
            reverse=True
            )

    async def get_alliance_clans(self) -> List[aClan]:
        query = bot_client.coc_db.db__alliance_clan.find({},{'_id':1})
        tags = [c['_id'] async for c in query]
        ret_clans = await self.fetch_many_clans(*tags)
        return sorted(
            ret_clans,
            key=lambda x:(x.level,x.max_recruitment_level,x.capital_hall),
            reverse=True
            )

    async def get_war_league_clans(self) -> List[aClan]:
        query = bot_client.coc_db.db__war_league_clan_setup.find(
            {
                'is_active':True
                },
            {'_id':1}
            )
        tags = [c['_id'] async for c in query]
        ret_clans = await self.fetch_many_clans(*tags)
        return sorted(
            ret_clans,
            key=lambda x:(MultiplayerLeagues.get_index(x.war_league_name),x.level,x.capital_hall),
            reverse=True
            )

    ############################################################
    #####
    ##### COC: CLAN WARS
    #####
    ############################################################    
    async def get_clan_war(self,clan:aClan) -> aClanWar:
        count = 0
        api_war = None
        
        while True:
            try:
                count += 1
                api_war = await self.client.coc.get_clan_war(clan.tag)
                break
            except coc.PrivateWarLog:
                return None
            except coc.NotFound as exc:
                raise InvalidTag(clan.tag) from exc
            except (coc.Maintenance,coc.GatewayError) as exc:
                raise ClashAPIError(exc) from exc
            except:
                if count > 3:
                    raise ClashAPIError()
                await asyncio.sleep(1)
        
        if api_war:
            if getattr(api_war,'state','notInWar') != 'notInWar':
                clan_war = await aClanWar.create_from_api(api_war)
                return clan_war
        return None
            
    async def get_league_group(self,clan:aClan) -> WarLeagueGroup:
        count = 0
        api_group = None

        while True:
            try:
                count += 1
                api_group = await self.client.coc.get_league_group(clan.tag)
                break
            except coc.NotFound:
                raise InvalidTag(clan.tag)
            except (coc.Maintenance,coc.GatewayError) as exc:
                raise ClashAPIError(exc)
            except:
                if count > 3:
                    raise ClashAPIError()
                await asyncio.sleep(1)
                
        if api_group and getattr(api_group,'state','notInWar') in ['preparation','inWar','ended','warEnded']:
            league_group = await WarLeagueGroup.from_api(clan,api_group)
            return league_group
        return None
                
    ############################################################
    #####
    ##### COC: RAID WEEKEND
    #####
    ############################################################ 
    async def get_raid_weekend(self,clan:aClan) -> aRaidWeekend:
        count = 0
        raidloggen = None
        api_raid = None
        
        while True:
            try:
                count += 1
                raidloggen = await self.client.coc.get_raid_log(clan_tag=clan.tag,page=False,limit=1)
                break
            except coc.PrivateWarLog:
                return None
            except coc.NotFound as exc:
                raise InvalidTag(self.tag) from exc
            except (coc.Maintenance,coc.GatewayError) as exc:
                raise ClashAPIError(exc) from exc
            except:
                if count > 3:
                    raise ClashAPIError()
                await asyncio.sleep(1)
                
        if raidloggen and len(raidloggen) > 0:
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
        embed.add_field(
            name="**API Client**",
            value="```ini"
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