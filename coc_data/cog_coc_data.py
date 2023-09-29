import os
import coc
import discord
import logging
import pendulum
import asyncio
import random

from typing import *
from mongoengine import connect
from redbot.core import commands
from redbot.core.utils import AsyncIter

from discord.ext import tasks
from art import text2art

from coc_client.api_client import BotClashClient

from mongoengine import DoesNotExist

from .objects.season.season import dSeason, aClashSeason
from .objects.players.player import aPlayer, db_Player, _PlayerAttributes
from .objects.players.player_season import db_PlayerStats
from .objects.clans.clan import aClan, db_Clan, db_AllianceClan
from .objects.clans.clan_cwl_attributes import db_WarLeagueClanSetup
from .objects.events.clan_war_leagues import WarLeagueGroup
from .objects.events.clan_war import db_ClanWar, aClanWar
from .objects.events.raid_weekend import db_RaidWeekend, aRaidWeekend

from .objects.discord.member import aMember
from .objects.discord.guild import aGuild
from .objects.discord.apply_panel import db_ClanApplication, account_recruiting_summary, account_recruiting_embed
from .objects.discord.recruiting_reminder import RecruitingReminder
from .objects.discord.clan_link import ClanGuildLink

from .feeds.capital_contribution import CapitalContributionFeed

from .tasks.default import TaskLoop
from .tasks.player_tasks import PlayerLoop
from .tasks.clan_tasks import ClanLoop
from .tasks.war_tasks import ClanWarLoop
from .tasks.raid_tasks import ClanRaidLoop
from .tasks.guild_tasks import DiscordGuildLoop

from .constants.coc_emojis import *
from .constants.coc_constants import *

from .utilities.components import *

from .exceptions import *

coc_main_logger = logging.getLogger("coc.main")
coc_main_logger.setLevel(logging.INFO)

coc_data_logger = logging.getLogger("coc.data")
coc_data_logger.setLevel(logging.INFO)

############################################################
############################################################
#####
##### EXCEPTIONS
#####
############################################################
############################################################
class LoginNotSet(Exception):
    def __init__(self, exc):
        self.message = exc
        super().__init__(self.message)
    def __str__(self):
        return f'{self.message}'

############################################################
############################################################
#####
##### DATA COG
#####
############################################################
############################################################
class ClashOfClansData(commands.Cog):
    """
    Data Client for Clash of Clans
    
    Working with Clash of Clans API, this cog facilities the caching, storage, and retrieval of data from the API.

    Permanent data is stored on MongoDB. Cached data is not persistent.

    MongoDB parameters are stored RedBot's API framework, using the `[p]set api clash_db` command. The accepted parameters are as follows:
    - `dbpriamry` : The name of the primary database.
    - `username` : Database Username
    - `password` : Database Password    
    """

    __author__ = "bakkutteh"
    __version__ = "1.3.0"

    def __init__(self,bot):
        self.bot = bot
        self.ready = False
        self.coc_main_log = coc_main_logger
        self.coc_data_log = coc_data_logger

        log_formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s')

        main_logpath = f"{self.bot.coc_log_path}/main"
        if not os.path.exists(main_logpath):
            os.makedirs(main_logpath)

        cocmain_log_handler = logging.handlers.RotatingFileHandler(
            f"{main_logpath}/main.log",
            maxBytes=3*1024*1024,
            backupCount=9
            )
        cocmain_log_handler.setFormatter(log_formatter)
        self.coc_main_log.addHandler(cocmain_log_handler)

        data_logpath = f"{self.bot.coc_log_path}/data"
        if not os.path.exists(data_logpath):
            os.makedirs(data_logpath)

        cocdata_log_handler = logging.handlers.RotatingFileHandler(
            f"{data_logpath}/data.log",
            maxBytes=10*1024*1024,
            backupCount=9
            )
        cocdata_log_handler.setFormatter(log_formatter)
        self.coc_data_log.addHandler(cocdata_log_handler)

        self.last_refresh_loop = None
        self.last_error_report = None

        self.clash_task_lock = asyncio.Lock()
        self.recruiting_task_lock = asyncio.Lock()

        self.api_maintenance = False

    def format_help_for_context(self, ctx: commands.Context) -> str:
        context = super().format_help_for_context(ctx)
        return f"{context}\n\nAuthor: {self.__author__}\nVersion: {self.__version__}"

    @property
    def client(self):
        return BotClashClient()
    
    @property
    def player_cache(self):
        return self.client.player_cache

    @property
    def clan_cache(self):
        return self.client.clan_cache

    async def cog_load(self):
        self.coc_main_log.info(
            "##################################################\n"
            + text2art("Loading Clash of Clans",font="big")
            )
        
        asyncio.create_task(self.cog_start_up())
    
    async def cog_start_up(self):            
        clash_database = await self.bot.get_shared_api_tokens("clash_db")
        if clash_database.get("dbprimary") is None:
            raise LoginNotSet(f"Clash of Clans Database Name not set.")
        if clash_database.get("username") is None:
            raise LoginNotSet(f"Clash of Clans Database Username not set.")
        if clash_database.get("password") is None:
            raise LoginNotSet(f"Clash of Clans Database Password not set.")
        
        #connect to mongoengine
        connect(
            db=clash_database.get("dbprimary"),
            username=clash_database.get("username"),
            password=clash_database.get("password"),
            uuidRepresentation="pythonLegacy"
            )

        asyncio.create_task(self.start_recruiting_loop())
        war_tasks = asyncio.create_task(aClanWar.load_all())
        raid_tasks = asyncio.create_task(aRaidWeekend.load_all())

        wars = await war_tasks        
        self.coc_main_log.info(
            f"Loaded {len(wars):,} Clan Wars from database."
            )
        raids = await raid_tasks
        self.coc_main_log.info(
            f"Loaded {len(raids):,} Capital Raids from database."
            )
        players = [p.tag for p in db_Player.objects().only('tag')]
        clans_in_database = [c.tag for c in db_Clan.objects().only('tag')]

        while True:
            if isinstance(getattr(self.bot,'coc_client',None),coc.EventsClient):
                if self.bot.coc_state._api_logged_in:
                    break
            await asyncio.sleep(1)

        self.clash_semaphore_limit = int((len(self.bot.coc_client.http._keys)*20))
        self.clash_semaphore = asyncio.Semaphore(self.clash_semaphore_limit)

        self.coc_main_log.info(f"Found {len(self.bot.coc_client.http._keys):,} API Keys, setting semaphore limit at {self.clash_semaphore_limit:,}.")
        
        self.clan_cache.queue.extend(clans_in_database)
        self.coc_main_log.info(
            f"Found {len(clans_in_database):,} clans in database."
            )
        self.player_cache.queue.extend(players)
        self.coc_main_log.info(
            f"Found {len(players):,} players in database."
            )        
        async with self.clash_task_lock:
            self.clash_data_loop.start()        
        self.bot_status_update_loop.start()
        
        self.bot.coc_client.add_events(
            self.clash_maintenance_start,
            self.clash_maintenance_complete
            )
        
        self.coc_main_log.info(f"Completed initialization of Clash Data Client.\n"
            + text2art("Clash On!",font="banner")
            )
        self.ready = True
    
    async def start_recruiting_loop(self):
        await self.bot.wait_until_red_ready()
        async with self.recruiting_task_lock:
            posts = RecruitingReminder.get_all()
            async for post in AsyncIter(posts):
                count = 0
                while True:
                    try:
                        count += 1
                        await post.refresh_reminder()
                        break
                    except Exception:
                        if count > 30:
                            self.coc_main_log.exception(f"Could not refresh reminder for {post.id} - {post}")
                            break
                        await asyncio.sleep(1)
        
            self.refresh_recruiting_reminders.start()        
    
    async def cog_unload(self):
        self.clash_data_loop.cancel()
        self.refresh_recruiting_reminders.cancel()
        self.bot_status_update_loop.cancel()

        self.coc_main_log.info(f"Stopped Clash Data Loop.")

        for handler in self.coc_main_log.handlers:
            self.coc_main_log.removeHandler(handler)
        for handler in self.coc_data_log.handlers:
            self.coc_data_log.removeHandler(handler)

        stop_tasks = []
        stop_tasks.extend([asyncio.create_task(i.stop()) for i in DiscordGuildLoop.loops()])
        stop_tasks.extend([asyncio.create_task(i.stop()) for i in ClanRaidLoop.loops()])
        stop_tasks.extend([asyncio.create_task(i.stop()) for i in ClanWarLoop.loops()])
        stop_tasks.extend([asyncio.create_task(i.stop()) for i in ClanLoop.loops()])
        stop_tasks.extend([asyncio.create_task(i.stop()) for i in PlayerLoop.loops()])

        #await asyncio.gather(*stop_tasks,return_exceptions=True)

        #disconnect from MongoEngine
        #disconnect()

    ##################################################
    ### TASK REFRESH LOOP
    ##################################################
    @tasks.loop(minutes=1.0)
    async def clash_data_loop(self):
        def predicate_clan_not_in_loop(clan):
            if clan.tag not in [i.tag for i in ClanLoop.loops() if i.loop_active]:
                return True
            if clan.tag not in [i.tag for i in ClanWarLoop.loops() if i.loop_active]:
                return True
            if clan.tag not in [i.tag for i in ClanRaidLoop.loops() if i.loop_active]:
                return True
            return False
        
        def predicate_player_not_in_loop(player):
            return player.tag not in [i.tag for i in PlayerLoop.loops() if i.loop_active]
        
        try:            
            clans = AsyncIter(self.clan_cache.values)
            async for clan in clans.filter(predicate_clan_not_in_loop):
                await self.create_clan_task(clan.tag)
                if clan.is_alliance_clan or clan.is_registered_clan or clan.cwl_config.is_cwl_clan:
                    await self.create_war_task(clan.tag)
                if clan.is_alliance_clan or clan.is_registered_clan:
                    await self.create_raid_task(clan.tag)

            players = AsyncIter(self.player_cache.values)
            async for player in players.filter(predicate_player_not_in_loop):
                await self.create_player_task(player.tag)
            
            for guild in self.bot.guilds:
                if guild.id not in [i.guild_id for i in DiscordGuildLoop.loops() if i.loop_active]:
                    await self.create_guild_task(guild.id)

            player_queue = self.player_cache.queue.copy()
            clan_queue = self.clan_cache.queue.copy()

            batch_limit = self.clash_semaphore_limit
            c_count = 0
            async for c in AsyncIter(clan_queue[:batch_limit]):
                if c not in ClanLoop.keys():
                    c_count += 1
                    rc = await self.create_clan_task(c)
                    if c == rc:
                        self.clan_cache.remove_from_queue(c)
                else:
                    self.clan_cache.remove_from_queue(c)

            p_limit = batch_limit - c_count
            async for p in AsyncIter(player_queue[:p_limit]):
                if p not in PlayerLoop.keys():
                    rp = await self.create_player_task(p)
                    if p == rp:
                        self.player_cache.remove_from_queue(p)
            
            await self._season_check()                

        except Exception as exc:
            await self.bot.send_to_owners(f"An error occured during Clash Data loop. Check logs for details."
                + f"```{exc}```")
            self.coc_main_log.exception(
                f"Error in Clash Data Loop"
                )        
        finally:
            self.last_refresh_loop = pendulum.now()
    
    @tasks.loop(minutes=5.0)
    async def refresh_recruiting_reminders(self):
        if self.recruiting_task_lock.locked():
            self.coc_main_log.warning(f"Recruiting Loop Lock already acquired.")
            return
        try:
            async with self.recruiting_task_lock:
                posts = RecruitingReminder.get_all()
                async for post in AsyncIter(posts):
                    await post.send_reminder()
        
        except Exception:
            await self.bot.send_to_owners(f"An error occured during Recruiting Loop. Check logs for details.")
            self.coc_main_log.exception(f"Error in Recruiting Loop")
    
    @tasks.loop(minutes=30.0)
    async def bot_status_update_loop(self):
        try:
            event_options = [
                'default',
                'player_count',
                'member_count'
                ]
            select_event = random.choice(event_options)        
            while True:
                if select_event in ['default']:
                    await self.bot.change_presence(
                        activity=discord.Activity(
                            type=discord.ActivityType.listening,
                            name=f"$help!")
                            )
                    break

                try:
                    if select_event in ['player_count']:
                        if len(PlayerLoop.keys()) == 0:
                            select_event = 'default'
                        else:
                            await self.bot.change_presence(
                                activity=discord.Activity(
                                    type=discord.ActivityType.watching,
                                    name=f"{len(PlayerLoop.keys()):,} Clashers")
                                    )
                            break
                except:
                    select_event = 'default'

                try:
                    if select_event in ['member_count']:
                        await self.bot.change_presence(
                            activity=discord.Activity(
                                type=discord.ActivityType.playing,
                                name=f"with {len(self.bot.users):,} Hoomans")
                                )
                        break
                    
                except:
                    select_event = 'default'                    
        
        except Exception:
            #await self.bot.send_to_owners(f"An error occured during the Bot Status Update Loop. Check logs for details.")
            self.coc_main_log.exception(
                f"Error in Bot Status Loop"
                )
    
    @coc.ClientEvents.maintenance_start()
    async def clash_maintenance_start(self):
        self.api_maintenance = True
        await self.clash_task_lock.acquire()

        self.coc_main_log.warning(f"Clash Maintenance Started. Sync loops locked.\n"
            + text2art("Clash Maintenance Started",font="small")
            )
        await self.bot.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.playing,
                name=f"Clash Maintenance!")
            )
    
    @coc.ClientEvents.maintenance_completion()
    async def clash_maintenance_complete(self,time_started):
        self.api_maintenance = False
        if self.clash_task_lock.locked():
            self.clash_task_lock.release()

        maint_start = pendulum.instance(time_started)
        maint_end = pendulum.now()

        self.coc_main_log.warning(f"Clash Maintenance Completed. Maintenance took: {maint_end.diff(maint_start).in_minutes()} minutes. Sync loops unlocked.\n"
            + text2art("Clash Maintenance Completed",font="small")
            )
        await self.bot.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.playing,
                name=f"Clash of Clans!")
            )
    
    ############################################################
    ############################################################
    #####
    ##### LISTENERS
    #####
    ############################################################
    ############################################################    
    @commands.Cog.listener("on_shard_connect")
    async def status_on_connect(self, shard_id):
        await self.bot.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.listening,
                name=f"$help!")
                )

    @commands.Cog.listener("on_member_join")
    async def new_discord_member(self,member:discord.Member):
        new_member = aMember(member.id,member.guild.id)
        await new_member.fetch_user_links()
    
    @commands.Cog.listener("on_member_update")
    async def sync_roles(self,before:discord.Member,after:discord.Member):
        now = pendulum.now()
        try:
            if before.roles == after.roles:
                return
            member = aMember(after.id,after.guild.id)
            while True:
                if member.last_role_sync and (now.int_timestamp - member.last_role_sync.int_timestamp) < 10:
                    break
                try:
                    await member.sync_clan_roles()
                    break
                except CacheNotReady:
                    await asyncio.sleep(60)
                    continue
        except Exception as e:
            self.coc_main_log.exception(f"Error syncing roles for {after.id} {after.name}#{after.discriminator} - {e}")
    
    @commands.Cog.listener("on_guild_channel_create")
    async def recruiting_ticket_listener(self,channel):

        application_id = None
        newline = "\n"

        await asyncio.sleep(2)        
        
        guild = aGuild(channel.guild.id)
        if len(guild.apply_panels) == 0:
            return
        
        async for message in channel.history(limit=1,oldest_first=True):
            for embed in message.embeds:
                if embed.footer.text == "Application ID":                    
                    application_id = embed.description
                    break
        if not application_id:
            return
        
        try:
            application = db_ClanApplication.objects.get(id=application_id)
        except DoesNotExist:
            embed = await clash_embed(
                context=self.bot,
                message=f"**Could not find application.**",
                success=False
                )
            return await channel.send(embed=embed)
        
        account_tasks = [asyncio.create_task(aPlayer.create(i)) for i in application.tags]
        clan_tasks = [asyncio.create_task(aClan.create(i)) for i in application.clans]
        
        member = aMember(user_id=application.applicant_id,guild_id=application.guild_id)
        
        clans = [c for c in await asyncio.gather(*clan_tasks,return_exceptions=True) if isinstance(c,aClan)]        
        application_embed = await clash_embed(
            context=self.bot,
            title=f"{member.name}",
            message=f"`{member.user_id}`"
                + f"\n**Joined Discord**"
                + f"\n<t:{member.created_at.int_timestamp}:f>"
                + f"\n\n**Joined {channel.guild.name}**"
                + f"\n<t:{member.joined_at.int_timestamp}:f>"
                + (f"\n\n**Applied to Clans**" if len(clans) > 0 else "")
                + (f"\n{newline.join([c.title for c in clans])}" if len(clans) > 0 else "")
                + f"\n\u200b",
            thumbnail=member.display_avatar)
        
        if application.answer_q1[1]:
            application_embed.add_field(
                name=f"**{application.answer_q1[0]}**",
                value=f"{application.answer_q1[1]}\n\u200b",
                inline=False
                )
        if application.answer_q2[1]:
            application_embed.add_field(
                name=f"**{application.answer_q2[0]}**",
                value=f"{application.answer_q2[1]}\n\u200b",
                inline=False
                )
        if application.answer_q3[1]:
            application_embed.add_field(
                name=f"**{application.answer_q3[0]}**",
                value=f"{application.answer_q3[1]}\n\u200b",
                inline=False
                )
        if application.answer_q4[1]:
            application_embed.add_field(
                name=f"**{application.answer_q4[0]}**",
                value=f"{application.answer_q4[1]}\n\u200b",
                inline=False
                )
        
        accounts = [a for a in await asyncio.gather(*account_tasks,return_exceptions=True) if isinstance(a,aPlayer)]        
        accounts.sort(key=lambda x:(x.town_hall.level,x.exp_level),reverse=True)
        accounts_townhalls = sorted(list(set([a.town_hall.level for a in accounts])),reverse=True)

        other_accounts = [tag for tag in member.account_tags if tag not in application.tags]
        if len(accounts) == 0:
            accounts_embed_text = "Did not find any valid accounts."
        else:
            accounts_embed_text = ""
            async for a in AsyncIter(accounts):
                accounts_embed_text += account_recruiting_summary(a)
        
        accounts_embed = await clash_embed(
            context=self.bot,
            title=f"{member.name}",
            message=accounts_embed_text + "\u200b",
            thumbnail=member.display_avatar
            )
        if len(other_accounts) > 0:
            list_oa = []
            other_accounts_embed_text = ""
            async for a in AsyncIter(other_accounts[:5]):
                try:
                    account = await aPlayer.create(a)
                except Exception:
                    continue
                else:
                    list_oa.append(account)
            
            list_oa.sort(key=lambda x:(x.town_hall.level,x.exp_level),reverse=True)
            async for a in AsyncIter(list_oa):
                other_accounts_embed_text += f"{a.title}\n\u200b\u3000{EmojisClash.CLAN} {a.clan_description}\n\n"

            accounts_embed.add_field(
                name=f"**Other Accounts (max. 5)**",
                value="\n" + other_accounts_embed_text,
                inline=False
                )
                        
        application.ticket_channel = channel.id
        application.save()

        channel_name = ""
        if channel.name.startswith('ticket-'):
            channel_name += f"{re.split('-', channel.name)[1]}-"
        else:
            channel_name += f"{re.split('📝', channel.name)[0]}"
        
        for c in clans:
            if c.unicode_emoji:
                channel_name += f"{c.unicode_emoji}"
            else:
                channel_name += f"-{c.abbreviation}"
        
        for th in accounts_townhalls:
            channel_name += f"-th{th}"
        
        await channel.edit(name=channel_name.lower())                    
        await channel.send(embed=application_embed)
        await channel.send(embed=accounts_embed)        
        await channel.set_permissions(member.discord_member,read_messages=True)
        
        async for c in AsyncIter(clans):
            link = ClanGuildLink.get_link(c.tag,channel.guild.id)
            if link.coleader_role:
                await channel.set_permissions(link.coleader_role,read_messages=True)
                if len(channel.threads) > 0:
                    thread = channel.threads[0]
                    await thread.send(
                        f"{link.coleader_role.mention} {c.emoji} {c.name} has a new applicant: {', '.join(f'TH{num}' for num in accounts_townhalls)}.",
                        allowed_mentions=discord.AllowedMentions(roles=True)
                        )                
    
    ##################################################
    ### SEASON HELPERS
    ##################################################
    @property    
    def current_season(self):
        try:
            current_season = aClashSeason(dSeason.objects.get(s_is_current=True).only('s_id').s_id)
        except:
            current_season = None
        
        if not current_season:
            current_season = aClashSeason.get_current_season()
            current_season.is_current = True
        return current_season

    @current_season.setter
    def current_season(self,season:aClashSeason):
        season.is_current = True
        season.save()
    
    @property
    def tracked_seasons(self) -> list[aClashSeason]:
        non_current_seasons = [aClashSeason(ss.s_id) for ss in dSeason.objects(s_is_current=False).only('s_id')]
        tracked = [s for s in non_current_seasons if s.season_start <= pendulum.now()]
        tracked.sort(key=lambda x:x.season_start,reverse=True)
        return tracked

    ##################################################
    ### TASK HELPERS
    ##################################################   
    async def create_player_task(self,player_tag):
        loop = PlayerLoop(self.bot,player_tag)
        if not loop.loop_active:
            await loop.start()
            return player_tag
    
    async def create_clan_task(self,clan_tag):
        loop = ClanLoop(self.bot,clan_tag)
        if not loop.loop_active:
            await loop.start()
            return clan_tag
    
    async def create_war_task(self,clan_tag):
        loop = ClanWarLoop(self.bot,clan_tag)
        if not loop.loop_active:
            await loop.start()
            return clan_tag
    
    async def create_raid_task(self,clan_tag):
        loop = ClanRaidLoop(self.bot,clan_tag)
        if not loop.loop_active:
            await loop.start()
            return clan_tag
    
    async def create_guild_task(self,guild_id):
        loop = DiscordGuildLoop(self.bot,guild_id)
        if not loop.loop_active:
            await loop.start()
            return guild_id
    
    async def _season_check(self):
        season = aClashSeason.get_current_season()
        if season.id == self.current_season.id:
            return None        
        async with self.clash_task_lock:
            while self.clash_semaphore._value < self.clash_semaphore_limit:
                await asyncio.sleep(0)
            self.current_season = season
        
        self.coc_main_log.info(f"New Season Started: {season.id} {season.description}\n"
            + text2art(f"{season.id}",font="small")
            )
        self.coc_data_log.info(f"New Season Started: {season.id} {season.description}\n"
            + text2art(f"{season.id}",font="small")
            )
        
        await self.bot.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.playing,
                name=f"start of the {self.current_season.short_description} Season! Clash on!")
                )

        bank_cog = self.bot.get_cog('Bank')
        if bank_cog:
            await bank_cog.member_legend_rewards()
            await bank_cog.apply_bank_taxes()
            await bank_cog.month_end_sweep()

    ##################################################
    ### PLAYER HELPERS
    ##################################################
    def get_player(self,tag:str) -> aPlayer:
        return aPlayer.from_cache(tag)
    
    def count_members_by_season(self,clan:Optional[aClan]=None, season:Optional[aClashSeason]=None):
        if not season or season.id not in [s.id for s in self.tracked_seasons]:
            season = self.current_season
        
        if season.is_current and clan:
            return len(db_Player.objects(home_clan=clan.tag,is_member=True).only('tag'))
        elif season.is_current and not clan:
            return len(db_Player.objects(is_member=True).only('tag'))
        elif not season.is_current and clan:
            return len(db_PlayerStats.objects(home_clan=clan.tag,is_member=True,season=season.id).only('tag'))
        elif not season.is_current and not clan:
            return len(db_PlayerStats.objects(is_member=True,season=season.id).only('tag'))
        else:
            return 0 
    
    def get_members_by_season(self,clan:Optional[aClan]=None, season:Optional[aClashSeason]=None):
        if not season or season.id not in [s.id for s in self.tracked_seasons]:
            season = self.current_season
        
        if season.is_current and clan:
            query = db_Player.objects(home_clan=clan.tag,is_member=True).only('tag')
        elif season.is_current and not clan:
            query = db_Player.objects(is_member=True).only('tag')
        elif not season.is_current and clan:
            query = db_PlayerStats.objects(home_clan=clan.tag,is_member=True,season=season.id).only('tag')
        elif not season.is_current and not clan:
            query = db_PlayerStats.objects(is_member=True,season=season.id).only('tag')
        
        #ret_players = [aPlayer.from_cache(p.tag) for p in query]
        #return sorted(ret_players, key=lambda x:(ClanRanks.get_number(x.alliance_rank),x.town_hall.level,x.exp_level),reverse=True)     
        return []

    async def fetch_player(self,tag:str) -> aPlayer:
        return await aPlayer.create(tag=tag)

    ##################################################
    ### CLAN HELPERS
    ##################################################
    def get_clan(self,tag:str) -> aClan:
        return aClan.from_cache(tag)
    
    async def fetch_clan(self,tag:str) -> aClan:
        return await aClan.create(tag)
    
    def get_alliance_clans(self):
        ret_clans = [self.get_clan(c.tag) for c in db_AllianceClan.objects().only('tag')]
        return sorted(ret_clans, key=lambda x:(x.level,x.capital_hall),reverse=True)
    
    def get_cwl_clans(self):
        ret_clans = [aClan.from_cache(c.tag) for c in db_WarLeagueClanSetup.objects(is_active=True).only('tag')]
        return sorted(ret_clans, key=lambda x:(x.level,multiplayer_leagues.index(x.war_league.name)),reverse=True)

    ##################################################
    ### CLAN WAR HELPERS
    ##################################################
    def get_clan_war_from_id(self,war_id:str) -> aClanWar:
        clan_war = aClanWar(war_id=war_id)
        if not clan_war._found_in_db:
            raise InvalidID(war_id)
        return clan_war
    
    def get_wars_by_player(self,player_tag:str,season: Optional[aClashSeason] = None):
        return aClanWar.for_player(player_tag,season=season)
    
    async def get_clan_war(self,tag:str) -> aClanWar:
        api_war = None
        try:
            api_war = await self.bot.coc_client.get_clan_war(tag)
        except coc.PrivateWarLog:
            return None
        except coc.NotFound as exc:
            raise InvalidTag(tag) from exc
        except (coc.Maintenance,coc.GatewayError) as exc:
            raise ClashAPIError(exc) from exc
        
        if not api_war or getattr(api_war,'state','notInWar') == 'notInWar':
            return None
        
        clan_war = await aClanWar.create_from_api(api_war)
        return clan_war

    async def get_league_war(self,league_group_id:str,war_tag:str):
        api_war = None
        try:
            api_war = await self.bot.coc_client.get_league_war(war_tag)
        except coc.NotFound as exc:
            raise InvalidTag(war_tag) from exc
        except (coc.Maintenance,coc.GatewayError) as exc:
            raise ClashAPIError(exc) from exc

        if api_war.clan and api_war.opponent:
            clan_war = await aClanWar.create_from_api(api_war,league_group_id=league_group_id)
            return clan_war

        return None

    async def get_league_group(self,tag:str) -> WarLeagueGroup:
        try:
            api_group = await self.bot.coc_client.get_league_group(tag)
        except coc.NotFound:
            pass
        except (coc.Maintenance,coc.GatewayError) as exc:
            raise ClashAPIError(exc)
        else:
            if api_group and api_group.state in ['preparation','inWar','warEnded'] and pendulum.from_format(api_group.season, 'YYYY-MM').format('M-YYYY') == self.current_season.id:
                league_group = await WarLeagueGroup.from_api(api_group)

                return league_group
        return None

    ##################################################
    ### RAID WEEKEND HELPERS
    ##################################################
    def get_raid_weekend_from_id(self,raid_id:str) -> aRaidWeekend:
        raid_weekend = aRaidWeekend(raid_id=raid_id)
        if not raid_weekend._found_in_db:
            raise InvalidID(raid_id)            
        return raid_weekend
    
    def get_raids_by_player(self,player_tag:str,season:Optional[aClashSeason] = None):
        return aRaidWeekend.for_player(player_tag,season=season)
    
    async def get_raid_weekend(self,tag:str) -> aRaidWeekend:
        clan = await aClan.create(tag)
        return clan.get_raid_weekend()        
        
    
    ##################################################
    ### DISCORD HELPERS
    ##################################################
    def get_member(self,user_id:int,guild_id:int):
        return aMember(
            user_id=user_id,
            guild_id=guild_id
            )
    def get_guild(self,guild_id:int):
        return aGuild(
            guild_id=guild_id
            )
    ##################################################
    ### TASK HELPERS
    ##################################################
    async def capital_contribution_feed(self,player:aPlayer,amount:int):
        await CapitalContributionFeed.send_feed_update(player=player,amount=amount)
    
    @commands.group(name="cocdata")
    @commands.is_owner()
    async def command_group_clash_data(self,ctx):
        """Manage the Clash of Clans Data Client."""
        if not ctx.invoked_subcommand:
            pass

    @command_group_clash_data.command(name="status")
    @commands.is_owner()
    async def subcommand_clash_data_status(self,ctx):
        """Clash of Clans Data Status."""

        if not hasattr(self.bot,'coc_client'):
            return await ctx.reply("Clash of Clans API Client not yet initialized.")
        
        embed = await clash_embed(ctx,
            title="**Clash of Clans Data Report**",
            message=f"**T**: Total | **A**: Active | **R**: Running | **W**: Waiting\n"
                )
        embed.add_field(
            name="**Events Client**",
            value="```ini"
                + f"\n{'[Master]':<15} {'Locked' if self.clash_task_lock.locked() else 'Unlocked'}"
                + (f" (API Maintenance)" if self.api_maintenance else "")
                + f"\n{'[Semaphore]':<15} {self.clash_semaphore._value:,} / {self.clash_semaphore_limit:,} (Waiting: {len(self.clash_semaphore._waiters) if self.clash_semaphore._waiters else 0:,})"
                + f"\n{'[Keys]':<15} {len(self.bot.coc_client.http._keys)}"
                + "```",
            inline=False
            )        
        embed.add_field(
            name="**Players**",
            value="```ini"
                + f"\n{'[Mem/DB/Queue]':<15} {len(self.player_cache):,} / {len(db_Player.objects()):,} (Queue: {len(self.player_cache.queue):,})"
                + f"\n{'[Loops]':<15} {len([i for i in PlayerLoop.loops() if i.loop_active]):,}"
                + f"\n{'[API Time]':<15} {round(PlayerLoop.api_avg())}s (min: {round(PlayerLoop.api_min())}s, max: {round(PlayerLoop.api_max())}s)"
                + f"\n{'[Runtime]':<15} {round(PlayerLoop.runtime_avg())}s (min: {round(PlayerLoop.runtime_min())}s, max: {round(PlayerLoop.runtime_max())}s)"
                + "```",
            inline=False
            )
        embed.add_field(
            name="**Clans**",
            value="```ini"
                + f"\n{'[Mem/DB/Queue]':<15} {len(self.clan_cache):,} / {len(db_Clan.objects()):,} (Queue: {len(self.clan_cache.queue):,})"
                + f"\n{'[Loops]':<15} {len([i for i in ClanLoop.loops() if i.loop_active]):,}"
                + f"\n{'[API Time]':<15} {round(ClanLoop.api_avg())}s (min: {round(ClanLoop.api_min())}s, max: {round(ClanLoop.api_max())}s)"
                + f"\n{'[Runtime]':<15} {round(ClanLoop.runtime_avg())}s (min: {round(ClanLoop.runtime_min())}s, max: {round(ClanLoop.runtime_max())}s)"
                + "```",
            inline=False
            )
        embed.add_field(
            name="**Clan Wars**",
            value="```ini"
                + f"\n{'[Database]':<15} {len(db_ClanWar.objects()):,}"
                + f"\n{'[Loops]':<15} {len([i for i in ClanWarLoop.loops() if i.loop_active]):,}"
                + f"\n{'[API Time]':<15} {round(ClanWarLoop.api_avg())}s"
                + f"\n{'[Runtime]':<15} {round(ClanWarLoop.runtime_avg())}s"
                + "```",
            inline=True
            )
        embed.add_field(
            name="**Capital Raids**",
            value="```ini"
                + f"\n{'[Database]':<15} {len(db_RaidWeekend.objects()):,}"
                + f"\n{'[Loops]':<15} {len([i for i in ClanRaidLoop.loops() if i.loop_active]):,}"
                + f"\n{'[API Time]':<15} {round(ClanRaidLoop.api_avg())}s"
                + f"\n{'[Runtime]':<15} {round(ClanRaidLoop.runtime_avg())}s"
                + "```",
            inline=True
            )        
        embed.add_field(
            name="**Discord Guilds**",
            value="```ini"
                + f"\n{'[Available]':<15} {len(self.bot.guilds):,}"
                + f"\n{'[Loops]':<15} {len([i for i in DiscordGuildLoop.loops() if i.loop_active]):,}"
                + f"\n{'[Runtime]':<15} {round(DiscordGuildLoop.runtime_avg())}s"
                + "```",
            inline=False
            )
        await ctx.reply(embed=embed)
    
    @command_group_clash_data.command(name="lock")
    @commands.is_owner()
    async def subcommand_clash_data_lock(self,ctx):
        """Lock the Clash of Clans Data Loop."""
        if self.clash_task_lock.locked():
            await ctx.reply("Clash Data Loop is already locked.")
        else:
            await self.clash_task_lock.acquire()
            await ctx.reply("Clash Data Loop locked.")
    
    @command_group_clash_data.command(name="unlock")
    @commands.is_owner()
    async def subcommand_clash_data_unlock(self,ctx):
        """Unlock the Clash of Clans Data Loop."""
        if self.clash_task_lock.locked():
            self.clash_task_lock.release()
            await ctx.reply("Clash Data Loop unlocked.")
        else:
            await ctx.reply("Clash Data Loop is not locked.")
    
    @command_group_clash_data.command(name="stream")
    @commands.is_owner()
    async def subcommand_clash_data_stream(self,ctx):
        """Toggle the Clash of Clans Data Stream."""

        current_data_level = self.coc_data_log.level

        if current_data_level == logging.INFO:
            self.coc_main_log.setLevel(logging.DEBUG)
            self.coc_data_log.setLevel(logging.DEBUG)
            self.coc_main_log.debug("Clash Data Stream enabled.")
            await ctx.reply("Clash Data Stream enabled.")
        
        else:
            self.coc_main_log.setLevel(logging.INFO)
            self.coc_data_log.setLevel(logging.INFO)
            self.coc_main_log.info("Clash Data Stream disabled.")
            await ctx.reply("Clash Data Stream disabled.")